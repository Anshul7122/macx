# MacX 0.2 — report: "drop in anything, play it on Metal"

*Written 17 October 2026 for Anshul. No programming knowledge needed; there's a glossary at the end.*

## In one paragraph

MacX can now take **any number of Windows files at once**: game folders, single programs, installers
(including the "setup.exe + data-1.bin, data-2.bin…" kind that repacks use), archives, split archives and disc
images. It sets them up one after another by itself, finds the games that got installed, and runs each one on
your Mac's graphics (Metal) the best available way, the same way GTA V Enhanced runs. GTA V Enhanced itself now
also runs from inside a sealed-off box: you played it there in open gameplay at close to 60 fps. Everything lives in
**boxes**, folders that each act as a separate, sealed-off Windows PC. The new version (0.2.0) is built,
installed in your Applications folder, and documented. It is saved on the `feature/boxes` branch and **not yet
published to GitHub**; that waits for your OK.

## What you can try right now

Open **MacX** (it now opens on the **Boxes** page). Two boxes are ready:

| Box | What's in it | Try this |
| --- | --- | --- |
| **Test Lab** | six small test "games" I made, in every supported form, already set up | Press **Play** on any of them. Each draws a coloured window for 8 seconds. |
| **GTA Box** | a copy of your Steam setup with GTA V Enhanced (made instantly, uses no extra disk space) | Press **Play** next to *Grand Theft Auto V Enhanced*. Steam, then the Rockstar launcher, then the game start inside the box. |
| **Repack Test** | a game installed from a real Inno Setup repack (setup.exe + .bin parts) | Press **Play** next to *Inno Racer*. |
| **Repack Lab** | Inno Setup itself, and the repack it built (*Inno Racer Repack*) | Drop the *Inno Racer Repack* folder into a new box to try the whole install yourself. |
| **Real Installers** | two real installers that came with GTA V (Rockstar's Social Club and Games Launcher) and Microsoft's Visual C++ installer | See "Real installers" below. Social Club is installed; the Rockstar launcher installer waits for your clicks. |

To try your own files: **New Box** → **Add Files…** (pick as many as you like) → MacX sets them up → **Play**.
The step-by-step guide is in [docs/USER-GUIDE.md](USER-GUIDE.md).

Remember to press **Stop** or **Stop All** when you're done, so the Mac doesn't keep working (and heating up).

## What I built, in plain words

### 1. Boxes: one folder = one Windows PC
Every box is a normal folder in `MacX Boxes` (in your home folder). Windows' own files for that "PC" (its C:
drive, settings, saves) are hidden inside it. Programs in a box can only see that box. A macOS feature called
a *sandbox* stops them from reading or changing the rest of your files. Delete the folder and the whole PC is
gone, with nothing left over. Making a new box takes under a second, because macOS can make "copies" that
share space until something changes (an *APFS clone*).

### 2. Loading anything, as much as you want
You can drop many things at once. MacX looks at each one and works out what it is:

- **Game folder or single `.exe`**: ready to play. MacX skips uninstallers, crash reporters and installers
  when choosing which program is "the game".
- **Installer**: `setup.exe`, an `.msi`, or a folder holding `setup.exe` plus its data parts (the repack
  layout). MacX runs it, and you click through its window as on Windows.
- **Archive**: `.zip`, `.7z`, `.rar`, `.tar`, or split into parts (`.7z.001`, `.002`…). MacX joins the parts,
  unpacks it, and then deals with whatever came out. If there was an installer inside, it runs that too.
- **Disc image** (`.iso`): MacX "inserts" it as drive D: and runs its setup, like putting in a CD.

### 3. "Set Up All": one button, one at a time
**Set Up All** works through everything in the background, one item after another, and shows its progress.
When you add files through the app it starts by itself. One item failing doesn't stop the others; each one
shows **Installed**, **Unpacked** or what went wrong, and has a **Log** button.

