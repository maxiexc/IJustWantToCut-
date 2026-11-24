import sys
import os
import re
import ctypes
import ctypes.util
import shlex  # 【新增】格式化印出含空白路徑的 FFmpeg 指令
import argparse

if sys.platform.startswith("linux"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    try:
        # 啟用 X11 多執行緒安全鎖，解除 --no-xlib 限制
        ctypes.CDLL("libX11.so.6").XInitThreads()
    except OSError:
        pass


_VLC_DLL_DIR_HANDLES = []


def _configure_vlc_environment():
    """在匯入 python-vlc 前配置 libvlc 與 plugins 路徑。"""
    if getattr(sys, "frozen", False):
        candidate_roots = [os.path.dirname(os.path.abspath(sys.executable))]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and os.path.normpath(meipass) != os.path.normpath(candidate_roots[0]):
            candidate_roots.append(meipass)

        lib_name = "libvlc.dll" if sys.platform == "win32" else "libvlc.so.5"
        for root in candidate_roots:
            vlc_dir = os.path.join(root, "vlc")
            lib_path = os.path.join(vlc_dir, lib_name)
            if os.path.isfile(lib_path):
                if sys.platform == "win32":
                    if hasattr(os, "add_dll_directory"):
                        try:
                            _VLC_DLL_DIR_HANDLES.append(os.add_dll_directory(vlc_dir))
                        except OSError:
                            pass
                    current_path = os.environ.get("PATH", "")
                    if vlc_dir not in current_path.split(os.pathsep):
                        os.environ["PATH"] = vlc_dir + os.pathsep + current_path
                    core_path = os.path.join(vlc_dir, "libvlccore.dll")
                    if os.path.isfile(core_path):
                        try:
                            ctypes.CDLL(core_path)
                        except OSError:
                            pass

                os.environ.setdefault("PYTHON_VLC_LIB_PATH", lib_path)
                plugins_dir = os.path.join(vlc_dir, "plugins")
                module_dir = plugins_dir if os.path.isdir(plugins_dir) else vlc_dir
                os.environ.setdefault("PYTHON_VLC_MODULE_PATH", module_dir)
                os.environ.setdefault("VLC_PLUGIN_PATH", module_dir)
                break

    if sys.platform.startswith("linux") and "PYTHON_VLC_LIB_PATH" not in os.environ:
        found = ctypes.util.find_library("vlc")
        if not found:
            for candidate in (
                "/usr/lib/x86_64-linux-gnu/libvlc.so.5",
                "/usr/lib/aarch64-linux-gnu/libvlc.so.5",
                "/usr/lib/libvlc.so.5",
            ):
                if os.path.isfile(candidate):
                    os.environ["PYTHON_VLC_LIB_PATH"] = candidate
                    break


_configure_vlc_environment()

_VLC_IMPORT_ERROR = None
try:
    import vlc
except Exception as exc:  # ImportError, OSError, NotImplementedError
    vlc = None
    _VLC_IMPORT_ERROR = exc

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QFrame, QPushButton, QLabel,
                               QSlider, QCheckBox, QComboBox, QFileDialog,
                               QProgressBar, QFormLayout, QMessageBox, QDoubleSpinBox,
                               QTabWidget, QSpinBox, QGroupBox)  # 新增匯入元件
from PySide6.QtCore import Qt, QTimer, QProcess
from PySide6.QtGui import QIcon

from media_processor import MediaProcessor
from version import APP_NAME, APP_VERSION


def _resolve_icon_path():
    """尋找應用程式圖示路徑（支援打包與開發模式）。"""
    candidates = []
    preferred_names = ("ijustwanttocut.ico", "ijustwanttocut.svg") if sys.platform == "win32" else ("ijustwanttocut.svg", "ijustwanttocut.ico")

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        meipass = getattr(sys, "_MEIPASS", None)
        for root in (exe_dir, meipass):
            if not root:
                continue
            for name in preferred_names:
                candidates.append(os.path.join(root, "assets", name))

    if sys.platform.startswith("linux"):
        candidates.append("/usr/share/icons/hicolor/scalable/apps/ijustwanttocut.svg")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    for name in preferred_names:
        candidates.append(os.path.join(script_dir, "packaging", "assets", name))

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None

