import subprocess
import json
import sys
import os
import shutil
from fractions import Fraction


class MediaProcessor:
    def __init__(self):
        # 跨平台自動尋找 ffmpeg 與 ffprobe（優先使用專案根目錄靜態版，其次系統 PATH）
        self.ffmpeg_path = self._resolve_executable("ffmpeg")
        self.ffprobe_path = self._resolve_executable("ffprobe")

    def _resolve_executable(self, cmd_name):
        local_name = cmd_name + ".exe" if sys.platform == "win32" else cmd_name
        local_path = os.path.abspath(os.path.join(".", local_name))

        if os.path.exists(local_path):
            return local_path

        system_path = shutil.which(cmd_name)
        if system_path:
            return system_path

        return cmd_name

    @staticmethod
    def _parse_int(value, default):
        try:
            if value is None or value == "N/A":
                return default
            return int(float(value))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _parse_float(value, default):
        try:
            if value is None or value == "N/A":
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    def get_media_info(self, file_path):
        """取得影片解析度、時長、原始碼率、幀率、色彩格式與音軌狀態"""
        if not os.path.exists(self.ffprobe_path) and not shutil.which(self.ffprobe_path):
            raise FileNotFoundError(f"找不到 ffprobe: {self.ffprobe_path}")

        cmd = [
            self.ffprobe_path, "-v", "error",
            "-show_entries",
            "format=duration,bit_rate:stream=codec_type,width,height,bit_rate,duration,r_frame_rate,avg_frame_rate,pix_fmt",
            "-of", "json",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFprobe 執行失敗: {result.stderr}")

        info = json.loads(result.stdout)
        streams = info.get("streams", [])
        fmt = info.get("format", {})

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        has_audio = any(s.get("codec_type") == "audio" for s in streams)

        # 時長與碼率：優先取視訊軌，若為 N/A 則退回容器 format 層級資訊
        duration_sec = self._parse_float(
            video_stream.get("duration"),
            self._parse_float(fmt.get("duration"), 0.0)
        )
        bitrate_bps = self._parse_int(
            video_stream.get("bit_rate"),
            self._parse_int(fmt.get("bit_rate"), 60000000)
        )

        # 解析幀率（優先使用 avg_frame_rate 以相容 VFR 螢幕錄影）
        fps_str = video_stream.get("avg_frame_rate", "0/0")
        if fps_str in ("0/0", "N/A", "", None):
            fps_str = video_stream.get("r_frame_rate", "0/0")
        try:
            fps = float(Fraction(fps_str)) if fps_str not in ("0/0", "N/A", "", None) else 0.0
        except (ValueError, ZeroDivisionError):
            fps = 0.0

        return {
            "width": self._parse_int(video_stream.get("width"), 0),
            "height": self._parse_int(video_stream.get("height"), 0),
            "duration_sec": duration_sec,
            "bitrate_bps": bitrate_bps,
            "has_audio": has_audio,
            "fps": fps,
            "pix_fmt": video_stream.get("pix_fmt", "unknown")
        }

    def build_export_command(self, input_file, output_file, start_sec, end_sec,
                             speed_factor=1.0, remove_audio=False,
                             target_width=None, max_bitrate_kbps=None, crf=28,
                             max_fps=None, source_fps=0.0, force_8bit=False):
        """動態生成 H.265 (MP4) 匯出指令"""
        cmd = [
            self.ffmpeg_path, "-y",
            "-ss", str(start_sec),
            "-to", str(end_sec),
            "-i", input_file
        ]

        video_filters = []
        audio_filters = []

        # 1. 變速處理
        if speed_factor != 1.0:
            video_filters.append(f"setpts={1.0 / speed_factor:.6f}*PTS")
            if not remove_audio:
                # 串聯 atempo，同時相容極慢 (<0.5x) 與高速 (>2.0x)
                s = speed_factor
                while s < 0.5:
                    audio_filters.append("atempo=0.5")
                    s /= 0.5
                while s > 2.0:
                    audio_filters.append("atempo=2.0")
                    s /= 2.0
                audio_filters.append(f"atempo={s:.4f}")

        # 2. 幀率上限（只降不升；置於 scale 前減少多餘影格縮放運算）
        if max_fps:
            effective_fps = source_fps * speed_factor
            if source_fps <= 0.0 or effective_fps > (max_fps + 0.1):
                video_filters.append(f"fps={max_fps}")

        # 3. 解析度縮放（高度 -2 自動對齊偶數以符合 H.265 規範）
        if target_width:
            video_filters.append(f"scale={target_width}:-2")

        # 4. 組合濾鏡與串流映射（明確指定主視訊/音訊軌，避免誤抓附屬資料軌）
        filter_str = ""
        if video_filters:
            filter_str += f"[0:v:0]{','.join(video_filters)}[v];"
        if audio_filters:
            filter_str += f"[0:a:0]{','.join(audio_filters)}[a];"

        if filter_str:
            filter_str = filter_str.rstrip(";")
            cmd.extend(["-filter_complex", filter_str])
            cmd.extend(["-map", "[v]" if video_filters else "0:v:0"])
            if not remove_audio:
                cmd.extend(["-map", "[a]" if audio_filters else "0:a:0?"])
        else:
            cmd.extend(["-map", "0:v:0"])
            if not remove_audio:
                cmd.extend(["-map", "0:a:0?"])

        # 5. 音軌編碼
        if remove_audio:
            cmd.append("-an")
        else:
            cmd.extend(["-c:a", "aac"])

        # 6. 影像編碼（CPU libx265 + hvc1 標籤以相容 Apple/跨平台播放器）
        cmd.extend([
            "-c:v", "libx265",
            "-crf", str(crf),
            "-tag:v", "hvc1"
        ])

        # 7. 色彩相容性（將 10-bit 轉為 8-bit yuv420p）
        if force_8bit:
            cmd.extend(["-pix_fmt", "yuv420p"])

        # 8. 智慧碼率上限（bufsize 設為 4 倍以吸收運動相機高動態波動）
        if max_bitrate_kbps:
            cmd.extend([
                "-maxrate", f"{max_bitrate_kbps}k",
                "-bufsize", f"{max_bitrate_kbps * 4}k"
            ])

        # 9. 將 MP4 moov 索引移至檔頭，支援網頁與通訊軟體快速起播
        cmd.extend(["-movflags", "+faststart"])

        cmd.append(output_file)
        return cmd

    def build_gif_export_command(self, input_file, output_file, start_sec, end_sec,
                                 speed_factor=1.0, target_width=480, fps=15):
        """動態生成高畫質 GIF 匯出指令（使用全域調色盤 palettegen）"""
        cmd = [
            self.ffmpeg_path, "-y",
            "-ss", str(start_sec),
            "-to", str(end_sec),
            "-i", input_file
        ]

        filters = []
        if speed_factor != 1.0:
            filters.append(f"setpts={1.0 / speed_factor:.6f}*PTS")

        filters.append(f"fps={fps}")

        if target_width:
            filters.append(f"scale={target_width}:-2:flags=lanczos")

        filter_str = ",".join(filters)
        complex_filter = f"[0:v:0]{filter_str},split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"

        cmd.extend(["-filter_complex", complex_filter, output_file])
        return cmd


if __name__ == "__main__":
    processor = MediaProcessor()
    test_file = "input.mp4"

    if not os.path.exists(test_file):
        print(f"找不到測試檔 {test_file}，略過獨立測試。")
        sys.exit(0)

    info = processor.get_media_info(test_file)
    print("媒體資訊:", json.dumps(info, indent=2, ensure_ascii=False))

    cmd = processor.build_export_command(
        input_file=test_file,
        output_file="output_p1_test.mp4",
        start_sec=0.0,
        end_sec=min(5.0, info["duration_sec"] or 5.0),
        speed_factor=2.0,
        remove_audio=not info["has_audio"],
        target_width=1920,
        max_bitrate_kbps=int(info["bitrate_bps"] / 1000) * 2,
        crf=23,
        max_fps=60,
        source_fps=info["fps"],
        force_8bit=True
    )
    print("\n生成指令:")
    print(" ".join(cmd))