# How MacX runs DirectX 12 on upstream Wine 11

Apple's **D3DMetal** (part of the Game Porting Toolkit) translates DirectX 11 and 12 to Metal. Apple ships it as
a *redistributable* aimed at CrossOver-style Wine: Windows-side DLLs (`d3d12.dll`, `dxgi.dll`, …), plus one
native library (`libd3dshared.dylib`) and the `D3DMetal.framework`. It runs in CrossOver and in Game Porting
Toolkit's own 2023-era Wine 7.7. Today's Steam client crashes on that Wine 7.7, and Steam has to share a Wine
with the games it launches. So a modern Wine is needed, and upstream Wine 11 can't load D3DMetal as-is.

Below are the six gaps between them, how each showed up, and the fix.

## 1. A removed Wine function: `__wine_unix_call`

D3DMetal's DLLs import `__wine_unix_call` from `ntdll.dll`. Upstream Wine 11 replaced it with a
`__wine_unix_call_dispatcher` pointer, so the DLLs failed to load.

**Fix:** `engine/bridge/ntdlx.c`, a tiny DLL exporting `__wine_unix_call` (forwarding to the dispatcher) and
`NtQueryVirtualMemory`. The installer rewrites the import table of each D3DMetal DLL from `ntdll.dll` to
`ntdlx.dll`, a same-length in-place patch (`patch_imports.py`).

## 2. The Mac driver's function table

D3DMetal's native side looks up an exported `macdrv_functions` table in Wine's Mac driver, with CrossOver's
layout: window data, Metal view and device helpers, and `OnMainThread`. Upstream Wine doesn't export it. An
earlier DXMT patch exported a partial table with empty slots.

**Fix:** `engine/wine-patches/0001-…`. The full 10-slot table, with an adapter that returns the CrossOver
(Wine 7.x) window-data layout, including the window, whole and client rects.

## 3. The thread register (GSBASE), the hard one

On macOS x86-64, `%gs` points at thread-local storage. Upstream Wine 11 *switches* `%gs` to the Windows TEB while
Windows code runs, and back to the macOS TSD on each syscall. CrossOver doesn't switch. D3DMetal's Windows-side
DLLs call its native code **directly** (the native library is compiled with the Windows calling convention),
without going through Wine's dispatcher. On upstream Wine that native code therefore runs with `%gs` = TEB, and
the first `pthread_setname_np` reads a NULL "pthread self" and crashes.

**Fix:** `engine/wine-patches/0002-…`, ntdll in **CrossOver mode**. `%gs` stays on the macOS TSD. Windows code
reaches its TEB through the TSD slots Apple reserves for Wine: slot 6 (`gs:0x30`, TEB self) and slot 11
(`gs:0x58`, TLS array). The dispatchers mirror these on every return to Windows code, and read the TEB through
`gs:0x30` instead of fixed `gs:` offsets.

Two traps along the way:
- **Slot 12 (`gs:0x60`, the PEB)** is libc's `localtime()` buffer key. Leaving the PEB there let `localtime()`
  write a `struct tm` over the real PEB; its `tm_zone` pointer landed on `PEB->ProcessHeap`. Copy-protected code
  still reads `gs:0x60`, so slot 12 is **swapped** at every boundary: the PEB while Windows code runs, libc's
  value (saved at TEB+0x348) while native code runs.
- **TLS:** the loader assigns a new thread's TLS array *after* the mirror runs, and TLS callbacks run before any
  syscall refreshes it. Rockstar's protected launcher crashed in exactly that window.
  `engine/bridge/patch_tls.py` makes ntdll's one TLS-array store also write `gs:0x58`.
  `patch_peb.py` routes ntdll's own three `gs:0x60` reads through the TEB.

## 4. Shared state: symlinks, not copies

Every D3DMetal `.so` (`d3d12.so`, `dxgi.so`, …) is the same library. Apple ships them as **symlinks** to
`libd3dshared.dylib`. Copying them gave each its own globals, so the Win32 dispatch table `dxgi.dll` filled in
was empty for `d3d12`, and it called NULL.

