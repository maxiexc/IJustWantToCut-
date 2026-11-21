#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

if [ -z "${APP_VERSION:-}" ]; then
    APP_VERSION="$(python3 -c 'import version; print(version.APP_VERSION)')"
fi
APP_VERSION="${APP_VERSION#v}"

if [ -z "$APP_VERSION" ]; then
    echo "ERROR: APP_VERSION could not be resolved." >&2
    exit 1
fi

if command -v dpkg >/dev/null 2>&1; then
    dpkg --validate-version "$APP_VERSION"
fi

echo "==> Building IJustWantToCut (${APP_VERSION}) with PyInstaller..."
rm -rf build/pyinstaller dist/IJustWantToCut build/deb_root
pyinstaller --noconfirm --clean \
    --workpath build/pyinstaller \
    --distpath dist \
    packaging/ubuntu/IJustWantToCut.spec

BUNDLE_DIR="$REPO_ROOT/dist/IJustWantToCut"
BIN_PATH="$BUNDLE_DIR/IJustWantToCut"

if [ ! -x "$BIN_PATH" ]; then
    echo "ERROR: Expected executable not found at $BIN_PATH" >&2
    exit 1
fi

QXCB_FOUND="$(find "$BUNDLE_DIR/_internal" -name 'libqxcb.so' -print -quit)"
if [ -z "$QXCB_FOUND" ]; then
    echo "ERROR: Qt xcb plugin (libqxcb.so) missing from bundle!" >&2
    exit 1
fi
echo "==> Found Qt xcb plugin: $QXCB_FOUND"

if [ -z "$(find "$BUNDLE_DIR/_internal" -name 'libpython3*.so*' -print -quit)" ]; then
    echo "ERROR: libpython shared library missing from bundle!" >&2
    exit 1
fi

leaked_libs="$(find "$BUNDLE_DIR/_internal" -type f \( \
    -name 'libstdc++.so*' -o \
    -name 'libgcc_s.so*' -o \
    -name 'libGL.so*' -o \
    -name 'libGLX.so*' -o \
    -name 'libEGL.so*' -o \
    -name 'libglib-2.0.so*' -o \
    -name 'libxcb*.so*' -o \
    -name 'libvlc*.so*' \
\) || true)"

if [ -n "$leaked_libs" ]; then
    echo "ERROR: Banned host libraries leaked into bundle:" >&2
    echo "$leaked_libs" >&2
    exit 1
fi

echo "==> Staging Debian package directory..."
DEB_ROOT="$REPO_ROOT/build/deb_root"
mkdir -p \
    "$DEB_ROOT/opt/ijustwanttocut" \
    "$DEB_ROOT/usr/bin" \
    "$DEB_ROOT/usr/share/applications" \
    "$DEB_ROOT/usr/share/icons/hicolor/scalable/apps" \
    "$DEB_ROOT/usr/share/doc/ijustwanttocut"

cp -a "$BUNDLE_DIR/." "$DEB_ROOT/opt/ijustwanttocut/"

cat > "$DEB_ROOT/usr/bin/ijustwanttocut" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
exec /opt/ijustwanttocut/IJustWantToCut "$@"
EOF
chmod 0755 "$DEB_ROOT/usr/bin/ijustwanttocut"
ln -s ijustwanttocut "$DEB_ROOT/usr/bin/IJustWantToCut"

cat > "$DEB_ROOT/usr/share/applications/ijustwanttocut.desktop" <<'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=IJustWantToCut
GenericName=Video Cutter and Speed Editor
Comment=Simple video cutter and speed editor (MP4/H.265 & GIF)
Exec=/usr/bin/ijustwanttocut %f
Icon=ijustwanttocut
Terminal=false
Categories=AudioVideo;Video;AudioVideoEditing;
MimeType=video/mp4;video/quicktime;video/x-msvideo;video/x-matroska;
StartupWMClass=ijustwanttocut
EOF
chmod 0644 "$DEB_ROOT/usr/share/applications/ijustwanttocut.desktop"

