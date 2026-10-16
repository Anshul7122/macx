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

## Debugging toolkit

Most of the root causes above were found with: Wine's `+seh`/`+relay`/`+loaddll`/`+file` channels (with
`RelayFromInclude` to trace only the game's own calls), `winedbg --command "bt all"`, macOS `sample` for native
stacks, Rockstar's own minidumps (parsed by hand for thread stacks), static disassembly (`llvm-objdump`) of
D3DMetal's shim, and small probe programs in `engine/tests/`.