**Installers with odd names.** Real installers aren't always called "setup". MacX also recognises them by the
tool they were made with: Inno Setup (what most repacks use), NSIS, InstallShield, Microsoft's WiX, 7-Zip. When
it still guesses wrong, the **⋯** menu next to the item says **Treat as an Installer** (or **Treat as a
Program**). **Install Options…** passes options to the installer, for example `/VERYSILENT` to install an Inno
Setup repack without clicking.

### 4. Finding what got installed
After installing, MacX looks where Windows itself would to find the games:

- Start Menu and Desktop shortcuts. I wrote a reader for Windows' shortcut file format.
- Windows' list of installed programs. Both halves are checked, because 32-bit installers write to a different place.
- Steam's own list of installed games.

For each game it reads the `.exe` to tell whether it's 32- or 64-bit and which DirectX version it uses.

### 5. Three ways to Metal, picked automatically
| Game | Way to Metal | Why |
| --- | --- | --- |
| Modern, 64-bit, DirectX 10/11/12 | **D3DMetal**: Apple's translator, the one GTA uses | the fastest and most compatible |
| 32-bit DirectX 10/11 | **DXMT**: a free translator straight to Metal | D3DMetal can't do 32-bit games |
| DirectX 9 and older, OpenGL, Vulkan | **Wine's own**: OpenGL, which Apple runs on Metal | covers older games |

You can change the choice per game with the menu next to it. Usually you leave it on **Auto**.

### 6. Your Steam setup in a box
**Copy my Steam setup into a box** makes a box that starts with your Steam, GTA V and saves. Copying your
100 GB setup took **1.7 seconds and no extra disk space**, and your original setup isn't touched. Steam games
appear in the box's list, and **Play** starts them through Steam.

### 7. The app
The Boxes page now has:

- **Add Files…**, and drag-and-drop onto a box
- **Set Up All**, with a progress bar
- a **Games & programs** list with Play/Stop and the graphics menu
- an **Installers, archives & discs** list with each item's status and Log/Eject buttons

It updates by itself when you change things in Finder.

## How I tested it

I made **six stand-in games**, small programs that draw a coloured window and write their frame rate to a
file. I packed them in every form MacX should accept:

| Test | Form | Graphics | Result |
| --- | --- | --- | --- |
| Metal Racer | repack-style installer: `setup.exe` + 3 data parts (150 MB) | DirectX 12, 64-bit | installed, ran on **D3DMetal**, 112 fps |
| Retro Classic | disc image (`.iso`) with autorun setup | DirectX 9, 32-bit | inserted as D:, installed, ran on **Wine/OpenGL**, ~4000 fps |
| Portable Shooter | `.zip` of a game folder (with an uninstaller to ignore) | DirectX 11, 64-bit | unpacked, right `.exe` picked, **D3DMetal** 106–113 fps; **DXMT** 120 fps |
| Pixel Arcade | `.7z` archive | DirectX 11, 32-bit | unpacked, ran on **DXMT**, 120 fps |
| Tiny Demo | a single `.exe` | DirectX 11, 64-bit | ran on **D3DMetal**, 113 fps |
| Space Miner | split archive (`.7z.001`–`.003`) containing an installer folder | DirectX 11, 64-bit | joined → unpacked → installed → ran on **D3DMetal**, 119 fps |