install -m 0644 \
    "$REPO_ROOT/packaging/assets/ijustwanttocut.svg" \
    "$DEB_ROOT/usr/share/icons/hicolor/scalable/apps/ijustwanttocut.svg"

cat > "$DEB_ROOT/usr/share/doc/ijustwanttocut/copyright" <<'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: IJustWantToCut
Source: https://github.com/maxiexc/IJustWantToCut-

Files: *
Copyright: IJustWantToCut Contributors
License: MIT
 Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:
 .
 The above copyright notice and this permission notice shall be included in all
 copies or substantial portions of the Software.
 .
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 SOFTWARE.

Files: /opt/ijustwanttocut/_internal/PySide6/* /opt/ijustwanttocut/_internal/shiboken6/*
Copyright: The Qt Company Ltd.
License: LGPL-3.0
 This package bundles PySide6 and shiboken6 runtime libraries under the terms
 of the GNU Lesser General Public License v3 (LGPL-3.0).
 See /usr/share/common-licenses/LGPL-3 on Debian/Ubuntu systems.

Comment: System Runtime Tools
 At runtime on Debian/Ubuntu systems, IJustWantToCut dynamically loads system
 libvlc (LGPL-2.1+) and invokes system ffmpeg/ffprobe subprocesses (GPL/LGPL)
 provided via APT package dependencies.
EOF
chmod 0644 "$DEB_ROOT/usr/share/doc/ijustwanttocut/copyright"

INSTALLED_SIZE="$(du -sk "$DEB_ROOT" | awk '{print $1}')"

mkdir -p "$DEB_ROOT/DEBIAN"
cat > "$DEB_ROOT/DEBIAN/control" <<EOF
Package: ijustwanttocut
Version: ${APP_VERSION}
Section: video
Priority: optional
Architecture: amd64
Maintainer: IJustWantToCut Maintainers <https://github.com/maxiexc/IJustWantToCut->
Homepage: https://github.com/maxiexc/IJustWantToCut-
Installed-Size: ${INSTALLED_SIZE}
Depends: libc6 (>= 2.35), libstdc++6, libgcc-s1, libvlc5, vlc-plugin-base, vlc-plugin-video-output, ffmpeg, libx11-6, libx11-xcb1, libxcb1, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-sync1, libxcb-xfixes0, libxcb-xinerama0, libxcb-xkb1, libxkbcommon0, libxkbcommon-x11-0, libxext6, libxrender1, libxfixes3, libxi6, libice6, libsm6, libgl1, libegl1, libdbus-1-3, libfontconfig1, libfreetype6, libexpat1, libharfbuzz0b, libglib2.0-0t64 | libglib2.0-0
Recommends: vlc-plugin-pipewire | vlc-plugin-base
Description: Simple video cutter and speed editor
 IJustWantToCut is a lightweight desktop GUI tool for trimming videos,
 adjusting playback speed (0.05x to 5.0x), and exporting to H.265 MP4
 or palette-optimized GIF using VLC preview and FFmpeg.
EOF
chmod 0644 "$DEB_ROOT/DEBIAN/control"

cat > "$DEB_ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
EOF
chmod 0755 "$DEB_ROOT/DEBIAN/postinst"

cat > "$DEB_ROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
EOF
chmod 0755 "$DEB_ROOT/DEBIAN/postrm"

DEB_NAME="ijustwanttocut_${APP_VERSION}_amd64.deb"
DEB_OUTPUT="$REPO_ROOT/dist/${DEB_NAME}"
echo "==> Building ${DEB_OUTPUT}..."
dpkg-deb --root-owner-group -Zxz --build "$DEB_ROOT" "$DEB_OUTPUT"

(cd "$REPO_ROOT/dist" && sha256sum "$DEB_NAME" > "${DEB_NAME}.sha256")
echo "==> Done: $DEB_OUTPUT"
ls -lh "$DEB_OUTPUT" "${DEB_OUTPUT}.sha256"
