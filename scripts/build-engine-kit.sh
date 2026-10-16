#!/bin/bash
# Builds the "engine kit": everything MacX adds on top of a stock Wine build, compiled from source.
#
#   build/engine-kit/
#     unix/winemac.so      Wine 11.18 Mac driver + CrossOver-layout macdrv_functions table (DXMT and D3DMetal)
#     unix/ntdll-cx.so     Wine 11.18 ntdll in "CrossOver mode" (GSBASE stays on the macOS TSD) - D3DMetal engine
#     unix/d3d12.so        unix side of the d3d12 wrapper (one Wine unix call)
#     windows/ntdlx.dll    forwards __wine_unix_call for Apple's D3DMetal DLLs
#     windows/d3d12.dll    d3d12 wrapper: D3D12GetInterface, d3d12core residency, queue-method thunks
#     windows/cefwrap.exe  Chromium helper wrapper (Steam / Rockstar launcher windows)
#     tools/*.py           PE patchers used when assembling the D3DMetal engine
#
# Needs: Xcode command line tools, Homebrew bison, and zig (`pip3 install ziglang`). End users don't build this;
# release builds of the app ship the kit.
set -euo pipefail
WINE_VERSION="${WINE_VERSION:-11.18}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
B="$REPO/build"; OUT="$B/engine-kit"; SRC="$B/wine-$WINE_VERSION"; OBJ="$B/wine-obj-$WINE_VERSION"
ZIG=(python3 -m ziglang cc -target x86_64-windows-gnu)
mkdir -p "$OUT"/{unix,windows,tools} "$B"

# --- Wine unix libraries (patched) -----------------------------------------------------------------
if [ ! -d "$SRC" ]; then
  curl -fL -o "$B/wine-$WINE_VERSION.tar.xz" "https://dl.winehq.org/wine/source/${WINE_VERSION%%.*}.x/wine-$WINE_VERSION.tar.xz"
  tar -C "$B" -xf "$B/wine-$WINE_VERSION.tar.xz"
fi

build_unix() {   # $1 = output name, rest = patches
  local name="$1"; shift
  local tree="$B/tree-$name"; rm -rf "$tree"; cp -cR "$SRC" "$tree"
  for p in "$@"; do patch -d "$tree" -p1 -s < "$REPO/engine/wine-patches/$p"; done
  local obj="$OBJ-$name"; mkdir -p "$obj"
  arch -x86_64 /bin/bash -c "cd '$obj' && export PATH=/opt/homebrew/opt/bison/bin:\$PATH CC='clang -arch x86_64' OBJC='clang -arch x86_64' CFLAGS=-O2 OBJCFLAGS=-O2
    [ -f Makefile ] || '$tree/configure' --enable-archs=none --without-x --without-freetype --without-gnutls \
      --without-gstreamer --without-sdl --without-cups --without-sane --without-usb --without-pcap --without-krb5 \
      --without-netapi --without-gphoto --without-v4l2 --without-pulse --without-oss --without-alsa --without-capi \
      --without-dbus --without-udev --without-wayland --without-ffmpeg --without-opencl --without-pcsclite \
      --without-unwind --without-inotify --without-gettext >/dev/null
    make -j\$(sysctl -n hw.ncpu) dlls/winemac.drv/winemac.so dlls/ntdll/ntdll.so >/dev/null"
  echo "$obj"
}
obj=$(build_unix patched 0001-winemac-macdrv-functions-window.patch 0002-ntdll-macos-crossover-gsbase-mode.patch)
cp "$obj/dlls/winemac.drv/winemac.so" "$OUT/unix/winemac.so"
cp "$obj/dlls/ntdll/ntdll.so" "$OUT/unix/ntdll-cx.so"
nm -gU "$OUT/unix/winemac.so" | grep -q _macdrv_functions || { echo "winemac.so: macdrv_functions missing"; exit 1; }

# --- bridge ----------------------------------------------------------------------------------------
E="$REPO/engine/bridge"
"${ZIG[@]}" -shared -O2 -o "$OUT/windows/ntdlx.dll" "$E/ntdlx.c" 2>/dev/null
python3 -I "$E/patch_imports.py" --builtin "$OUT/windows/ntdlx.dll" >/dev/null
"${ZIG[@]}" -shared -O2 -o "$OUT/windows/d3d12.dll" "$E/d3d12wrap.c" "$E/d3d12wrap.def" -ldxguid -luuid 2>/dev/null
python3 -I "$E/patch_imports.py" --builtin "$OUT/windows/d3d12.dll" >/dev/null
clang -arch x86_64 -O2 -shared -fvisibility=hidden -o "$OUT/unix/d3d12.so" "$E/d3d12_unix.c"
"${ZIG[@]}" -municode -O2 -o "$OUT/windows/cefwrap.exe" "$REPO/engine/wrap/wrap.c" -Wl,--subsystem,windows 2>/dev/null
cp "$E"/patch_imports.py "$E"/patch_peb.py "$E"/patch_tls.py "$OUT/tools/"
echo "$WINE_VERSION" > "$OUT/WINE_VERSION"

echo "Engine kit for Wine $WINE_VERSION:"; (cd "$OUT" && find . -type f | sort | xargs shasum | sed 's/^/  /')
