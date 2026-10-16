# Third-party components

| Component | How it's used | License |
|---|---|---|
| [Wine](https://www.winehq.org) 11.18 | Downloaded at install time ([Gcenx build](https://github.com/Gcenx/macOS_Wine_builds)). `winemac.so` and `ntdll.so` are rebuilt from Wine source with the patches in `engine/wine-patches/` and shipped in the app's engine kit. | LGPL 2.1+. Source: <https://dl.winehq.org/wine/source/11.x/wine-11.18.tar.xz> plus `engine/wine-patches/`. |
| [DXVK-macOS](https://github.com/Gcenx/DXVK-macOS) 1.10.3 | Downloaded at install time. | zlib |
| [DXMT](https://github.com/3Shain/dxmt) 0.80 | Downloaded at install time. | See the DXMT repository |
| Apple D3DMetal (Game Porting Toolkit) | **Not distributed.** Copied at install time from the user's own Game Porting Toolkit; its DLL import tables and one export name are patched on the user's machine. | Apple's Game Porting Toolkit license |
| Wine headers (via [zig](https://ziglang.org)'s mingw-w64) | Compiling the Windows-side bridge DLLs. | mingw-w64 / zig licenses |

The GTA V Enhanced findings in `docs/HOW-IT-WORKS.md` (Agility SDK residency, overlay hook validation) credit
[aprilmaccydee/gta5enhanced-mac](https://github.com/aprilmaccydee/gta5enhanced-mac). No code from that project
is included.
