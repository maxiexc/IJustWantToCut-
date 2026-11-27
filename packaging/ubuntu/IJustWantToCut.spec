# -*- mode: python ; coding: utf-8 -*-
import os

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

# Exclude bulky Qt6 and standard library modules unused by IJustWantToCut.
# Keep PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets, PySide6.QtDBus, PySide6.QtOpenGL.
EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtLocation",
    "PySide6.QtNetwork",
    "PySide6.QtNetworkAuth",
    "PySide6.QtNfc",
    "PySide6.QtPdf",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtXml",
    "tkinter",
    "unittest",
    "pydoc",
]

# Host system libraries that MUST NOT be bundled from Ubuntu 22.04 so the
# executable dynamically resolves compatible native libraries on 22.04 ~ 26.04.
HOST_LIB_PREFIXES = (
    "libstdc++.so",
    "libgcc_s.so",
    "libglib-2.0.so",
    "libgobject-2.0.so",
    "libgthread-2.0.so",
    "libgio-2.0.so",
    "libgmodule-2.0.so",
    "libfontconfig.so",
    "libfreetype.so",
    "libharfbuzz.so",
    "libexpat.so",
    "libdbus-1.so",
    "libsystemd.so",
    "libGL.so",
    "libGLX.so",
    "libGLdispatch.so",
    "libEGL.so",
    "libOpenGL.so",
    "libdrm",
    "libgbm",
    "libvulkan",
    "libX11",
    "libxcb",
    "libxkbcommon",
    "libXext",
    "libXrender",
    "libXfixes",
    "libXi",
    "libICE",
    "libSM",
    "libvlc",
    "libvlccore",
)

a = Analysis(
    [os.path.join(REPO_ROOT, "main_ui.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "vlc",
        "media_processor",
        "version",
        "_build_meta",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

a.binaries = [
    entry for entry in a.binaries
    if not os.path.basename(entry[0]).startswith(HOST_LIB_PREFIXES)
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="IJustWantToCut",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="IJustWantToCut",
)