(120 fps is your display's limit, so 112–120 means "as fast as the screen can show".)

- **All five added in one go** were set up in about **6 seconds**, and three of the games ran **at the same
  time** at about 112 fps each.
- **Pressing Play in the app** started the game and showed **Running** and **Stop**.
- **GTA V Enhanced inside a sandboxed box:** Steam, then the Rockstar launcher (signed in), then
  `GTA5_Enhanced.exe` started inside the box. **You played it there: no issues, close to 60 fps in open
  gameplay** (with good cooling). For comparison I also started it from your original setup and sampled both
  the same way: they reach the same state with the same memory use (~1.4–1.5 GB at the start screen), the same
  28 game archives open and ~97 threads.
- **A real Inno Setup repack** (the format of game repacks and GOG offline installers). With your OK I
  downloaded the official Inno Setup 6.7.3 installer (10.6 MB, from Inno Setup's own release page):
  1. MacX installed Inno Setup silently in a box (`/VERYSILENT`), through the normal Set Up queue.
  2. Inno Setup, running in that box, built a real repack of a DirectX 12 game: `setup.exe` plus
     `setup-1.bin`, `-2.bin` and `-3.bin`, LZMA2-compressed and solid, 120 MB packed into 63 MB.
  3. That repack folder went into a **brand-new box**. MacX recognised it as an installer, installed it
     quietly in **7 seconds** with every file byte-for-byte identical to the original, and found the game
     through the shortcuts the installer made.
  4. It recognised the game as DirectX 12, 64-bit, picked D3DMetal, and **Play ran it on Metal at 112.9 fps**.

  This also caught a real bug: shortcuts made under Wine store their text slightly differently from Windows,
  and MacX's reader would have broken **Play** for every game installed by a real installer. Fixed. The whole
  test can be repeated with `scripts/make-inno-repack.sh`.
- **A real game, installed, repacked and played** — Unigine *Heaven* 4.0, a free 3D benchmark built on a real
  game engine (DirectX 11). With your OK I downloaded its official installer (247 MB, from Unigine):
  1. **Its 2013 installer crashes inside Wine 11 itself.** It's an old 32-bit Inno Setup 5 installer; it
     fails on both MacX engines, also outside the sandbox, and in Apple's older Wine too. That's a Wine
     limitation, and real repacks often use such installers, so MacX got a **fallback**: when an Inno Setup
     installer fails and `innoextract` is installed (I installed it with Homebrew, with your OK), MacX unpacks
     the installer instead. Heaven's took **7 seconds** and landed as a ready-to-play folder.
  2. MacX recognised Heaven as **DirectX 11, 32-bit** (from its engine DLL; the `.exe` itself doesn't say)
     and picked **DXMT**, because Apple's D3DMetal only runs 64-bit games.
  3. **It runs on Metal** (you saw it on screen): about **25 fps at Medium quality, 1280×720** (8.8 fps at its
     heavy default settings). Wine's own DirectX 11 and OpenGL routes started but drew nothing.
  4. **The repack:** I packed the game with Inno Setup into `setup.exe` + `setup-1.bin`…`setup-4.bin`
     (260 MB), exactly the repack layout, with a shortcut carrying Heaven's launch options. In a **brand-new
     box** MacX installed it in **6 seconds** (all 63 files identical), found the game and its launch options
     through the shortcut, picked DXMT and played it: **13–25 fps** depending on the scene (first start,
     while it was still compiling shaders).

  Heaven is slower than GTA V because it's 32-bit (so it can't use D3DMetal) and it's built to push
  graphics chips hard. Its own launcher window comes up empty under Wine, like Steam's and Rockstar's did, so
  each game now has **⋯ → Program & Launch Options…** to start the game itself directly. MacX also learned
  to use a game's `.bat` launcher when that's how the game starts.
- **Real installers (not made by me):** the setups that came with GTA V were used as real-world examples.

  | Installer | Made with | Result |
  | --- | --- | --- |
  | Rockstar Social Club setup (122 MB) | NSIS | **installed quietly in ~15 s** through Set Up, inside the sandbox, with the option `/S` |
  | Rockstar Games Launcher setup (106 MB) | Rockstar's own | not recognised by name or tool, so marked with **Treat as an Installer**; it ignores `/S` and opens its window waiting for clicks, exactly as on Windows (I can't click inside Wine windows, so I stopped it) |
  | Microsoft Visual C++ 2015-2022 (x64) | WiX | recognised automatically; **fails under Wine itself** (also outside the sandbox), harmless because Wine already contains those files |
- **Your original setup was checked** after copying: unchanged.
- **Leftovers check (from the first part of the boxes work):** a box deleted in Finder while a game was
  running left nothing behind. Its programs were stopped and its temporary files removed.

## Performance

What decides how fast a game runs, and what MacX now does about it:

| Thing | What I found | What changed |
| --- | --- | --- |
| **Heat** | The biggest factor. Apple chips slow down when hot (your 45 → 60 fps after better cooling). | Advice in the user guide: cooling, plugged in, frame cap, upscaling. |
| **macOS Game Mode** (game gets priority, background work waits) | Turns on only for full-screen games from a "game" app. Wine has no identity of its own, so macOS credits the app that started it. I expected games started from MacX to count as MacX (which is marked as a game app). **Tested: they don't.** While a game is in front, macOS sees an anonymous "Wine" app and keeps Game Mode off. | Confirmed with a full-screen run started from MacX's Play button (Superposition): macOS logged MacX's launch but never switched Game Mode on. Fixing it means launching each game's Wine process as a "game" app through macOS's app launcher; that's for a later version. |
| **MacX's own background work** while you play | Every 4 s the app checked which box each Windows program belongs to by listing all their open files: 0.47 s each time with only Steam running, and far more with a game (thousands of open files). | It now asks only for each program's working folder: **0.075 s**, about 6 times less with Steam alone, and the gap grows with a game running. |
| **The box sandbox** | It checks file access; games do little of that while playing. GTA V reached the same state inside and outside a box, and played at ~60 fps in a box. | Nothing needed. |
| **Upscaling** | GTA V offers FSR (and DLSS, which D3DMetal turns into Apple's MetalFX). | Turned on in MacX already (MetalFX); recommended in the guide. |
| **Frame-rate overlay** | Costs very little. | Can be switched off on the This PC page. |

## Problems I hit and fixed (the interesting part)

1. **The sandbox blocked Wine itself.** macOS's sandbox rules need the "allow" to name exactly the same kind
   of access as the "deny". A general "allow reading" didn't beat a specific "deny reading file contents".
2. **DXVK turned out to be too old.** DXVK was the planned translator for older games. The macOS version is
   from 2023 and fails with the newer graphics library (MoltenVK 1.4) that comes with Wine 11, for 32-bit and
   DirectX 9 games. I switched those games to DXMT and Wine's own route, which both worked first time.
3. **Windows picks DLLs from the game's own folder first.** When a game had DXMT files next to it, it used
   them even when set to D3DMetal. MacX now puts DXMT files next to a game only when it uses DXMT, and takes
   them away again otherwise.
4. **The Rockstar launcher crashed in the box.** I had replaced the system-wide DXVK files that your setup
   uses for the launcher's built-in web browser, and DXMT lacks one function that browser needs. Boxes now keep
   the same system-wide files as your original setup, and the launcher works.
5. **A hidden macOS file (`.DS_Store`) in Windows' users folder** made the GTA box copy fail halfway. Fixed.
6. **The app could have refreshed itself in a loop.** Each refresh writes a small settings file, which looked
   like "something changed in the folder". It now ignores the box's own bookkeeping files.
7. **The old status bar counted games in boxes** as if they were on the old shared drive. Fixed. The old
   "Force Quit" also no longer touches boxes.
8. **The app froze at launch.** The old *MacX Drive* folder lives on your Desktop, which macOS protects. Each
   newly built MacX has to be allowed to look at it again, and while macOS waited for that answer, the app's
   window waited too. MacX now loads boxes first, watches folders in the background, and gives its helper
   requests a time limit, so the window never freezes.
9. **Shortcuts made by real installers broke Play.** Wine writes a hidden end-of-text character into
   shortcut fields; MacX passed it on to the game and starting it failed. Found with the real Inno Setup repack;
   fixed.
10. **Real installers aren't always called "setup".** Rockstar's was taken for a game. MacX now also recognises
   installers by the tool they were made with, and you can correct it with the ⋯ menu.

## Limits — what this doesn't do (honestly)

- **The repacks I tested are ones I built** with the real Inno Setup, one of them of a real game (Heaven); no
  pirated content. Big real-world repacks use the same tool, often an older version (which Wine 11 can crash
  on; MacX then unpacks it with innoextract) plus extra compression helpers that need a lot of memory and time.
- **32-bit games are slower** than 64-bit ones: they go through DXMT instead of Apple's D3DMetal.
- **Some games' own launcher windows come up empty** under Wine. Use ⋯ → Program & Launch Options… to start
  the game's program directly.
- **Multi-part `.rar` archives** (`.part1.rar`, `.part2.rar`) can't be joined by macOS's built-in unpacker. Unpack
  them with *The Unarchiver* or *Keka* first.
- **Kernel-level anti-cheat** (BattlEye, Easy Anti-Cheat, Vanguard, Call of Duty's Ricochet) doesn't work under
  any Wine-based tool. Single-player modes sometimes do.
- **Installers that need extra Windows parts** (for example the .NET Framework) may fail. The Log button shows
  why. Adding automatic installs of those parts is a good next step.
- **The sandbox is a fence, not a virus scanner.** It stops normal programs from touching your files, but only
  run things you trust.
- **Microsoft Visual C++ installers fail under Wine** (a Wine limitation). Harmless: games still run.
- **Some installers ignore "install quietly" options** and need you to click through their window.
- **macOS may ask whether MacX can access your Desktop folder** (for the older MacX Drive). Click Allow.

## Where everything is

| What | Where |
| --- | --- |
| The installed app | `~/Applications/MacX.app` (version 0.2.0) |
| The installer for others | `~/Developer/macx/dist/MacX-0.2.0.dmg` |
| Your boxes | `~/MacX Boxes/` (*Test Lab*, *GTA Box*, *Real Installers*, *Repack Lab*, *Repack Test*, *Heaven*, *Heaven Fallback*, *Heaven Repack Test*) |
| User guide | `docs/USER-GUIDE.md` |
| How it works (technical) | `docs/HOW-IT-WORKS.md`, section 7 |
| This report | `docs/REPORT-0.2.md` |
| Work checklist | `docs/PROGRESS.md` |
| The code | `app/macxbox.py` (boxes), `app/main.swift` (the app), `engine/tests/` (test programs), `scripts/make-test-fixtures.sh` |
| Saved versions (git) | branch `feature/boxes`, on top of 0.1.1, **not pushed to GitHub yet** |

To remove the test boxes: drag *Test Lab*, *Real Installers*, *Repack Lab*, *Repack Test* or *GTA Box* to the
Trash. Finder shows about 0.5–0.7 GB for each test box, but much of that is the Windows system they share with
each other (copy-on-write), so deleting one frees less. *GTA Box* shares its
files with your original setup, so deleting it frees only what changed inside it.

## Next milestone (your plan): a shippable, downloadable MacX

1. **Publish 0.2.0** on the same GitHub repo: merge `feature/boxes`, tag `v0.2.0`, attach the `.dmg`. I need
   your OK for this, since it's public.
2. **A low-maintenance website**: a single page on GitHub Pages (free, served from the same repo, updates when
   you push), with a download button that always points at the newest release, three screenshots and the
   "what won't run" list.
3. **First-run polish for strangers**: a short welcome tour, automatic installs of common Windows parts
   (.NET, Visual C++), and a "Report a problem" button that zips the logs.
4. **Signing**: without Apple's paid developer account, people have to right-click → Open once. The README
   explains this; it's fine for an open-source project.

## Glossary

- **Wine** — free software that lets Windows programs run on a Mac by answering their Windows requests.
- **DirectX** — Microsoft's graphics system that Windows games use (versions 9, 10, 11, 12).
- **Metal** — Apple's graphics system. Everything has to end up here to be drawn on a Mac.
- **D3DMetal** — Apple's DirectX-to-Metal translator (part of the free Game Porting Toolkit).
- **DXMT** — an open-source DirectX 10/11-to-Metal translator. Unlike D3DMetal, it also handles 32-bit games.
- **DXVK / MoltenVK** — DirectX → Vulkan → Metal, a two-step route. Now only used for launcher windows.
- **Prefix / C: drive** — the folder where Wine keeps one Windows installation. Each box has its own.
- **Sandbox** — a macOS feature that limits which files a program may touch.
- **APFS clone** — a macOS copy that takes no extra space until one side changes.
- **Repack** — a game packaged as an installer plus compressed data parts (`setup.exe` + `.bin` files).
- **32-bit / 64-bit** — older Windows programs are 32-bit; modern games are 64-bit. It matters for which
  translator can run them.
