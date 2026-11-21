import sys
import os
import re
import vlc
import ctypes
import shlex  # 【新增】格式化印出含空白路徑的 FFmpeg 指令

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QFrame, QPushButton, QLabel,
                               QSlider, QCheckBox, QComboBox, QFileDialog,
                               QProgressBar, QFormLayout, QMessageBox, QDoubleSpinBox,
                               QTabWidget, QSpinBox, QGroupBox)  # 新增匯入元件
from PySide6.QtCore import Qt, QTimer, QProcess

from media_processor import MediaProcessor

if sys.platform.startswith('linux'):
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    try:
        # 啟用 X11 多執行緒安全鎖，解除 --no-xlib 限制
        ctypes.CDLL("libX11.so.6").XInitThreads()
    except OSError:
        pass


class FastCutEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FastCut - 運動相機/空拍機 剪輯變速工具")
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
        self.combo_res_mp4.setEditable(True)
        self.combo_res_mp4.addItems(["原始解析度", "1920 (1080p)", "2560 (2K)", "3840 (4K)"])
        layout_mp4.addRow("目標寬度:", self.combo_res_mp4)

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
        self.btn_export_mp4.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold;")
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
        self.btn_export_gif.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold;")
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
        if sys.platform.startswith('linux'):
            # 【修改】使用 any 自動偵測系統可用的硬體解碼器（VAAPI / NVDEC 等），搭配 OpenGL 渲染
            self.vlc_instance = vlc.Instance(
                "--avcodec-hw=any",
                "--vout=gl"
            )
            # 確保 QFrame 建立獨立的原生 X11 視窗句柄供 OpenGL/VAAPI 繪製
            self.video_frame.setAttribute(Qt.WA_NativeWindow, True)
        else:
            self.vlc_instance = vlc.Instance()

        self.media_player = self.vlc_instance.media_player_new()
        win_id = int(self.video_frame.winId())
        if sys.platform.startswith('linux'):
            self.media_player.set_xwindow(win_id)
        elif sys.platform == 'win32':
            self.media_player.set_hwnd(win_id)

    # ---------- 播放與操作邏輯 ----------
    def load_video(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "選擇影片素材", "", "Video Files (*.mp4 *.mov *.avi)")
        if file_path:
            self.input_file = file_path
            self.current_media_info = self.processor.get_media_info(file_path)
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
            fps=self.spin_gif_fps.value()
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
        button.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")

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
        output = self.ffmpeg_process.readAllStandardError().data().decode("utf-8")

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

        for btn, label in ((self.btn_export_mp4, "匯出為 MP4 (H.265)"),
                           (self.btn_export_gif, "匯出為 GIF 動圖")):
            btn.setEnabled(True)
            btn.setText(label)
            btn.setStyleSheet("")

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

if __name__ == "__main__":
    if sys.platform.startswith('linux'):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        try:
            # 預先初始化 X11 多執行緒安全鎖，才能安心移除 --no-xlib 並啟用硬解/GL
            ctypes.CDLL("libX11.so.6").XInitThreads()
        except OSError:
            pass
    app = QApplication(sys.argv)
    window = FastCutEditor()
    window.show()
    sys.exit(app.exec())
