#!/usr/bin/env bash
# Build FFmpeg ${FFMPEG_VERSION} into ${FFMPEG_PREFIX} (default /ffmpeg_build).
# Used by docker/base/Dockerfile.python-wheels ffmpeg-vlm wheel stages (av + opencv-python-headless).
set -euo pipefail

FFMPEG_VERSION="${FFMPEG_VERSION:-8.1.2}"
FFMPEG_PREFIX="${FFMPEG_PREFIX:-/ffmpeg_build}"
JOBS="${JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"

cleanup_work() {
    cd /
    rm -rf "${1:?}"
}

if [[ -f "${FFMPEG_PREFIX}/lib/pkgconfig/libavcodec.pc" ]]; then
    echo "Using cached FFmpeg at ${FFMPEG_PREFIX}"
    pkg-config --modversion libavcodec
    exit 0
fi

mkdir -p "${FFMPEG_PREFIX}"

# libvpx (opencv-python manylinux ffmpeg configure enables --enable-libvpx)
VPX_VERSION="${VPX_VERSION:-v1.15.2}"
if [[ ! -f "${FFMPEG_PREFIX}/lib/pkgconfig/vpx.pc" ]]; then
    work="$(mktemp -d)"
    git clone --depth 1 -b "${VPX_VERSION}" https://chromium.googlesource.com/webm/libvpx.git "${work}/libvpx"
    cd "${work}/libvpx"
    vpx_args=(
        --prefix="${FFMPEG_PREFIX}"
        --disable-examples
        --disable-unit-tests
        --enable-vp9-highbitdepth
        --enable-pic
        --enable-shared
    )
    if [[ "$(uname -m)" == "x86_64" ]]; then
        vpx_args+=(--as=yasm)
    fi
    ./configure "${vpx_args[@]}"
    make -j"${JOBS}"
    make install
    cleanup_work "${work}"
fi

# x264 (PyAV build-deps enables --enable-libx264)
if [[ ! -f "${FFMPEG_PREFIX}/lib/pkgconfig/x264.pc" ]]; then
    work="$(mktemp -d)"
    git clone --depth 1 https://code.videolan.org/videolan/x264.git "${work}/x264"
    cd "${work}/x264"
    ./configure --prefix="${FFMPEG_PREFIX}" --enable-shared --enable-pic
    make -j"${JOBS}"
    make install
    cleanup_work "${work}"
fi

work="$(mktemp -d)"
curl -fsSL "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.gz" -o "${work}/ffmpeg.tar.gz"
tar -xf "${work}/ffmpeg.tar.gz" -C "${work}"
cd "${work}/ffmpeg-${FFMPEG_VERSION}"

PKG_CONFIG_PATH="${FFMPEG_PREFIX}/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export PKG_CONFIG_PATH

./configure \
    --prefix="${FFMPEG_PREFIX}" \
    --extra-cflags="-I${FFMPEG_PREFIX}/include" \
    --extra-ldflags="-L${FFMPEG_PREFIX}/lib" \
    --disable-doc \
    --disable-static \
    --enable-shared \
    --enable-pic \
    --enable-gpl \
    --enable-version3 \
    --enable-libvpx \
    --enable-libx264

make -j"${JOBS}"
make install

echo "/ffmpeg_build/lib/" >> /etc/ld.so.conf.d/ffmpeg-vendor.conf
ldconfig

"${FFMPEG_PREFIX}/bin/ffmpeg" -version | head -1
cleanup_work "${work}"
