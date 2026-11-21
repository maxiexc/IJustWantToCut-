# syntax=docker/dockerfile:1

FROM ubuntu:22.04 AS builder

ARG APP_VERSION=""
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-pip \
    binutils \
    dpkg-dev \
    patchelf \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-sync1 \
    libxcb-xfixes0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    libgl1 \
    libegl1 \
    libdbus-1-3 \
    libfontconfig1 \
    libfreetype6 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/build-venv
ENV PATH="/opt/build-venv/bin:${PATH}"

WORKDIR /src

COPY packaging/ubuntu/requirements-build.txt packaging/ubuntu/requirements-build.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r packaging/ubuntu/requirements-build.txt

COPY version.py main_ui.py media_processor.py ./
COPY packaging ./packaging

RUN sed -i 's/\r$//' packaging/ubuntu/*.sh \
    && APP_VERSION="${APP_VERSION}" bash packaging/ubuntu/build_deb.sh

FROM scratch AS export
COPY --from=builder /src/dist/*.deb /
COPY --from=builder /src/dist/*.sha256 /
