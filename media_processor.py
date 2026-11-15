import subprocess
import json
import sys
import os
import shutil  # 新增匯入


class MediaProcessor:
    def __init__(self):
        # 自動尋找 ffmpeg 與 ffprobe
        self.ffmpeg_path = self._resolve_executable("ffmpeg")
        self.ffprobe_path = self._resolve_executable("ffprobe")

    def _resolve_executable(self, cmd_name):
        """
        跨平台自動尋找執行檔邏輯：
        1. 先檢查專案當前目錄下有沒有 (針對 Windows 放入的 .exe)
        2. 若沒有，尋找系統環境變數 PATH 中有沒有 (針對 Ubuntu apt 安裝)
        """
        # 判斷是否為 Windows 並補上 .exe
        local_name = cmd_name + ".exe" if sys.platform == "win32" else cmd_name
        local_path = os.path.join(".", local_name)

        if os.path.exists(local_path):
            return local_path

        # 如果當前目錄沒有，去系統 PATH 找
        system_path = shutil.which(cmd_name)
        if system_path:
            return system_path

        # 如果都找不到，回傳預設名稱讓後續拋出錯誤
        return cmd_name

    def _ensure_exe(self, path):
        if sys.platform == "win32" and not path.endswith(".exe"):
            return path + ".exe"
        return path

    def get_media_info(self, file_path):
        """取得影片解析度、時長與原始碼率"""
        if not os.path.exists(self.ffprobe_path):
            raise FileNotFoundError(f"找不到 ffprobe: {self.ffprobe_path}")

        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,bit_rate,duration",
            "-of", "json",
            file_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFprobe 執行失敗: {result.stderr}")

        info = json.loads(result.stdout)
        stream = info.get("streams", [{}])[0]

        # 整理回傳資料
        data = {
            "width": int(stream.get("width", 0)),
            "height": int(stream.get("height", 0)),
            "duration_sec": float(stream.get("duration", 0.0)),
            # 如果 ffprobe 讀不到 bitrate，預設給 60Mbps (60000000)
            "bitrate_bps": int(stream.get("bit_rate", 60000000))
        }
        return data

    def build_export_command(self, input_file, output_file, start_sec, end_sec,
                             speed_factor=1.0, remove_audio=False,
                             target_width=None, max_bitrate_kbps=None, crf=28):
        """動態生成 FFmpeg 輸出指令"""

        cmd = [self.ffmpeg_path, "-y"]

        # 1. 剪輯時間設定 (放在 -i 前面以加速處理)
        cmd.extend(["-ss", str(start_sec)])
        cmd.extend(["-to", str(end_sec)])
        cmd.extend(["-i", input_file])

        # 2. 影像與聲音濾鏡 (Filter Complex)
        video_filters = []
        audio_filters = []

        # 變速處理
        if speed_factor != 1.0:
            video_filters.append(f"setpts={1.0 / speed_factor}*PTS")
            if not remove_audio:
                audio_filters.append(f"atempo={speed_factor}")

        # 解析度調整 (若有指定寬度，高度設為 -1 維持比例)
        if target_width:
            video_filters.append(f"scale={target_width}:-1")

        # 組合濾鏡字串
        filter_str = ""
        if video_filters:
            filter_str += f"[0:v]{','.join(video_filters)}[v];"
        if audio_filters:
            filter_str += f"[0:a]{','.join(audio_filters)}[a];"

        # 3. 映射與編碼設定
        if filter_str:
            # 移除最後的結尾分號
            filter_str = filter_str.rstrip(";")
            cmd.extend(["-filter_complex", filter_str])
            cmd.extend(["-map", "[v]"])
            if not remove_audio and audio_filters:
                cmd.extend(["-map", "[a]"])
        else:
            # 如果完全沒有濾鏡 (原速、原解析度)，直接映射影像
            cmd.extend(["-map", "0:v"])
            if not remove_audio:
                cmd.extend(["-map", "0:a"])

        # 音軌設定
        if remove_audio:
            cmd.append("-an")
        else:
            cmd.extend(["-c:a", "aac"])

        # 影像編碼設定 (H.265)
        cmd.extend([
            "-c:v", "libx265",
            "-crf", str(crf),
            "-tag:v", "hvc1"
        ])

        # 智慧碼率上限設定 (防止檔案過大)
        if max_bitrate_kbps:
            cmd.extend([
                "-maxrate", f"{max_bitrate_kbps}k",
                "-bufsize", f"{max_bitrate_kbps * 2}k"  # 緩衝區通常設為碼率的2倍
            ])

        cmd.append(output_file)
        return cmd

    def build_gif_export_command(self, input_file, output_file, start_sec, end_sec,
                                 speed_factor=1.0, target_width=480, fps=15):
        """動態生成高畫質 GIF 匯出指令"""
        cmd = [self.ffmpeg_path, "-y", "-ss", str(start_sec), "-to", str(end_sec), "-i", input_file]

        filters = []
        # 1. 變速處理
        if speed_factor != 1.0:
            filters.append(f"setpts={1.0 / speed_factor}*PTS")

        # 2. 影格率設定
        filters.append(f"fps={fps}")

        # 3. 解析度縮放 (採用 lanczos 演算法保持縮小後的銳利度)
        if target_width:
            filters.append(f"scale={target_width}:-1:flags=lanczos")

        # 4. 高畫質 GIF 調色盤技術 (split 分流 -> 生成調色盤 -> 應用調色盤)
        filter_str = ",".join(filters)
        complex_filter = f"[0:v]{filter_str},split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"

        cmd.extend(["-filter_complex", complex_filter])
        cmd.append(output_file)

        return cmd


# ---------------- 測試驗證區塊 ----------------
if __name__ == "__main__":
    processor = MediaProcessor()

    print("1. 測試 FFprobe 讀取媒體資訊...")
    try:
        info = processor.get_media_info("input.mp4")
        print(f"   解析度: {info['width']}x{info['height']}")
        print(f"   時長: {info['duration_sec']:.2f} 秒")
        print(f"   原始碼率: {info['bitrate_bps'] / 1000:.0f} kbps")

        print("\n2. 測試 FFmpeg 指令生成 (情境：2倍速, 去音軌, 寬度1920, 限流原始碼率)...")
        command_list = processor.build_export_command(
            input_file="input.mp4",
            output_file="output_test.mp4",
            start_sec=2.0,
            end_sec=10.0,
            speed_factor=2.0,
            remove_audio=True,
            target_width=1920,
            max_bitrate_kbps=int(info['bitrate_bps'] / 1000)
        )
        print("   生成指令:")
        print(" ".join(command_list))

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")