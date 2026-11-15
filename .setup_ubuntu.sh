#!/bin/bash

# 當發生錯誤時立即停止腳本
set -e

echo "========================================"
echo "  FastCut - Ubuntu 開發環境自動設定腳本"
echo "========================================"

# 1. 安裝系統級別依賴 (VLC 核心必須依賴系統 GUI 函式庫)
echo -e "\n[1/3] 檢查並安裝系統依賴 (需要 sudo 權限)..."
sudo apt update
sudo apt install -y vlc libvlc-dev python3-venv python3-pip wget xz-utils

# 2. 自動下載與配置 FFmpeg Linux 靜態編譯版
echo -e "\n[2/3] 檢查 FFmpeg 獨立執行檔..."
if [ ! -f "./ffmpeg" ] || [ ! -f "./ffprobe" ]; then
    echo ">> 尚未找到獨立版 FFmpeg，正在從 John Van Sickle 下載最新穩定靜態版..."

    # 下載 amd64 架構的最新 release 版本
    wget -q --show-progress https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -O ffmpeg_static.tar.xz

    echo ">> 解壓縮並提取 ffmpeg 與 ffprobe..."
    # 利用 wildcards 只抽出我們需要的兩個二進位檔案，忽略說明文件
    tar -xf ffmpeg_static.tar.xz --strip-components=1 --wildcards '*/ffmpeg' '*/ffprobe'

    # 清理暫存檔並賦予執行權限
    rm ffmpeg_static.tar.xz
    chmod +x ffmpeg ffprobe
    echo ">> FFmpeg 獨立版準備完成！"
else
    echo ">> 已偵測到專案目錄下的 ffmpeg 與 ffprobe，跳過下載。"
fi

# 3. 建立 Python 虛擬環境與安裝套件
echo -e "\n[3/3] 設定 Python 虛擬環境 (venv)..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo ">> 已建立 venv 資料夾"
fi

# 啟動虛擬環境 (注意：在 shell script 中需使用 source)
source venv/bin/activate

echo ">> 升級 pip 並安裝 Python 依賴..."
pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo ">> 警告: 找不到 requirements.txt，將手動安裝核心套件..."
    pip install PySide6 python-vlc
    pip freeze > requirements.txt
fi

echo "========================================"
echo "  環境設定成功！"
echo "========================================"
echo -e "請在終端機輸入以下指令啟動軟體：\n"
echo "  source venv/bin/activate"
echo "  python main_ui.py"
echo "========================================"