MP4_BTN_STYLE = "background-color: #2980b9; color: white; font-weight: bold;"
GIF_BTN_STYLE = "background-color: #8e44ad; color: white; font-weight: bold;"
STOP_BTN_STYLE = "background-color: #c0392b; color: white; font-weight: bold;"


class FastCutEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} - 剪輯變速工具")
        self.setGeometry(100, 100, 1050, 650)

        self.processor = MediaProcessor()
        self.current_media_info = None
        self.input_file = None
        self.mark_in_ms = 0
        self.mark_out_ms = 0

        self.init_ui()
        self.init_vlc()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui_time)
        self.timer.start(50)

        self.ffmpeg_process = QProcess(self)
        self.ffmpeg_process.readyReadStandardError.connect(self.read_ffmpeg_progress)
        self.ffmpeg_process.finished.connect(self.export_finished)
        self.ffmpeg_error_log = ""  # 新增：用於儲存詳細日誌
        self.is_exporting = False
        self.export_cancelled = False
        self.current_output_file = None
        self.current_export_btn = None

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # ================= 左側：影片預覽與剪輯區 (保持不變) =================
        left_layout = QVBoxLayout()
        self.btn_load = QPushButton("載入影片素材")
        self.btn_load.setMinimumHeight(40)
        self.btn_load.clicked.connect(self.load_video)
        left_layout.addWidget(self.btn_load)

        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setMinimumSize(640, 360)
        left_layout.addWidget(self.video_frame)

        self.slider_progress = QSlider(Qt.Horizontal)
        self.slider_progress.setRange(0, 0)
        self.slider_progress.setEnabled(False)
        self.slider_progress.sliderMoved.connect(self.seek_video)
        left_layout.addWidget(self.slider_progress)

        time_layout = QHBoxLayout()
        self.btn_play = QPushButton("▶ 播放 / 暫停")
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_play.setEnabled(False)
        self.lbl_time = QLabel("00:00:00.000 / 00:00:00.000")
        time_layout.addWidget(self.btn_play)
        time_layout.addWidget(self.lbl_time)
        time_layout.addStretch()
        left_layout.addLayout(time_layout)

        mark_layout = QHBoxLayout()
        self.btn_mark_in = QPushButton("設定起點 (Mark In)")
        self.btn_mark_in.clicked.connect(self.set_mark_in)
        self.btn_mark_out = QPushButton("設定終點 (Mark Out)")
        self.btn_mark_out.clicked.connect(self.set_mark_out)
        self.lbl_range = QLabel("剪輯範圍: 全部")
        mark_layout.addWidget(self.btn_mark_in)
        mark_layout.addWidget(self.btn_mark_out)
        mark_layout.addWidget(self.lbl_range)
        left_layout.addLayout(mark_layout)

        main_layout.addLayout(left_layout, stretch=2)

        # ================= 右側：編輯與分頁匯出面板 =================
        right_layout = QVBoxLayout()

        # --- 共用設定區 (播放速度) ---
        group_common = QGroupBox("共用編輯設定")
        layout_common = QFormLayout()

        speed_layout = QHBoxLayout()
        self.slider_speed = QSlider(Qt.Horizontal)
        self.slider_speed.setRange(1, 50)
        self.slider_speed.setValue(10)
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.05, 5.0)
        self.spin_speed.setSingleStep(0.05)
        self.spin_speed.setValue(1.0)
        self.spin_speed.setSuffix(" x")

        self.slider_speed.valueChanged.connect(lambda v: self.spin_speed.setValue(v / 10.0))
        self.spin_speed.valueChanged.connect(lambda v: self.slider_speed.setValue(int(v * 10)))
        speed_layout.addWidget(self.slider_speed)
        speed_layout.addWidget(self.spin_speed)
        layout_common.addRow("播放速度:", speed_layout)
        group_common.setLayout(layout_common)
        right_layout.addWidget(group_common)

        # --- 分頁區 (Tabs) ---
        self.tabs = QTabWidget()

        # 【Tab 1】H.265 (MP4) 匯出
        tab_mp4 = QWidget()
        layout_mp4 = QFormLayout(tab_mp4)

        self.chk_remove_audio = QCheckBox("匯出時去除音軌")
        layout_mp4.addRow("音軌:", self.chk_remove_audio)

        self.combo_res_mp4 = QComboBox()
        self.combo_res_mp4.setEditable(True)
        self.combo_res_mp4.addItems(["原始解析度", "1920 (1080p)", "2560 (2K)", "3840 (4K)"])
        self.combo_res_mp4.setCurrentText("1920 (1080p)")  # 【修改】預設 1080p
        layout_mp4.addRow("目標寬度:", self.combo_res_mp4)

        # 輸出幀率上限 (可選：不限制 / 60 FPS / 30 FPS)
        self.combo_fps_mp4 = QComboBox()
        self.combo_fps_mp4.addItems(["不限制 (原始幀率)", "上限 60 FPS", "上限 30 FPS"])
        self.combo_fps_mp4.setCurrentText("上限 30 FPS")  # 【修改】預設上限 30 FPS
        layout_mp4.addRow("幀率上限:", self.combo_fps_mp4)

        # 【新增】8-bit 色彩相容性選項
        self.chk_force_8bit = QCheckBox("強制輸出 8-bit (yuv420p)")
        layout_mp4.addRow("色彩相容:", self.chk_force_8bit)

        self.slider_quality = QSlider(Qt.Horizontal)
        self.slider_quality.setRange(18, 32)
        self.slider_quality.setValue(23)
        self.lbl_quality_val = QLabel("品質: 預設 (CRF 23)")
        self.lbl_bitrate_info = QLabel("原始碼率上限: 尚未載入")
        self.lbl_bitrate_info.setStyleSheet("color: gray; font-size: 10px;")
        self.slider_quality.valueChanged.connect(lambda v: self.lbl_quality_val.setText(f"品質: CRF {v}"))
        layout_mp4.addRow("匯出畫質:", self.slider_quality)
        layout_mp4.addRow("", self.lbl_quality_val)
        layout_mp4.addRow("", self.lbl_bitrate_info)

        self.btn_export_mp4 = QPushButton("匯出為 MP4 (H.265)")
        self.btn_export_mp4.setMinimumHeight(40)
        self.btn_export_mp4.setStyleSheet(MP4_BTN_STYLE)
        self.btn_export_mp4.clicked.connect(self.start_export_mp4)
        self.btn_export_mp4.setEnabled(False)
        layout_mp4.addRow(self.btn_export_mp4)

        self.tabs.addTab(tab_mp4, "MP4 (H.265)")

        # 【Tab 2】GIF 動圖匯出
        tab_gif = QWidget()
        layout_gif = QFormLayout(tab_gif)

        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 60)
        self.spin_fps.setValue(15)  # GIF 預設通常為 10~15 較省空間
        self.spin_fps.setSuffix(" FPS")
        layout_gif.addRow("每秒張數:", self.spin_fps)

        self.combo_res_gif = QComboBox()
        self.combo_res_gif.setEditable(True)
        self.combo_res_gif.addItems(["480", "640", "800", "1024"])  # GIF 解析度通常較小
        layout_gif.addRow("目標寬度:", self.combo_res_gif)

        self.btn_export_gif = QPushButton("匯出為 GIF 動圖")
        self.btn_export_gif.setMinimumHeight(40)
        self.btn_export_gif.setStyleSheet(GIF_BTN_STYLE)
        self.btn_export_gif.clicked.connect(self.start_export_gif)
        self.btn_export_gif.setEnabled(False)
        layout_gif.addRow(self.btn_export_gif)

        self.tabs.addTab(tab_gif, "GIF 動圖")

        right_layout.addWidget(self.tabs)
        right_layout.addStretch()

        # --- 全域進度條 ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        right_layout.addWidget(self.progress_bar)

        main_layout.addLayout(right_layout, stretch=1)

    def init_vlc(self):
        if vlc is None:
            raise RuntimeError(f"無法載入 VLC 模組: {_VLC_IMPORT_ERROR}")

        if sys.platform.startswith('linux'):
            # 【修改】使用 any 自動偵測系統可用的硬體解碼器（VAAPI / NVDEC 等），搭配 OpenGL 渲染
            self.vlc_instance = vlc.Instance(
                "--avcodec-hw=any",
                "--vout=gl"
            )
            if self.vlc_instance is None:
                self.vlc_instance = vlc.Instance()
            # 確保 QFrame 建立獨立的原生 X11 視窗句柄供 OpenGL/VAAPI 繪製
            self.video_frame.setAttribute(Qt.WA_NativeWindow, True)
        else:
            self.vlc_instance = vlc.Instance()

        if self.vlc_instance is None:
            raise RuntimeError("無法初始化 VLC 實例，請確認系統已安裝 libvlc5 與對應外掛。")

        self.media_player = self.vlc_instance.media_player_new()
        if self.media_player is None:
            raise RuntimeError("無法建立 VLC MediaPlayer。")

        win_id = int(self.video_frame.winId())
        if sys.platform.startswith('linux'):
            self.media_player.set_xwindow(win_id)
        elif sys.platform == 'win32':
            self.media_player.set_hwnd(win_id)

    # ---------- 播放與操作邏輯 ----------
    def load_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "選擇影片素材", "", "Video Files (*.mp4 *.mov *.avi *.mkv)"
        )
        if file_path:
            self.load_video_file(file_path)

    def load_video_file(self, file_path):
        if not os.path.isfile(file_path):
            QMessageBox.warning(self, "找不到檔案", f"找不到影片檔案:\n{file_path}")
            return

        try:
            media_info = self.processor.get_media_info(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "讀取失敗", f"無法解析影片資訊:\n{exc}")
            return

        self.input_file = file_path
        self.current_media_info = media_info
        max_kbps = int(self.current_media_info['bitrate_bps'] / 1000)
        src_fps = self.current_media_info.get('fps', 0.0)
        src_pix = self.current_media_info.get('pix_fmt', 'unknown')
        self.lbl_bitrate_info.setText(f"來源: {src_fps:.2f} fps | {src_pix} | 碼率 {max_kbps} kbps")

        total_ms = int(self.current_media_info['duration_sec'] * 1000)
        self.mark_in_ms = 0
        self.mark_out_ms = total_ms
        self.update_mark_label()

        self.slider_progress.setRange(0, total_ms)
        self.slider_progress.setEnabled(True)
        self.btn_play.setEnabled(True)
        self.btn_export_mp4.setEnabled(True)
        self.btn_export_gif.setEnabled(True)

        media = self.vlc_instance.media_new(file_path)
        self.media_player.set_media(media)
        self.media_player.play()

    def toggle_play(self):
        if self.media_player.is_playing():
            self.media_player.pause()
        else:
            self.media_player.play()

    def seek_video(self, position_ms):
        self.media_player.set_time(position_ms)
        self.update_time_label_only(position_ms)

    def update_ui_time(self):
        if self.current_media_info and self.media_player.is_playing():
            current_ms = self.media_player.get_time()
            if current_ms < 0: return
            if not self.slider_progress.isSliderDown():
                self.slider_progress.blockSignals(True)
                self.slider_progress.setValue(current_ms)
                self.slider_progress.blockSignals(False)
            self.update_time_label_only(current_ms)

    def update_time_label_only(self, current_ms):
        total_ms = int(self.current_media_info['duration_sec'] * 1000)
        self.lbl_time.setText(f"{self.format_ms(current_ms)} / {self.format_ms(total_ms)}")

    def format_ms(self, ms):
        m, s = divmod(int(ms / 1000), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}.{int(ms % 1000):03d}"

    def set_mark_in(self):
        self.mark_in_ms = max(0, self.media_player.get_time())
        self.update_mark_label()

    def set_mark_out(self):
        self.mark_out_ms = max(self.mark_in_ms, self.media_player.get_time())
        self.update_mark_label()

    def update_mark_label(self):
        self.lbl_range.setText(f"剪輯範圍: {self.format_ms(self.mark_in_ms)} 至 {self.format_ms(self.mark_out_ms)}")

    def parse_width(self, res_text):
        if "1920" in res_text:
            return 1920
        elif "2560" in res_text:
            return 2560
        elif "3840" in res_text:
            return 3840
        elif res_text.isdigit():
            return int(res_text)
        return None

    # ---------- 匯出處理 ----------
    def pre_export_setup(self):
        if not self.input_file: return None, None, None
        self.media_player.pause()
        start_sec = self.mark_in_ms / 1000.0
        end_sec = self.mark_out_ms / 1000.0
        speed = self.spin_speed.value()
        self.target_duration_sec = (end_sec - start_sec) / speed
        return start_sec, end_sec, speed

    def start_export_mp4(self):
        # 【新增】若正在執行 MP4 匯出，再點一次即為「停止匯出」
        if self.is_exporting:
            if self.current_export_btn == self.btn_export_mp4:
                self.cancel_export()
            return

        start_sec, end_sec, speed = self.pre_export_setup()
        if start_sec is None:
            return

        output_file, _ = QFileDialog.getSaveFileName(self, "匯出 MP4", "output.mp4", "MP4 影片檔 (*.mp4)")
        if not output_file:
            return

        # 【新增防呆】如果使用者勾選了去除音軌，或「原始影片根本沒音軌」，都強制設定為 True
        actual_remove_audio = self.chk_remove_audio.isChecked() or not self.current_media_info.get('has_audio', True)

        # 動態計算碼率上限（至少保底 30 Mbps，加速時等比例放寬）
        base_kbps = max(int(self.current_media_info['bitrate_bps'] / 1000), 30000)
        dynamic_max_kbps = int(base_kbps * max(1.0, speed))

        fps_text = self.combo_fps_mp4.currentText()
        max_fps = 60 if "60" in fps_text else (30 if "30" in fps_text else None)

        cmd_list = self.processor.build_export_command(
            self.input_file,
            output_file,
            start_sec,
            end_sec,
            speed_factor=speed,
            remove_audio=actual_remove_audio,
            target_width=self.parse_width(self.combo_res_mp4.currentText()),
            max_bitrate_kbps=dynamic_max_kbps,
            crf=self.slider_quality.value(),
            max_fps=max_fps,
            source_fps=self.current_media_info.get('fps', 0.0),
            force_8bit=self.chk_force_8bit.isChecked()
        )
        self.execute_ffmpeg(cmd_list, self.btn_export_mp4, output_file)

    def start_export_gif(self):
        # 【新增】若正在執行 GIF 匯出，再點一次即為「停止匯出」
        if self.is_exporting:
            if self.current_export_btn == self.btn_export_gif:
                self.cancel_export()
            return

        start_sec, end_sec, speed = self.pre_export_setup()
        if start_sec is None:
            return

        output_file, _ = QFileDialog.getSaveFileName(self, "匯出 GIF", "output.gif", "GIF 動圖 (*.gif)")
        if not output_file:
            return

        cmd_list = self.processor.build_gif_export_command(
            self.input_file, output_file, start_sec, end_sec,
            speed_factor=speed,
            target_width=self.parse_width(self.combo_res_gif.currentText()),
            fps=self.spin_fps.value()
        )
        self.execute_ffmpeg(cmd_list, self.btn_export_gif, output_file)

    def execute_ffmpeg(self, cmd_list, button, output_file):
        self.progress_bar.setValue(0)
        self.ffmpeg_error_log = ""
        self.is_exporting = True
        self.export_cancelled = False
        self.current_output_file = output_file
        self.current_export_btn = button

        # 鎖定另一顆按鈕，保留目前這顆作為「停止匯出」
        other_btn = self.btn_export_gif if button == self.btn_export_mp4 else self.btn_export_mp4
        other_btn.setEnabled(False)

        button.setEnabled(True)
        button.setText("停止匯出")
        button.setStyleSheet(STOP_BTN_STYLE)

        print("\n[FFmpeg CMD]", " ".join(shlex.quote(str(arg)) for arg in cmd_list))
        self.ffmpeg_process.start(cmd_list[0], cmd_list[1:])

    def cancel_export(self):
        if not self.is_exporting or self.ffmpeg_process.state() == QProcess.NotRunning:
            return

        self.export_cancelled = True
        if self.current_export_btn:
            self.current_export_btn.setEnabled(False)
            self.current_export_btn.setText("正在停止...")

        # 優先送出 'q' 讓 FFmpeg 跨平台正常退出，2 秒未結束則強制 kill
        self.ffmpeg_process.write(b"q\n")
        self.ffmpeg_process.closeWriteChannel()
        QTimer.singleShot(2000, self._force_kill_ffmpeg)

    def _force_kill_ffmpeg(self):
        if self.export_cancelled and self.ffmpeg_process.state() != QProcess.NotRunning:
            self.ffmpeg_process.kill()

    def read_ffmpeg_progress(self):
        output = self.ffmpeg_process.readAllStandardError().data().decode("utf-8", errors="replace")

        # 【修改】將文字持續附加到日誌變數中，避免進度條讀取後文字消失
        self.ffmpeg_error_log += output

        match = re.search(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})", output)
        if match and getattr(self, 'target_duration_sec', 0) > 0:
            h, m, s = match.groups()
            current_sec = int(h) * 3600 + int(m) * 60 + float(s)
            percent = int((current_sec / self.target_duration_sec) * 100)
            self.progress_bar.setValue(min(percent, 99))

    def export_finished(self, exit_code, exit_status=None):
        was_cancelled = self.export_cancelled
        target_file = self.current_output_file

        # 還原狀態與按鈕樣式
        self.is_exporting = False
        self.export_cancelled = False
        self.current_output_file = None
        self.current_export_btn = None

        for btn, label, style in (
            (self.btn_export_mp4, "匯出為 MP4 (H.265)", MP4_BTN_STYLE),
            (self.btn_export_gif, "匯出為 GIF 動圖", GIF_BTN_STYLE),
        ):
            btn.setEnabled(True)
            btn.setText(label)
            btn.setStyleSheet(style)

        if was_cancelled:
            self.progress_bar.setValue(0)
            if target_file and os.path.exists(target_file):
                try:
                    os.remove(target_file)
                except OSError as e:
                    print(f"[Warning] 清理未完成檔案失敗: {e}")
            QMessageBox.information(self, "已停止", "已停止匯出，並移除未完成的檔案。")
            return

        if exit_code == 0:
            self.progress_bar.setValue(100)
            QMessageBox.information(self, "完成", "匯出成功！")
        else:
            self.progress_bar.setValue(0)
            print("\n========== FFmpeg 完整錯誤日誌 ==========")
            print(self.ffmpeg_error_log)
            print("=========================================")
            key_lines = [
                line for line in self.ffmpeg_error_log.splitlines()
                if any(k in line.lower() for k in ("error", "invalid", "incompatible", "failed", "cannot", "unable"))
            ]
            err_msg = "\n".join(key_lines[-15:]) if key_lines else self.ffmpeg_error_log[-2500:]
            QMessageBox.critical(
                self, "錯誤",
                f"匯出失敗，錯誤代碼: {exit_code}\n\n關鍵錯誤（完整日誌已印於終端機）:\n{err_msg}"
            )

    def closeEvent(self, event):
        if hasattr(self, "timer") and self.timer is not None:
            self.timer.stop()

        if hasattr(self, "ffmpeg_process") and self.ffmpeg_process is not None:
            if self.ffmpeg_process.state() != QProcess.NotRunning:
                self.ffmpeg_process.terminate()
                if not self.ffmpeg_process.waitForFinished(1500):
                    self.ffmpeg_process.kill()

        if hasattr(self, "media_player") and self.media_player is not None:
            try:
                self.media_player.stop()
                self.media_player.release()
            except Exception:
                pass
            self.media_player = None

        if hasattr(self, "vlc_instance") and self.vlc_instance is not None:
            try:
                self.vlc_instance.release()
            except Exception:
                pass
            self.vlc_instance = None

        super().closeEvent(event)


