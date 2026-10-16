#!/bin/bash
# Builds the test programs and six stand-in "games" in every form MacX should accept, so the whole
# drop -> install/unpack -> detect -> run-on-Metal path can be tested without real game files.
#
#   build/fixtures/Metal Racer (repack)/   setup.exe + data-1..3.bin installer, DirectX 12 game (64-bit)
#   build/fixtures/Retro Classic.iso       disc image with autorun.inf + setup.exe, DirectX 9 game (32-bit)
#   build/fixtures/Portable Shooter.zip    zip of a game folder, DirectX 11 (64-bit), with an uninstaller to ignore
#   build/fixtures/Pixel Arcade.7z         7-Zip archive, DirectX 11 (32-bit)
#   build/fixtures/Tiny Demo.exe           a single loose program, DirectX 11 (64-bit)
#   build/fixtures/Space Miner.7z.001..3   a split 7-Zip archive holding a repack-style installer folder, so
#                                          MacX has to join, unpack and then install it (DirectX 11, 64-bit)
#
# Needs: python3 -m pip install ziglang   (a C compiler that targets Windows)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
T="$REPO/build/tests"; F="$REPO/build/fixtures"; W="$REPO/build/fixtures-work"
CC=(python3 -m ziglang cc -municode -O2 -Wl,--subsystem,windows)
mkdir -p "$T"
"${CC[@]}" -target x86_64-windows-gnu "$REPO/engine/tests/dx12test.c" -o "$T/dx12test.exe" -ld3d12 -ldxgi -ldxguid
"${CC[@]}" -target x86_64-windows-gnu "$REPO/engine/tests/dx11test.c" -o "$T/dx11test.exe" -ld3d11 -ldxgi -ldxguid
"${CC[@]}" -target x86-windows-gnu    "$REPO/engine/tests/dx11test.c" -o "$T/dx11test32.exe" -ld3d11 -ldxgi -ldxguid
"${CC[@]}" -target x86-windows-gnu    "$REPO/engine/tests/dx9test.c"  -o "$T/dx9test32.exe" -ld3d9
"${CC[@]}" -target x86-windows-gnu    "$REPO/engine/tests/mxsetup.c"  -o "$T/mxsetup.exe" -lole32 -luuid -lshell32
"${CC[@]}" -target x86_64-windows-gnu "$REPO/engine/tests/escape.c"   -o "$T/escape.exe"
rm -f "$T"/*.pdb "$T"/*.lib

rm -rf "$F" "$W"; mkdir -p "$F" "$W"

# 1. Repack-style installer: the game is ~150 MB so it spans three 64 MB data parts.
mkdir -p "$W/racer/Data"
cp "$T/dx12test.exe" "$W/racer/MetalRacer.exe"
for i in 1 2 3; do head -c $((50 << 20)) /dev/urandom > "$W/racer/Data/assets$i.pak"; done
mkdir -p "$F/Metal Racer (repack)"
cp "$T/mxsetup.exe" "$F/Metal Racer (repack)/setup.exe"
python3 "$REPO/engine/tests/mxpack.py" "$W/racer" "Metal Racer" "MetalRacer.exe" "$F/Metal Racer (repack)" 64

# 2. Disc image with an autorun setup.
mkdir -p "$W/retro-game" "$W/retro-disc"
cp "$T/dx9test32.exe" "$W/retro-game/RetroClassic.exe"
printf 'old school\n' > "$W/retro-game/readme.txt"
cp "$T/mxsetup.exe" "$W/retro-disc/setup.exe"
python3 "$REPO/engine/tests/mxpack.py" "$W/retro-game" "Retro Classic" "RetroClassic.exe" "$W/retro-disc" 64
printf '[autorun]\r\nopen=setup.exe\r\n' > "$W/retro-disc/autorun.inf"
hdiutil makehybrid -quiet -iso -joliet -default-volume-name RETRO -o "$F/Retro Classic.iso" "$W/retro-disc"

# 3. Zip of a portable game folder (plus files MacX should not pick as "the game").
mkdir -p "$W/zip/Portable Shooter/bin"
cp "$T/dx11test.exe" "$W/zip/Portable Shooter/bin/Shooter.exe"
cp "$T/mxsetup.exe" "$W/zip/Portable Shooter/unins000.exe"
printf 'have fun\n' > "$W/zip/Portable Shooter/readme.txt"
(cd "$W/zip" && /usr/bin/zip -qr "$F/Portable Shooter.zip" "Portable Shooter")

# 4. 7-Zip archive of a 32-bit DirectX 11 game.
mkdir -p "$W/7z/Pixel Arcade"
cp "$T/dx11test32.exe" "$W/7z/Pixel Arcade/Arcade.exe"
/usr/bin/tar --format 7zip -cf "$F/Pixel Arcade.7z" -C "$W/7z" "Pixel Arcade"

# 5. One loose program.
cp "$T/dx11test.exe" "$F/Tiny Demo.exe"

# 6. Split archive -> installer folder -> game.
mkdir -p "$W/miner-game" "$W/miner/Space Miner Repack"
cp "$T/dx11test.exe" "$W/miner-game/SpaceMiner.exe"
head -c $((20 << 20)) /dev/urandom > "$W/miner-game/world.pak"
cp "$T/mxsetup.exe" "$W/miner/Space Miner Repack/setup.exe"
python3 "$REPO/engine/tests/mxpack.py" "$W/miner-game" "Space Miner" "SpaceMiner.exe" "$W/miner/Space Miner Repack" 8
/usr/bin/tar --format 7zip -cf "$W/Space Miner.7z" -C "$W/miner" "Space Miner Repack"
python3 - "$W/Space Miner.7z" "$F/Space Miner.7z" <<'PY'
import sys
src, dst = sys.argv[1:]
with open(src, "rb") as f:
    n = 1
    while True:
        chunk = f.read(8 << 20)
        if not chunk:
            break
        open("%s.%03d" % (dst, n), "wb").write(chunk)
        n += 1
PY

rm -rf "$W"
ls -la "$F" "$F/Metal Racer (repack)"
