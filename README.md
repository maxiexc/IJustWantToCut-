# FastCut 影片剪輯變速工具

FastCut 是一個專為「運動相機 (如 GoPro)」與「空拍機 (如 DJI)」素材所設計的輕量級開源影片編輯工具。本專案捨棄了傳統非線性剪輯軟體繁雜的介面，專注於提供極致簡單的**剪輯**與**變速**功能，並藉由 FFmpeg 強大的底層引擎，實現無損原始細節的高畫質 (H.265) 輸出。

## ✨ 主要功能

- **精準預覽與剪輯**：內建 VLC 引擎，支援 H.265/4K 原始素材流暢預覽，並可設定毫秒 (ms) 級別的起訖點。
- **無極變速**：支援 0.1x 到 5.0x 的播放速度調整。
- **Kdenlive 風格解析度設定**：可選擇常見比例或手動輸入自訂解析度 (如 2704)，系統將自動維持長寬比。
- **智慧畫質控制**：採用 CRF 品質標準，並**自動鎖定原始素材碼率天花板**，確保高動態畫面不產生無謂的檔案體積膨脹。
- **多格式輸出**：支援匯出為高畫質 MP4 (H.265) 或經過全域調色盤 (palettegen) 處理的高畫質 GIF 動圖。
- **支援去除音軌**。
- **跨平台支援**：相容於 Windows 10/11 與 Ubuntu 22.04+。

## 📦 系統需求與相依套件

本專案使用 Python 開發，依賴以下模組與系統工具：

- **Python 3.8+**
- **前端介面**: `PySide6`
- **播放引擎**: `python-vlc`, 系統須安裝官方 [VLC Media Player](https://www.videolan.org/) (64-bit)
- **處理引擎**: [FFmpeg](https://ffmpeg.org/) (需包含 `libx265` 編碼器)

## 🚀 快速開始 (安裝與執行)

### Windows 系統
1. 請先安裝 [VLC Media Player (Windows 64-bit)](https://www.videolan.org/)。
2. 下載 [FFmpeg Windows 靜態編譯版](https://www.gyan.dev/ffmpeg/builds/) (推薦 release-essentials)。解壓縮後，將 `bin/` 目錄下的 `ffmpeg.exe` 與 `ffprobe.exe` 放置於本專案根目錄。
3. 開啟命令提示字元或 PowerShell：
   ```bash
   git clone https://github.com/yourusername/FastCut.git
   cd FastCut
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   python main_ui.py
   ```

### Ubuntu (Linux) 系統
專案內提供了一鍵設定腳本，會自動安裝 VLC 依賴、下載 Linux 專用的 FFmpeg 靜態檔並設定好 Python 虛擬環境。
1. 開啟終端機：
   ```bash
   git clone https://github.com/yourusername/FastCut.git
   cd FastCut
   chmod +x setup_ubuntu.sh
   ./setup_ubuntu.sh
   ```
2. 啟動軟體：
   ```bash
   source venv/bin/activate
   python main_ui.py
   ```

## ⚠️ 已知限制與注意事項

- **Ubuntu Wayland 顯示支援**：Ubuntu 22.04+ 預設採用 Wayland 顯示伺服器，但為了讓 VLC 視窗能正確嵌入，程式內強制使用了 X11 (xcb) 模式相容。
- **硬體加速支援**：目前匯出功能採用 `libx265` (CPU 軟解)。若您的設備具備 NVIDIA 或 Intel 獨立顯卡，您可以自行修改 `media_processor.py` 中的參數 (如 `hevc_nvenc` 或 `hevc_qsv`) 以獲得大幅度的匯出速度提升。
- **GIF 檔案大小**：高品質 GIF 原生存在檔案較大的問題。建議在匯出 GIF 時，將「目標寬度」調降 (如 640)，並將 FPS 設為 10-15。

## 📄 授權條款 (License)

本專案原始碼採用 [MIT License](LICENSE) 授權。您可以自由修改、散佈與商業使用。

**外部套件聲明：**
- 本軟體動態連結之 `PySide6` 與 `libvlc` 屬 LGPL 授權。
- 本軟體外部呼叫之 `FFmpeg` 屬 GPL/LGPL 授權。本專案不包含其二進位檔案，使用者須自行下載安裝。這些外部工具之版權歸原作者所有。