## 5. GTA V Enhanced: the DirectX 12 Agility SDK

GTA V Enhanced exports `D3D12SDKVersion`/`D3D12SDKPath` and refused to start
(`ERR_GFX_D3D_NOD3D12`) even though D3DMetal happily creates feature-level 12_2 devices. It expects
`d3d12core.dll` loaded in the process (as Windows' Agility SDK loader does) and uses `D3D12GetInterface`, which
D3DMetal doesn't export.

**Fix:** a `d3d12.dll` wrapper (`engine/bridge/d3d12wrap.c`). D3DMetal's own `d3d12.dll` is renamed `d3dmt.dll`,
its export-directory name patched to match (otherwise its forwarders loop back to the wrapper). The wrapper
forwards the D3DMetal exports, implements `D3D12GetInterface` (`ID3D12SDKConfiguration1`, `ID3D12DeviceFactory`)
and loads Wine's `d3d12core.dll`.

## 6. GTA V Enhanced: overlay hook validation

Next, the game hung in "Initializing", until its ~60 s watchdog crashed it deliberately. Rockstar's Social Club
overlay hooks `ID3D12CommandQueue::ExecuteCommandLists` and `::Signal`, and first checks with `VirtualQuery`
that they're committed, executable Windows memory. D3DMetal's methods are native Mach-O code that Wine reports
as `MEM_FREE`, so validation failed and the renderer was torn down.

**Fix:** after device creation, the wrapper repoints vtable slots 10 and 14 of D3DMetal's shared queue vtable at
forwarding thunks inside the wrapper (real PE memory). The vtable lives in a read-only Mach-O segment, so the write
goes through a one-function Wine unix library (`d3d12_unix.c`, `vm_protect`).
Credit: [aprilmaccydee/gta5enhanced-mac](https://github.com/aprilmaccydee/gta5enhanced-mac) identified these last
two causes on CrossOver. MacX implements the fixes as a built-in, version-independent wrapper rather
than a runtime memory patch.

## 7. Boxes: one folder, one Windows PC

A box is `~/MacX Boxes/<Name>/` with the Wine prefix hidden in `.macx/prefix`, so the folder owns everything
(code: `app/macxbox.py`).

- **Template + clone.** `box-template` is a prefix built once with `wineboot` and given the D3DMetal bridge
  files (`ntdlx`, `nvapi64`, `nvngx`, `d3dmt`) and DXVK. New boxes are `cp -c` APFS clones: instant, and they
  share disk blocks until written. Each clone gets a fresh `MachineGuid`. The template is rebuilt when the
  engines change or `TEMPLATE_VERSION` is bumped.
- **Containment.** `dosdevices` keeps only `c:`, `w:` (the box folder) and inserted discs; `z:` is removed.
  The user shell folders (`Desktop`, `Documents`, ...) that Wine links to the Mac's own folders become real
  folders inside the box. Re-checked on every launch.
- **Sandbox.** Programs start under `sandbox-exec` with a generated profile: deny writes and file-data reads
  under the home folder, then allow the box folder and the MacX engines. One catch: the allows must name the
  same operations as the deny (`file-read-data`, not `file-read*`). A wildcard allow does not override a
  specific deny, and Wine's `bin/../lib/...` loader paths then fail with *sandbox blocked open()*.
- **One Wine server per box.** Wine keys its server on the prefix folder's device and inode
  (`/tmp/.wine-UID/server-<dev>-<ino>`), so separate prefixes never share a server and one box can't kill
  another's processes. Processes are attributed to a box with one `lsof` call over all Wine pids.
- **Deleted in Finder.** The app watches `~/MacX Boxes` with FSEvents (ignoring the box's own `.macx`
  bookkeeping). On every list, Wine processes whose prefix is no longer a live box are killed, stale server
  dirs are removed (a server dir is mapped back to its prefix through `/.vol/<dev>/<ino>` + `F_GETPATH`, which
  still resolves for a folder in the Trash) and disc images inserted from a deleted box are ejected.

### Loading anything

Files in the box folder (drive W:) are classified: game folder / program (has a playable `.exe`; uninstallers,
crash reporters, redistributables are skipped when picking "the" exe), installer (`setup*.exe`, `install*`,
`.msi`, or a folder whose only programs are setups, which covers *setup.exe + data-N.bin* repacks), archive,
split archive (`.7z.001`, `.zip.001`; the later parts are hidden), disc image, shortcut, script.

Installers that aren't named like one are recognised by the marks their tool leaves in the first and last
2 MB of the file (Inno Setup, Nullsoft/NSIS, InstallShield, `.wixburn`, 7-Zip SFX, Setup Factory, ...). Custom
installers (Rockstar's, for one) carry none, so the user can override the classification per item, and give
installers options (`/VERYSILENT`, `/S`, `/quiet`).

**Set Up** starts a detached worker (`macxctl.py box _work`) that takes the pending items one at a time and
records each result in `.macx/state.json` (kept apart from `box.json`, which the app rewrites):
archives are unpacked with macOS's own `bsdtar` (zip, 7z, rar, tar; split parts are joined first) into a
folder named after the archive, and anything new that comes out is queued too; discs are attached with
`hdiutil` (read-only), linked as the next free drive letter, and their `autorun.inf` / `setup.exe` is run;
installers run on the Wine engine, sandboxed, and the worker waits for them to finish (exit code 0 =
installed). The app shows the worker's `task.json` as a progress bar.

**Finding what got installed.** Start Menu and Desktop `.lnk` shortcuts (parsed directly: the Shell Link
format's LinkInfo gives the target path), `.url` shortcuts to `steam://rungameid/`, the
`...\CurrentVersion\Uninstall` keys in `system.reg` (both the 64-bit and the `Wow6432Node` half, where 32-bit
installers write), and Steam's `appmanifest_*.acf` files. Each target's PE header gives 32/64-bit, and its
import strings give the DirectX version.

### Which way to Metal

| Game | Route | How MacX sets it up |
| --- | --- | --- |
| 64-bit DirectX 10/11/12 | D3DMetal | the `d3dmetal` engine; its builtin d3d11/d3d12/dxgi are D3DMetal |
| DirectX 10/11 (32- or 64-bit) | DXMT | DXMT's `d3d11`/`dxgi`/`d3d10core` (builtin marker stripped) copied next to the exe, plus `WINEDLLOVERRIDES=...=n,b` |
| DirectX 9 and older, OpenGL, Vulkan | Wine | wined3d over OpenGL (Metal-backed on Apple silicon), winevulkan over MoltenVK |

Findings that shaped this:

- **DLLs next to the exe win.** Wine loads a DLL from the program's own folder before its builtin, whatever
  the engine: with DXMT files beside it, a game set to D3DMetal still got DXMT. So MacX removes its DXMT
  copies again (only files identical to its own) whenever a game runs another way.
- **DLLs in system32 don't.** For the Windows folders Wine prefers its builtins unless an override says
  "native". The shared setup relies on that: DXVK sits in `system32` and only the programs the registry sets
  to native (the Steam and Rockstar launchers' Chromium windows) use it. Boxes keep exactly that layout;
  replacing it with DXMT made the Rockstar launcher crash (DXMT doesn't implement
  `SwapDeviceContextState`, which Chromium's ANGLE calls).
- **DXVK for macOS is too old for 32-bit and DirectX 9 now.** DXVK-macOS 1.10.3 (2023) against the MoltenVK
  1.4 that ships with Wine 11: 32-bit DirectX 11 fails in `vkCreateBuffer` (external memory handle type) and
  DirectX 9 in `vkCreateDevice` (geometry shader feature). DXMT's 32-bit build and wined3d cover those games.

**Launchers installed into a box** get what the shared setup's Repair gives them: Steam's and the Rockstar
launcher's Chromium helpers are wrapped (`--in-process-gpu`), and the Rockstar executables are set to DXVK
with D3DMetal's `d3d12` / `nvapi64` hidden (written with `regedit` once, then left alone).

**A real Inno Setup repack.** Inno Setup 6.7.3 installed into a box with `/VERYSILENT`; its `ISCC.exe`, run in
the box, compiled `engine/tests/innoracer.iss` (LZMA2, solid, `DiskSpanning` into 30 MB `setup-N.bin` slices) to
`setup.exe` + 3 parts; a fresh box installed that in 7 s (files byte-identical) and played the game on D3DMetal
at 112.9 fps (`scripts/make-inno-repack.sh` repeats all of it). It exposed one bug: Wine's IShellLink writer
counts a terminating NUL in the .lnk StringData fields, so arguments came back as `"\0"`; strings are now cut at
the first NUL.

**A real game: Unigine Heaven 4.0** (official installer, 247 MB). Its Inno Setup 5 installer (2013, 32-bit)
crashes in Wine 11 on both engines, sandboxed or not: an access violation in Wine's 32-bit code with
`esp=ffffffff`, then "Exception frame is not in stack limits" (GPTK's Wine 7.7 has no 32-bit support at all).
So for Inno installers that fail, the setup worker falls back to `innoextract` (if installed) and unpacks
`{app}` into the box. Heaven is 32-bit DirectX 11 with the API only in its engine DLL, so detection now also
scans the DLLs next to an `.exe` that names no API (Unity, Unreal, Unigine games). On DXMT: 8.8 fps at its
defaults, 24.7 fps at QUALITY_MEDIUM 1280×720; wined3d's D3D11 and Heaven's OpenGL renderer draw nothing.
Repacked with Inno Setup 6 (setup.exe + 4 × ≤80 MB parts, shortcut with Parameters/WorkingDir), it installs in a
fresh box in 6 s with all files identical and plays on DXMT (13–25 fps, first run). Its Qt WebKit launcher is
a layered window that stays transparent under Wine, hence per-game Program & Launch Options; folders whose only
top-level launcher is a `.bat` naming one of their programs start through that `.bat` (`cmd /c`), and DXMT's
DLLs are placed next to every program folder of the game, not only the started one.

**Unigine Superposition (64-bit DX11) on D3DMetal.** Black 3D scene with the UI drawing: the engine log showed
`E5017: Aborting due to not yet implemented feature: Double-to-integer conversion` — Wine's builtin
`d3dcompiler_47` (vkd3d-shader's HLSL compiler) rather than Microsoft's copy shipped in the game's `bin`.
Boxes now run every game with `d3dcompiler_42…47,d3dx11_42/43,d3dx9_42/43=n,b`: a game's own copy wins, Wine's
builtin is the fallback. Then the benchmark stopped right after "Benchmark running": the engine (a separate
process from its launcher) never became the active app, since macOS 14's cooperative activation doesn't let a
new process take focus; one click into its window fixes it. 1080p Medium: score 4,259, 31.86 fps average.

**Downloads into a box ("MacX Games" on the Desktop).** A box flagged `installHere` passes `/DIR=W:\<Game>` to
Inno Setup installers (repacks, GOG), with the name cleaned of `[… Repack]`, versions and "setup"; files that
are still downloading (`.crdownload`, `.part`, `.!qB`, …) are not listed; `.exe`s opened from Finder inside a
box are set up or played in that box (not the shared setup); and the innoextract fallback is skipped when the
unpacked files are under 5% of the installer's data (repacks keep the game in their own compressed format,
which only their installer can read). The Desktop entry is a link to `~/MacX Boxes/MacX Games`, since the
Desktop itself is a protected folder.

**Names Windows can't use.** A download folder whose name ends in a space or a dot (common with torrent
clients) can't be named in Windows: Wine strips the trailing space, so the installer starts in the Windows folder
("could not open working directory") and can't find the data parts next to it. Items are renamed without it when
added, set up or played.

Real installers tried: Rockstar's Social Club setup (NSIS, 122 MB) installs quietly in about 15 s; the Rockstar
Games Launcher's own installer ignores `/S` and waits for clicks, as on Windows; Microsoft's VC++ 2015-2022
redistributable (WiX Burn) fails under Wine 11 itself (`Failed to extract all files from container, erf
1:2:0`, also outside the sandbox and from C:), which is harmless because Wine ships msvcp140/vcruntime140.

**The app and the Desktop folder.** The legacy drive folder lives on the Desktop, which macOS protects:
opening it (FSEvents' watch-root opens every parent directory) blocks while macOS waits for the user to allow
access, and an ad-hoc-signed app is asked again after every rebuild. The app therefore loads boxes first and
starts its folder watches off the main thread, so a pending prompt can't freeze the window.

### Performance

- **Game Mode.** macOS turns Game Mode on for a full-screen game whose app is in the games category. Wine
  processes have no app identity of their own (RunningBoard lists them as `anon<wine>`), so macOS attributes
  them to the app that launched them. MacX's Info.plist declares `public.app-category.games`, but that doesn't
  carry over: in a full-screen test started from MacX's Play button (Superposition, 17 October) `gamepolicyd`
  logged MacX's own launch (`gameDidLaunch`, "Game mode status is now paused") and never switched Game Mode on
  while the game was frontmost; the frontmost app was the anonymous Wine process. (One "on" event was logged on
  16 October while a Wine game ran, cause unknown.) Making Game Mode work needs the game's Wine process itself
  to be launched by LaunchServices as a game-category app; still to do. A separate game-category wrapper bundle around
  the `wine` binary was tried and isn't needed (an exec'd process stays anonymous anyway).
- **MacX's own cost while a game runs.** The app refreshes status every 4 s. Attributing Wine processes to boxes
  used to list every open file of every Wine process (`lsof`), and a game keeps thousands open. It now asks
  `lsof` only for each process's working folder (`-d cwd`), which is inside its prefix's C: drive or its box
  folder, or is a wineserver's server dir (resolved through `/.vol`); only processes that doesn't explain get
  the full scan. With Steam running: 0.47 s → 0.075 s per check. (Reading `WINEPREFIX` from the process
  environment would be cheaper still, but Wine doesn't pass it on to the processes it starts.)
- **Sandbox cost.** `sandbox-exec` checks file opens; a running game does few. The same GTA V start-up state
  (memory, archives open, threads) was reached inside and outside a box, and GTA V played at ~60 fps in a box.
- **Read-only helper calls have a 45 s limit**, so a file system that blocks (macOS waiting for Desktop-folder
  permission) can't leave the app waiting forever.

**Copy of the shared setup.** `box clone-main` is `cp -cR` of the shared prefix into a new box (1.7 s for a
100 GB Steam + GTA V install, no extra disk), keeping its MachineGuid (it is the same PC) and then applying
the containment above. GTA V Enhanced was started from Steam inside such a box, under the sandbox: Steam →
PlayGTAV → Rockstar launcher → `GTA5_Enhanced.exe`, title active in the Rockstar launcher.

**Migration.** `box migrate` renames the old shared prefix and Desktop folder into `Main` (same disk, so no
copy) and leaves symlinks at the old paths for the Steam code.

## Debugging toolkit

Most of the root causes above were found with: Wine's `+seh`/`+relay`/`+loaddll`/`+file` channels (with
`RelayFromInclude` to trace only the game's own calls), `winedbg --command "bt all"`, macOS `sample` for native
stacks, Rockstar's own minidumps (parsed by hand for thread stacks), static disassembly (`llvm-objdump`) of
D3DMetal's shim, and small probe programs in `engine/tests/`.
