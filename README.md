# MacX

Run Windows games and apps on Apple silicon Macs, including **DirectX 12** games, through
**upstream Wine 11 + Apple's D3DMetal**.

- **DirectX 12 → Metal** via Apple's D3DMetal (from the Game Porting Toolkit), bridged onto an upstream
  Wine 11 build. Until now D3DMetal only ran inside CrossOver or Game Porting Toolkit's old Wine 7.7.
- **DirectX 9–11** via DXMT (DirectX 10/11 → Metal, 32- and 64-bit) and Wine's own DirectX 9 (OpenGL, which
  Apple runs on Metal).
- **A Windows drive on your Desktop.** A *MacX* folder appears on the Desktop and shows up inside Windows as
  drive **W:**. Drop a game folder, `.exe`, installer, `.iso` or `.zip` into it and it shows up in
  the app, ready to play, install, mount or unpack.
- **Steam for Windows**, the Rockstar Games Launcher and other launchers, with their window-drawing quirks fixed.
- **Per-program engine and graphics choice**, with an automatic default based on the DirectX version each
  program uses.
- **Boxes: one folder = one sealed-off Windows PC.** Each folder in `~/MacX Boxes` is a separate Windows
  install (its own C:, registry, saves and Wine server). Programs in a box see only drive C: and the box
  folder as W:, not the rest of your Mac. Delete the folder in Finder and the whole Windows PC goes with it.
- **Drop in anything, as much as you like.** Game folders, single `.exe` programs, installers (also
  "setup.exe + data-1.bin, data-2.bin…" folders and `.msi`), `.zip` / `.7z` / `.rar` archives, split
  `.001` archives and `.iso` discs. **Set Up All** unpacks, inserts and installs them one after another, then
  lists every game with the best way to Metal already picked.

**Tested:** GTA V Enhanced (DirectX 12, Steam), Story Mode, about **45 fps** on a MacBook with M4, also started
inside a sandboxed box. Six stand-in games covering every supported form (installer + data parts, disc
image, zip, 7z, split archive, single exe; DirectX 9/11/12, 32- and 64-bit) install and run at the display's
120 Hz cap. Build them with `scripts/make-test-fixtures.sh`.

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

## Boxes

A box is a folder in `~/MacX Boxes` that behaves like its own Windows PC. Everything Windows-side lives in the
folder's hidden `.macx` subfolder, so the folder *is* the PC: copy it to back it up, rename it, or drag it to
the Trash to delete it. MacX notices a deleted box and stops anything still running in it.

**Using one** (the full walkthrough is in **[docs/USER-GUIDE.md](docs/USER-GUIDE.md)**):

1. *Boxes* page → **New Box**. New boxes are clones of a prepared template (APFS copy-on-write): under a
   second, and almost no disk space until programs write to it.
2. **Add Files…**, or drag any number of things onto the box (in the app or into its folder in Finder).
3. **Set Up All** works through them in the background, one at a time:

   | You add | MacX does |
   | --- | --- |
   | a game folder or a single `.exe` | nothing to set up; it's listed as a game right away |
   | an installer: `setup.exe`, a folder with `setup.exe` + `data-1.bin`…, or an `.msi` | runs it (you click through its own window as on Windows) |
   | `.zip` `.7z` `.rar` `.tar`, or split `.7z.001` / `.zip.001` parts | unpacks it, then sets up whatever came out (e.g. an installer inside) |
   | `.iso` / `.img` disc image | inserts it as drive D: (E:, …) and runs its setup / autorun |

4. Installed games appear under **Games & programs** (found from their Start Menu and Desktop shortcuts,
   Windows' installed-programs list and Steam). Press **Play**.

**How graphics reach Metal** — picked per game from what it uses, changeable in the game's menu:

| Game uses | Route | Notes |
| --- | --- | --- |
| DirectX 10 / 11 / 12, 64-bit | **D3DMetal** (Apple, from the Game Porting Toolkit) | the GTA V Enhanced path |
| DirectX 10 / 11, 32-bit | **DXMT** (DirectX → Metal) | D3DMetal is 64-bit only |
| DirectX 9 and older, OpenGL | **Wine** (OpenGL, which Apple runs on Metal) | |
| Vulkan | **Wine** (Vulkan → MoltenVK → Metal) | |

**Your existing Steam setup** can join in two ways: **Copy my Steam setup into a box** makes an APFS clone of
it (instant, no extra disk space, the original untouched), which is how GTA V Enhanced was run inside a
sandboxed box. **Move my existing setup into a box** moves it instead (nothing copied).

What a box keeps in:

| From inside a box, a Windows program... | |
| --- | --- |
| sees drives | C: (the box's own), W: (the box folder), and any disc you inserted. No Z: drive (the whole Mac) |
| writes Desktop, Documents, saves | into the box (real folders, not links to your Mac's folders) |
| reads or writes your home folder through Wine's `\\?\unix\` paths | blocked by a macOS sandbox profile (`sandbox-exec`) |
| uses the network, GPU, audio, controllers | allowed, as normal |

Limits: the sandbox closes the obvious ways out of a box; it is not a security boundary for malware.
Programs can still read system-wide locations outside your home folder, and use the network. Metal's shader
cache is shared by all Wine programs (macOS keeps it per app, not per box). Multi-part `.part1.rar`
archives need unpacking with an app such as The Unarchiver first.

## What won't run

Be realistic about these; no Wine-based tool (MacX, CrossOver, Whisky, Game Porting Toolkit) gets past them:

- **Kernel-level anti-cheat**: BattlEye, Easy Anti-Cheat in kernel mode, Riot Vanguard, Activision's
  Ricochet (Call of Duty), FACEIT. They need a Windows kernel driver, and Wine has no Windows kernel.
  Multiplayer in those games won't connect; some refuse to start at all. Single-player modes that can start
  without the anti-cheat (e.g. GTA V Story Mode with `-nobattleye`) can work. Each game's online terms
  still apply.
- **DRM**: Steam, Rockstar and most launcher DRM works. Denuvo usually works but counts hardware changes as
  new activations, and each box looks like a different PC (its own MachineGuid), so installing the same
  Denuvo game in several boxes can use up its daily activation limit.
- **Hardware-specific features**: NVIDIA-only features such as DLSS, Windows kernel drivers, VR headsets.

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
| `app/` | SwiftUI app (`main.swift`), backend (`macxctl.py`), installer (`macxinstall.py`) |
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
