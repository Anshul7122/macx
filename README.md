# MacX

Run Windows games and apps on Apple silicon Macs, including **DirectX 12** games, through
**upstream Wine 11 + Apple's D3DMetal**.

- **DirectX 12 → Metal** via Apple's D3DMetal (from the Game Porting Toolkit), bridged onto an upstream
  Wine 11 build. Until now D3DMetal only ran inside CrossOver or Game Porting Toolkit's old Wine 7.7.
- **DirectX 9–11** via DXMT (DirectX 11 → Metal) or DXVK (→ Vulkan → MoltenVK).
- **A Windows drive on your Desktop.** A *MacX* folder appears on the Desktop and shows up inside Windows as
  drive **W:**. Drop a game folder, `.exe`, installer, `.iso` or `.zip` into it and it shows up in
  the app, ready to play, install, mount or unpack.
- **Steam for Windows**, the Rockstar Games Launcher and other launchers, with their window-drawing quirks fixed.
- **Per-program engine and graphics choice**, with an automatic default based on the DirectX version each
  program uses.

**Tested:** GTA V Enhanced (DirectX 12, Steam), Story Mode, about **45 fps** on a MacBook with M4, plus DirectX 11
and 12 test programs at the display's 120 Hz cap.

> MacX is an independent open-source project by Anshul Chaudhary. It is not affiliated with Microsoft, Apple,
> Valve or Rockstar Games.

## Requirements

- Apple silicon Mac, macOS 14 or newer, Rosetta 2
- About 4 GB free disk space
- **Apple's Game Porting Toolkit** (free with an Apple ID; supplies D3DMetal):
  <https://developer.apple.com/games/game-porting-toolkit/>,
  or `brew install --cask gcenx/wine/game-porting-toolkit`

## Install

1. Download `MacX-x.y.z.dmg` from [Releases](../../releases) and drag **MacX** to Applications.
2. MacX is free and isn't notarized by Apple (that needs a paid developer account), so macOS warns the first time.
   Right-click **MacX** → **Open** → **Open**. If macOS still refuses, run this once in Terminal:
   `xattr -dr com.apple.quarantine /Applications/MacX.app`
3. The setup screen checks your Mac and installs the engines (a few minutes, about 1.5 GB). Downloads are pinned
   and checksum-verified, and D3DMetal is copied from *your* Game Porting Toolkit install.

## How it works

The short version: Apple's D3DMetal is built for CrossOver-style Wine. Upstream Wine 11 differs in
four places, and MacX bridges each one. GTA V Enhanced then needed two more fixes for Agility SDK
residency and overlay hook validation. Read **[docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)**.

## Build from source

```bash
pip3 install ziglang            # Windows-side compiler
brew install bison              # for configuring Wine
scripts/build-engine-kit.sh     # patched Wine 11.18 libraries + bridge DLLs (compiled from source)
scripts/build-app.sh --dmg      # dist/MacX.app and the .dmg
```

| Path | What |
|---|---|
| `app/` | SwiftUI app (`main.swift`), backend (`wpctl.py`), installer (`wpinstall.py`) |
| `engine/wine-patches/` | Patches to Wine 11.18 (`winemac.drv`, `ntdll`) |
| `engine/bridge/` | `ntdlx.dll`, the `d3d12` wrapper (+ unix side), PE patchers |
| `engine/wrap/` | Chromium helper wrapper (Steam / Rockstar launcher windows) |
| `engine/tests/` | DirectX 11/12 and capability test programs |

## Credits and licenses

MacX's own code is MIT-licensed ([LICENSE](LICENSE)). It builds on [Wine](https://www.winehq.org)
(LGPL), [Gcenx's macOS Wine builds](https://github.com/Gcenx/macOS_Wine_builds),
[DXVK-macOS](https://github.com/Gcenx/DXVK-macOS), [DXMT](https://github.com/3Shain/dxmt) and Apple's D3DMetal
(not redistributed). The GTA V Enhanced root-cause analysis by
[aprilmaccydee/gta5enhanced-mac](https://github.com/aprilmaccydee/gta5enhanced-mac) pointed to the last two fixes.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
