# Changelog

本檔案記錄 **IJustWantToCut** 的所有重要變更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本編號採用 [語意化版本 (SemVer)](https://semver.org/lang/zh-TW/)。

> **發版維護流程**：開發期間請將變更寫在 `## [Unreleased]` 底下；準備發佈新版本（例如 `v0.1.0`）時，將 `## [Unreleased]` 下的條目移至新的 `## [0.1.0] - YYYY-MM-DD` 區段並提交，最後推送對應 Git Tag（`git tag v0.1.0 && git push origin v0.1.0`），Release CD 即會自動擷取該區段作為 GitHub Release 說明。

## [Unreleased]

### Added
- 支援 Windows 64-bit 單檔安裝程式（Inno Setup）與免安裝可攜包（Portable Zip），內嵌 FFmpeg 與 libVLC。
- 支援 Ubuntu 22.04 ~ 26.04 `.deb` 安裝包、應用程式圖示與桌面選單整合。
- 導入 CI / CD 分離流程：PR 自動執行靜態與設定檢查，下 `v*` Tag 自動觸發雙平台打包、驗證與 GitHub Release 發佈。
- 打包執行檔於建置期自動注入 Git Tag 版本號，並同步顯示於視窗標題與 `--version`。
- 建立 `CHANGELOG.md` 維護機制與自動擷取工具。

### Fixed
- 修正 GIF 匯出元件屬性名稱錯誤與重複建立解析度下拉選單的問題。
- 改善打包環境下 FFmpeg / FFprobe 與 libVLC 的跨平台路徑解析及視窗關閉時的資源清理。
