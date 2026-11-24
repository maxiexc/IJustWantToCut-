# IJustWantToCut (只是剪片)

一個專注於**剪輯**與**變速**剪輯軟體，讓大家可以簡單的把影片簡成短片或動圖。

##  主要功能

- **預覽與剪輯**：內建 VLC 引擎，支援 H.265/4K 原始素材流暢預覽，並可設定毫秒 (ms) 級別的起訖點。
- **無段變速**：支援 0.1x 到 5.0x 的播放速度調整。
- **輸出解析度設定**：可選擇常見比例或手動輸入自訂解析度 (如 2704)，系統將自動維持長寬比。
- **輸出畫質控制**：採用 CRF 品質標準，並**自動鎖定原始素材碼率天花板**，確保高動態畫面不產生無謂的檔案體積膨脹。
- **輸出**：支援匯出為高畫質 MP4 (H.265) 或經過全域調色盤 (palettegen) 處理的高畫質 GIF 動圖。
- **支援去除音軌**。
- **跨平台支援**：相容於 Windows 10/11 與 Ubuntu 22.04 ~ 26.04。

##  系統需求與相依套件

本專案使用 Python 開發，依賴以下模組與系統工具：

- **Python 3.8+**
- **前端介面**: `PySide6`
- **播放引擎**: `python-vlc`, 系統須安裝官方 [VLC Media Player](https://www.videolan.org/) (64-bit)
- **處理引擎**: [FFmpeg](https://ffmpeg.org/) (需包含 `libx265` 編碼器)

## 安裝與執行

### Windows 執行檔安裝（Windows 10 / 11 64-bit，推薦）
從 GitHub Releases 下載 Windows 發行檔（已內嵌 FFmpeg 與 libVLC，**不需預先安裝 Python、VLC 或 FFmpeg**）：
- **安裝版（推薦）**：下載 `IJustWantToCut-<version>-win64-setup.exe` 執行安裝精靈即可建立開始選單與桌面捷徑。
- **免安裝可攜版**：下載 `IJustWantToCut-<version>-win64-portable.zip`，解壓縮後直接執行 `IJustWantToCut\IJustWantToCut.exe`。

> 首次執行未簽章之執行檔時，Windows SmartScreen 可能會跳出提示，點選「其他資訊 → 仍要執行」即可。

### Ubuntu `.deb` 安裝包（Ubuntu 22.04 ~ 26.04，推薦）
若已從 GitHub Releases 取得 `.deb` 安裝包（或透過下方 Docker 腳本自行建置），可直接使用 `apt` 安裝，系統將自動補齊 `libvlc5`、`ffmpeg` 與 Qt6 XCB 執行期依賴：
```bash
sudo apt update
sudo apt install ./ijustwanttocut_<version>_amd64.deb
```
安裝完成後，可從桌面應用程式選單開啟 **IJustWantToCut**，或在終端機執行：
```bash
ijustwanttocut
```
（亦可使用 `IJustWantToCut` 指令名稱啟動，或加上 `--version` 查看版本。）

### 從原始碼打包（Windows / Ubuntu / GitHub Actions CI/CD）

#### 方式一：GitHub Actions 跨平台自動建置與發佈（推薦）
整合式跨平台 Workflow 位於 `.github/workflows/release.yml`：
- 推送至 `main` / `master`、建立 Pull Request 或手動觸發 `workflow_dispatch` 時，會同步執行：
  1. **Ubuntu `.deb`**：於 Ubuntu 22.04 容器編譯，並在 Ubuntu `22.04` / `24.04` / `26.04` 容器驗證安裝、`ldd` 連結與 `xvfb-run` GUI 啟動測試。
  2. **Windows 安裝程式 & 可攜包**：於 `windows-2025`（Python 3.11 + PyInstaller + Inno Setup 6）打包內嵌 FFmpeg 與 libVLC 的 `setup.exe` 與 `portable.zip`，並自動實測可攜版啟動、靜默安裝、安裝後啟動與靜默解除安裝。
- 推送 `v*` 標籤（例如 `git tag v0.1.0 && git push origin v0.1.0`）且雙平台驗證全數通過後，自動建立單一 GitHub Release 並附上所有平台產物與 `.sha256` 校驗檔。

#### 方式二：於本機建置 Windows 發行檔
需準備 **Python 3.10 或 3.11 (64-bit)** 與 **Inno Setup 6**：
```powershell
pip install -r packaging\windows\requirements-build.txt
.\packaging\windows\build_windows.ps1
# 驗證產出的 Portable Zip 與 Setup 安裝檔
.\packaging\windows\verify_windows.ps1
```

#### 方式三：透過 Docker 於本機建置 Ubuntu `.deb`
專案內已提供基於 Ubuntu 22.04 的多階段 Dockerfile，可在 Windows / Linux / macOS 直接產出相容於 Ubuntu 22.04 ~ 26.04 的 `.deb`（輸出至 `dist/`）：
- **Windows (PowerShell)**：
  ```powershell
  # 僅建置 .deb 與 .sha256
  .\packaging\ubuntu\build_docker.ps1

  # 建置並依序在 Ubuntu 22.04、24.04、26.04 容器中安裝與執行煙霧測試
  .\packaging\ubuntu\build_docker.ps1 -Verify
  ```
- **Linux / macOS (Bash)**：
  ```bash
  ./packaging/ubuntu/build_docker.sh --verify
  ```

### Windows 系統（從原始碼執行）
1. 請先安裝 [VLC Media Player (Windows 64-bit)](https://www.videolan.org/)。
2. 下載 [FFmpeg Windows 靜態編譯版](https://www.gyan.dev/ffmpeg/builds/) (推薦 release-essentials)。解壓縮後，將 `bin/` 目錄下的 `ffmpeg.exe` 與 `ffprobe.exe` 放置於本專案根目錄。
3. 開啟命令提示字元或 PowerShell：
   ```bash
   git clone https://github.com/maxiexc/IJustWantToCut-.git
   cd IJustWantToCut-
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   python main_ui.py
   ```

### Ubuntu (Linux) 系統（開發環境從原始碼執行）
專案內提供了一鍵設定腳本，會自動安裝 VLC 依賴、下載 Linux 專用的 FFmpeg 靜態檔並設定好 Python 虛擬環境。
1. 開啟終端機：
   ```bash
   git clone https://github.com/maxiexc/IJustWantToCut-.git
   cd IJustWantToCut-
   chmod +x setup_ubuntu.sh
   ./setup_ubuntu.sh
   ```
2. 啟動軟體：
   ```bash
   source venv/bin/activate
   python main_ui.py
   ```

## 已知限制與注意事項

- **Ubuntu Wayland 顯示支援**：Ubuntu 22.04+ 預設採用 Wayland 顯示伺服器，但為了讓 VLC 視窗能正確嵌入，程式內強制使用了 X11 (xcb) 模式相容。
- **硬體加速支援**：目前匯出功能採用 `libx265` (CPU 軟解)。若您的設備具備 NVIDIA 或 Intel 獨立顯卡，您可以自行修改 `media_processor.py` 中的參數 (如 `hevc_nvenc` 或 `hevc_qsv`) 以獲得大幅度的匯出速度提升。
- **GIF 檔案大小**：高品質 GIF 原生存在檔案較大的問題。建議在匯出 GIF 時，將「目標寬度」調降 (如 640)，並將 FPS 設為 10-15。

## 授權條款 (License)

本專案原始碼採用 [MIT License](LICENSE) 授權。您可以自由修改、散佈與商業使用。

**外部套件聲明：**

- 本軟體動態連結之 `PySide6` 與 `libvlc` 屬 LGPL 授權。
- 本軟體外部呼叫之 `FFmpeg` 屬 GPL/LGPL 授權。本專案不包含其二進位檔案，使用者須自行下載安裝。這些外部工具之版權歸原作者所有。