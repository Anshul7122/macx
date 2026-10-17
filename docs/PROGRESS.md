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
- [ ] Push / release 0.2.0 on GitHub — waiting for the user's OK
- [ ] Confirm the Game Mode icon appears when playing full screen from MacX (screen was locked)

## Rules
- Close apps/games after testing (`python3 app/macxctl.py box stop "<box>"`, quit MacX) — the Mac heats up.
- No pirated content; tests use the self-made fixtures. Personal GitHub only (Anshul7122), noreply email.