def parse_args(argv):
    parser = argparse.ArgumentParser(prog=APP_NAME, add_help=True)
    parser.add_argument("--version", action="store_true", help="顯示版本資訊並結束")
    parser.add_argument("--smoke-test", action="store_true", help="執行啟動冒煙測試並結束")
    parser.add_argument("input_file", nargs="?", help="預先載入的影片路徑")
    return parser.parse_known_args(argv)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    args, qt_args = parse_args(argv)

    if args.version:
        print(f"{APP_NAME} {APP_VERSION}", flush=True)
        return 0

    app = QApplication(sys.argv[:1] + qt_args)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setDesktopFileName("ijustwanttocut")

    icon_path = _resolve_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    if vlc is None:
        if sys.platform == "win32":
            vlc_hint = "請確認安裝目錄下包含完整的 vlc\\libvlc.dll，或系統已安裝 64-bit VLC Media Player。"
        else:
            vlc_hint = "請確認系統已安裝 libvlc5 與 VLC 外掛。"
        err_detail = f"無法載入 VLC 播放引擎 (libvlc)。{vlc_hint}\n詳細錯誤: {_VLC_IMPORT_ERROR}"
        if args.smoke_test:
            print(f"[SMOKE-TEST] ERROR: {err_detail}", file=sys.stderr, flush=True)
        else:
            QMessageBox.critical(None, APP_NAME, err_detail)
        return 1

    try:
        window = FastCutEditor()
    except Exception as exc:
        if args.smoke_test:
            print(f"[SMOKE-TEST] ERROR: Failed to initialize FastCutEditor: {exc}", file=sys.stderr, flush=True)
        else:
            QMessageBox.critical(None, APP_NAME, f"程式初始化失敗:\n{exc}")
        return 1

    if args.smoke_test:
        tools = window.processor.check_tools()
        missing_tools = [name for name, (ok, _) in tools.items() if not ok]
        if missing_tools:
            print(f"[SMOKE-TEST] ERROR: Missing tools {missing_tools}: {tools}", file=sys.stderr, flush=True)
            window.close()
            return 1

        if window.vlc_instance is None or window.media_player is None:
            print("[SMOKE-TEST] ERROR: VLC instance or media player is None", file=sys.stderr, flush=True)
            window.close()
            return 1

        print(f"[SMOKE-TEST] ffmpeg={tools['ffmpeg'][1]}", flush=True)
        print(f"[SMOKE-TEST] ffprobe={tools['ffprobe'][1]}", flush=True)
        print(f"[SMOKE-TEST] vlc_lib={os.environ.get('PYTHON_VLC_LIB_PATH', 'system')}", flush=True)
        print(f"[SMOKE-TEST] vlc_plugins={os.environ.get('VLC_PLUGIN_PATH', 'system')}", flush=True)

        window.show()

        def _finish_smoke_test():
            window.close()
            app.quit()

        QTimer.singleShot(500, _finish_smoke_test)
        exit_code = app.exec()
        if exit_code != 0:
            print(f"[SMOKE-TEST] ERROR: Qt event loop exited with {exit_code}", file=sys.stderr, flush=True)
            return exit_code

        print("[SMOKE-TEST] OK", flush=True)
        return 0

    if args.input_file:
        QTimer.singleShot(0, lambda: window.load_video_file(args.input_file))

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
