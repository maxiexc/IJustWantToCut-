#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"

APP_VERSION=""
VERIFY=0

while [ $# -gt 0 ]; do
    case "$1" in
        --version)
            APP_VERSION="${2:-}"
            shift 2
            ;;
        --verify)
            VERIFY=1
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--version <ver>] [--verify]"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

mkdir -p "$DIST_DIR"

BUILD_CMD=(
    docker build
    --target export
    --output "type=local,dest=${DIST_DIR}"
    -f "$REPO_ROOT/packaging/ubuntu/Dockerfile"
)

if [ -n "$APP_VERSION" ]; then
    BUILD_CMD+=(--build-arg "APP_VERSION=${APP_VERSION}")
fi

BUILD_CMD+=("$REPO_ROOT")

echo "==> Building Ubuntu .deb via Docker (Ubuntu 22.04 builder)..."
DOCKER_BUILDKIT=1 "${BUILD_CMD[@]}"

echo "==> Build output in ${DIST_DIR}:"
ls -lh "$DIST_DIR"/ijustwanttocut_*.deb*

if [ "$VERIFY" -eq 1 ]; then
    for ubuntu_ver in 22.04 24.04 26.04; do
        echo "==> Verifying .deb inside ubuntu:${ubuntu_ver}..."
        docker run --rm \
            -v "${DIST_DIR}:/pkg:ro" \
            -v "${REPO_ROOT}/packaging/ubuntu/verify_deb.sh:/verify.sh:ro" \
            "ubuntu:${ubuntu_ver}" \
            bash /verify.sh
    done
fi
