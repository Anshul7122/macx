# MacX 0.2 work log (branch `feature/boxes`)

Goal: a working build where any number of files (game folders, single .exe, installers including
"repack" style setup.exe + data-N.bin, .msi, .zip/.7z/.rar, split .001 archives, .iso discs) can be dropped
into a box, get set up automatically, and then run on Metal like GTA V Enhanced does. Document everything and
finish with a plain-language report (docs/REPORT-0.2.md).

## Done
- [x] Boxes (one folder = one Windows PC), sandbox, Finder-delete detection (commit 55e771f)
- [x] Test fixtures: `scripts/make-test-fixtures.sh` (6 stand-in games in every format, 32/64-bit, DX9/11/12)
- [x] Backend: files on W: classified; setup queue (unpack / insert disc + run setup / run installer), chains
      archive -> installer; installed games found via Start Menu/Desktop shortcuts, uninstall registry, Steam
- [x] Graphics routes: D3DMetal (64-bit DX10-12), DXMT placed beside the exe (DX10/11 incl. 32-bit),
      Wine's own (DX9 via OpenGL-on-Metal, Vulkan via MoltenVK); DXVK kept system-wide for launchers
- [x] All 6 test games installed and ran on Metal (~112-120 fps; DX9 ~4000 fps)
- [x] Swift UI: Boxes page with Add Files, drop anything, Set Up All, progress, Play/Stop, engine picker
- [x] "Copy my Steam setup into a box" (APFS clone, 1.7 s, no extra disk); GTA V Enhanced launched in the
      sandboxed box (Steam -> Rockstar launcher -> GTA5_Enhanced.exe ran ~5 min, title active)
- [x] Legacy status no longer counts box processes

## Remaining
- [x] Commit this work
- [x] App defaults to the Boxes page; version 0.2.0
- [x] Docs: README (Boxes section rewrite), docs/HOW-IT-WORKS.md section 7, docs/USER-GUIDE.md (plain language)
- [x] Build .dmg + install to ~/Applications, open it, check Boxes page, quit it
- [x] Final report docs/REPORT-0.2.md (plain language, what/why/how to use/limits)
- [x] Close everything (no Wine, no MacX running); delete the auto-resume cron job
- [x] GTA V Enhanced played in a box by the user (~60 fps open gameplay)
- [x] Real installers: Social Club (NSIS) installed quietly; installer detection by tool + Treat as Installer/Program + Install Options; launcher fixes in boxes; app no longer freezes on the Desktop permission
- [x] Performance pass: Game Mode (MacX is a game-category app; Wine games are credited to it), process
      attribution via working folder (0.47 s -> 0.075 s per check), 45 s limit on read-only helper calls,
      fullscreen option in the DX12 test, "best frame rate" guide section
- [x] Real Inno Setup repack (built with official Inno Setup 6.7.3, downloaded with the user's OK): installed via
      MacX in a fresh box in 7 s, files identical, played on D3DMetal 112.9 fps; fixed .lnk NUL bug
- [x] Real game: Unigine Heaven 4.0 (user OK'd download + innoextract via Homebrew). Old Inno 5 installer
      crashes in Wine 11 -> innoextract fallback; detected 32-bit DX11 via engine DLL -> DXMT; ~25 fps medium;
      repacked with Inno Setup 6 -> fresh box install 6 s -> played 13-25 fps. Added Program & Launch Options,
      .bat launchers, DXMT in all program folders, status colour by state.
- [x] Game Mode tested from MacX's Play button: does NOT switch on (frontmost app is anonymous Wine). Docs corrected.
- [x] Superposition on D3DMetal works (2026-10-20): game shaders compiled with Wine's builtin d3dcompiler -> black;
      boxes now prefer games' own d3dcompiler/d3dx (n,b). Benchmark stop = focus (click into window). Score 4259,
      31.9 fps avg 1080p Medium. Repack (Inno, 1.5 GB) installs in a fresh box in 91 s, detected D3DMetal.
- [x] MVP for the user's own test: "MacX Games" Desktop folder (box, installHere -> Inno /DIR=W:\Game),
      in-progress downloads hidden, Finder double-click inside a box handled in that box, innoextract
      fallback sanity check. Next: user downloads a repack, installs it there, plays, records a video for analysis.
- [ ] ~~Paused here (user asked to stop, 2026-10-17 18:25):~~ Unigine Superposition (64-bit DX11, official
      installer 1,339 MB, user OK'd) is in box "Superposition", unpacked by the innoextract fallback (its
      installer fails under Wine, code 1). On D3DMetal its launcher works but the 3D scene renders black (UI and
      HUD draw, ~200 fps). On DXMT the launcher crashes (IDXGIKeyedMutex). Next step: the item is already set to
      exe bin/superposition.exe + the launcher's own args + engine dxmt -> press Play, check the scene renders,
      measure fps (xctrace), then repack with Inno Setup (Repack Lab) and install in a fresh box.
- [ ] Game Mode: launch the game's Wine process via LaunchServices as a game-category app (wrapper bundle +
      `open -n -a`, sandbox applied inside); exec'd processes stay anonymous.
- [ ] **Older 32-bit installers crash (Inno Setup 5.x: most repacks, Superposition's and Heaven's official
      installers).** Same as WineHQ 60494 / Gcenx/macOS_Wine_builds#172: after Wine sets a thread's 32-bit context
      (NtSetInformationThread(ThreadWow64Context) at the end of a user callback), the program's next far jump into
      wow64cpu's syscall_32to64 runs in 32-bit mode under Rosetta (AV at wow64cpu+0x1135 reading 0x2EC5, then
      handlers at 0 -> "stack overflow ... addr 0x0"). Deterministic for Inno 5.5.7 right after the first window.
      Tried and ruled out (on a copy of the engine; originals untouched): forcing SS/DS/ES to the flat selector,
      and replacing the iretq full-restore with an ljmp return (r8 at the fault shows the fast ljmp path was
      used). Next idea: force CS to the cs32 global on both return paths (context SegCs may be odd after the
      callback), and log the WOW64_CONTEXT set at that call. Auto-mode safety checks block binary-patching /
      inspecting the Wine engine, so this needs the user's explicit permission rule. Fallback today: innoextract
      for plain Inno installers (not for repacks with their own compression).
- [ ] Push / release 0.2.0 on GitHub — waiting for the user's OK
- [ ] Confirm the Game Mode icon appears when playing full screen from MacX (screen was locked)

## Rules
- Close apps/games after testing (`python3 app/macxctl.py box stop "<box>"`, quit MacX) — the Mac heats up.
- No pirated content; tests use the self-made fixtures. Personal GitHub only (Anshul7122), noreply email.
