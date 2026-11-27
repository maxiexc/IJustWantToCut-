#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

DEB_PATH="${1:-}"
if [ -z "$DEB_PATH" ]; then
    for candidate in /pkg/ijustwanttocut_*_amd64.deb; do
        if [ -f "$candidate" ]; then
            DEB_PATH="$candidate"
            break
        fi
    done
fi

if [ -z "$DEB_PATH" ] || [ ! -f "$DEB_PATH" ]; then
    echo "ERROR: .deb package not found (checked: '${DEB_PATH:-/pkg/ijustwanttocut_*_amd64.deb}')" >&2
    exit 1
fi

if [ "${DEB_PATH#/}" = "$DEB_PATH" ]; then
    DEB_PATH="$(pwd)/$DEB_PATH"
fi

echo "==> Verifying package: $DEB_PATH"
. /etc/os-release
echo "==> Target OS: ${PRETTY_NAME:-unknown}"

PKG_VERSION="$(dpkg-deb -f "$DEB_PATH" Version)"
echo "==> Package Version metadata: $PKG_VERSION"
if [ -n "${EXPECTED_VERSION:-}" ]; then
    EXP_CLEAN="${EXPECTED_VERSION#v}"
    if [ "$PKG_VERSION" != "$EXP_CLEAN" ]; then
        echo "ERROR: .deb version ($PKG_VERSION) does not match EXPECTED_VERSION ($EXP_CLEAN)" >&2
        exit 1
    fi
fi

apt-get update
apt-get install -y --no-install-recommends "$DEB_PATH" xvfb xauth

echo "==> Checking CLI --version..."
VER_OUT_LOWER="$(ijustwanttocut --version)"
VER_OUT_UPPER="$(IJustWantToCut --version)"
EXPECTED_CLI="IJustWantToCut ${PKG_VERSION}"
echo "ijustwanttocut --version => $VER_OUT_LOWER"
echo "IJustWantToCut --version => $VER_OUT_UPPER"

if [ "$VER_OUT_LOWER" != "$EXPECTED_CLI" ]; then
    echo "ERROR: Unexpected --version output: expected '$EXPECTED_CLI', got '$VER_OUT_LOWER'" >&2
    exit 1
fi

if [ "$VER_OUT_LOWER" != "$VER_OUT_UPPER" ]; then
    echo "ERROR: Version mismatch between ijustwanttocut and IJustWantToCut" >&2
    exit 1
fi

echo "==> Checking shared library linkage (ldd)..."
QXCB_PATH="/opt/ijustwanttocut/_internal/PySide6/Qt/plugins/platforms/libqxcb.so"
if [ ! -f "$QXCB_PATH" ]; then
    QXCB_PATH="$(find /opt/ijustwanttocut/_internal -name 'libqxcb.so' | head -n 1 || true)"
fi

if [ -z "$QXCB_PATH" ] || [ ! -f "$QXCB_PATH" ]; then
    echo "ERROR: Could not locate libqxcb.so in /opt/ijustwanttocut/_internal" >&2
    exit 1
fi

CHECK_LD_PATH="/opt/ijustwanttocut/_internal:/opt/ijustwanttocut/_internal/PySide6/Qt/lib:${LD_LIBRARY_PATH:-}"
for target_bin in /opt/ijustwanttocut/IJustWantToCut "$QXCB_PATH"; do
    echo "Checking ldd on $target_bin"
    ldd_out="$(LD_LIBRARY_PATH="$CHECK_LD_PATH" ldd "$target_bin")"
    if echo "$ldd_out" | grep -q "not found"; then
        echo "ERROR: Missing shared libraries for $target_bin:" >&2
        echo "$ldd_out" | grep "not found" >&2
        exit 1
    fi
done

echo "==> Checking FFmpeg libx265 encoder..."
FFMPEG_ENCODERS="$(ffmpeg -hide_banner -encoders 2>/dev/null || true)"
if ! printf '%s\n' "$FFMPEG_ENCODERS" | grep -q "libx265"; then
    echo "ERROR: System ffmpeg does not report libx265 encoder!" >&2
    exit 1
fi

echo "==> Running GUI smoke test under Xvfb..."
SMOKE_OUT="$(xvfb-run -a -s "-screen 0 1280x720x24" ijustwanttocut --smoke-test)"
echo "$SMOKE_OUT"
if ! echo "$SMOKE_OUT" | grep -q "\[SMOKE-TEST\] OK"; then
    echo "ERROR: Smoke test did not emit [SMOKE-TEST] OK" >&2
    exit 1
fi

echo "==> Testing clean package removal..."
apt-get remove -y ijustwanttocut
if [ -e /opt/ijustwanttocut ] || [ -e /usr/bin/ijustwanttocut ] || [ -L /usr/bin/IJustWantToCut ]; then
    echo "ERROR: Package removal left files behind!" >&2
    exit 1
fi

echo "==> Verification PASSED on ${PRETTY_NAME:-Ubuntu}!"
