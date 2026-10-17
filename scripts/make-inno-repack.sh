#!/bin/bash
# Builds a real Inno Setup "repack" (setup.exe + setup-1.bin, -2.bin, ...; LZMA2, solid) of the DirectX 12 test game
# inside MacX boxes, then installs it in a fresh box and plays it — the same path a downloaded repack or GOG offline
# installer takes. Needs the official Inno Setup installer (https://jrsoftware.org/isdl.php) and the test programs
# from scripts/make-test-fixtures.sh.
#
#   scripts/make-inno-repack.sh ~/Downloads/innosetup-6.7.3.exe
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; CTL=(python3 "$REPO/app/macxctl.py")
INNO="$1"; LAB="Repack Lab"; TEST="Repack Test"; B="$HOME/MacX Boxes"
wait_setup() { until python3 -c 'import json,sys;sys.exit(0 if json.load(open(sys.argv[1]))["finished"] else 1)' "$B/$1/.macx/task.json" 2>/dev/null; do sleep 2; done; }

# 1. Inno Setup itself, installed quietly through MacX
"${CTL[@]}" box new "$LAB" >/dev/null
"${CTL[@]}" box add "$LAB" "$INNO" >/dev/null
"${CTL[@]}" box set "$LAB" "$(basename "$INNO")" args "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /ALLUSERS" >/dev/null
"${CTL[@]}" box setup "$LAB" >/dev/null; wait_setup "$LAB"

# 2. the game (120 MB: the DX12 test + half incompressible, half compressible data) and the repack
S="$B/$LAB/.build/src"; mkdir -p "$S/Data"
cp "$REPO/build/tests/dx12test.exe" "$S/InnoRacer.exe"
head -c $((60 << 20)) /dev/urandom > "$S/Data/textures.pak"
python3 -c 'import sys; l=b"".join(b"vertex %d %d %d normal 0 1 0 uv 0.5 0.5\n" % (i, i*3%977, i*7%613) for i in range(4000)); open(sys.argv[1],"wb").write(((l*8)[:1<<20])*60)' "$S/Data/world.dat"
cp "$REPO/engine/tests/innoracer.iss" "$B/$LAB/.build/racer.iss"
(cd "$REPO/app" && python3 -c '
import sys, macxbox as X
code = X.spawn(sys.argv[1], "wine", ["C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe", "W:\\.build\\racer.iss"], X.box_path(sys.argv[1]), "iscc").wait()
sys.exit(code)' "$LAB")

# 3. install the repack in a fresh box, quietly, and play it
"${CTL[@]}" box new "$TEST" >/dev/null
"${CTL[@]}" box add "$TEST" "$B/$LAB/Inno Racer Repack" >/dev/null
"${CTL[@]}" box set "$TEST" "Inno Racer Repack" args "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-" >/dev/null
"${CTL[@]}" box setup "$TEST" >/dev/null; wait_setup "$TEST"
"${CTL[@]}" box play "$TEST" 'C:\Games\Inno Racer\InnoRacer.exe'
R="$B/$TEST/.macx/prefix/drive_c/Games/Inno Racer/result.txt"
until grep -qs fps "$R"; do sleep 2; done; cat "$R"
