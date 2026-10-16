"""MacX installer: builds the engines and the Windows C: drive on a fresh Mac.

Downloads (pinned, checksum-verified): Gcenx's Wine 11.18 macOS build, DXVK-macOS, DXMT. Apple's D3DMetal is never
downloaded or shipped here: it is imported from the user's own Game Porting Toolkit install.
Progress goes to <ROOT>/install-status.json so the app can show it.
"""
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import urllib.request

import macxctl as W

PINS = {
    "wine": ("https://github.com/Gcenx/macOS_Wine_builds/releases/download/11.18/wine-devel-11.18-osx64.tar.xz",
             "aa0ea4c82e636ae7bca2076387cb0a5affa26509ad13f119ecd0d62bd7ba6f82"),
    "dxvk": ("https://github.com/Gcenx/DXVK-macOS/releases/download/v1.10.3-20230507/"
             "dxvk-macOS-async-v1.10.3-20230507.tar.gz",
             "f67d99d0a8eeedd7d406b283a3df9f939b5965acb00efcb33d0c6235c195a516"),
    "dxmt": ("https://github.com/3Shain/dxmt/releases/download/v0.80/dxmt-v0.80-builtin.tar.gz",
             "8f260e36b5739e68f3bad613381441385c4dc7b85b78ba8de653d5a6a264529d"),
}
STEAM_SETUP_URL = "https://cdn.fastly.steamstatic.com/client/installer/SteamSetup.exe"
GPTK_HELP = "https://developer.apple.com/games/game-porting-toolkit/"
# D3DMetal's Windows-side DLLs; each one's unix side is the shared libd3dshared.dylib
D3DM_DLLS = ("atidxx64", "d3d10", "d3d11", "d3d12", "dxgi", "nvapi64", "nvngx", "nvngx-on-metalfx")
STATUS = os.path.join(W.ROOT, "install-status.json")
DOWNLOADS = os.path.join(W.ROOT, "downloads")
STEPS = ["Checking this Mac", "Downloading Wine 11", "Downloading graphics layers", "Setting up Wine 11",
         "Setting up D3DMetal engine", "Creating the Windows drive", "Finishing"]


# ------------------------------------------------------------------------------------------------- progress
def status(step, detail="", fraction=None, done=False, error=None):
    os.makedirs(W.ROOT, exist_ok=True)
    data = {"step": step, "stepIndex": STEPS.index(step) if step in STEPS else len(STEPS), "steps": STEPS,
            "detail": detail, "fraction": fraction, "done": done, "error": error, "time": time.time()}
    with open(STATUS + ".tmp", "w") as f:
        json.dump(data, f)
    os.replace(STATUS + ".tmp", STATUS)


def run(cmd, **kw):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError("%s failed: %s" % (os.path.basename(cmd[0]), r.stdout.strip()[-400:]))
    return r.stdout


# ------------------------------------------------------------------------------------------------- checks
def gptk_lib():
    return os.path.join(W.GPTK_APP, "Contents", "Resources", "wine", "lib")


def preflight():
    checks = []

    def add(name, ok, detail="", fix=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "fix": fix})

    add("Apple silicon Mac", platform.machine() == "arm64" or "Apple" in run(["sysctl", "-n", "machdep.cpu.brand_string"]),
        platform.machine())
    ver = platform.mac_ver()[0] or "0"
    add("macOS 14 or newer", int(ver.split(".")[0]) >= 14, "macOS " + ver)
    rosetta = subprocess.run(["arch", "-x86_64", "/usr/bin/true"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL).returncode == 0
    add("Rosetta 2", rosetta, "", "Install it: open Terminal and run  softwareupdate --install-rosetta")
    st = os.statvfs(W.HOME)
    free_gb = st.f_bavail * st.f_frsize / 1e9
    add("4 GB free disk space", free_gb >= 4, "%.0f GB free" % free_gb)
    d3dm = os.path.isdir(os.path.join(gptk_lib(), "external", "D3DMetal.framework"))
    add("Apple Game Porting Toolkit (D3DMetal)", d3dm, W.GPTK_APP if d3dm else "not found",
        "Install Apple's Game Porting Toolkit (free Apple ID): " + GPTK_HELP +
        " or with Homebrew:  brew install --cask gcenx/wine/game-porting-toolkit")
    kit_ok = os.path.isfile(os.path.join(W.KIT, "WINE_VERSION"))
    add("MacX engine kit", kit_ok, W.KIT, "Reinstall MacX (the kit ships inside the app).")
    return checks


# ------------------------------------------------------------------------------------------------- downloads
def download(name, step):
    url, want = PINS[name]
    os.makedirs(DOWNLOADS, exist_ok=True)
    dest = os.path.join(DOWNLOADS, os.path.basename(url))
    if os.path.exists(dest) and W.sha(dest) == want:
        return dest
    tmp = dest + ".part"
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            status(step, "%s: %d of %d MB" % (os.path.basename(url), got >> 20, total >> 20),
                   got / total if total else None)
    if W.sha(tmp) != want:
        os.remove(tmp)
        raise RuntimeError("Checksum mismatch for %s (download corrupted or changed upstream)." % os.path.basename(url))
    os.replace(tmp, dest)
    return dest


def extract(archive, dest):
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    with tarfile.open(archive) as t:
        t.extractall(dest, filter="data") if sys.version_info >= (3, 12) else t.extractall(dest)


def single_child(path):
    kids = [k for k in os.listdir(path) if not k.startswith(".")]
    return os.path.join(path, kids[0]) if len(kids) == 1 else path


# ------------------------------------------------------------------------------------------------- PE helpers
def kit_tool(name, *args):
    run([sys.executable, "-I", os.path.join(W.KIT, "tools", name)] + list(args))


def set_export_name(path, new):
    """Rename a PE's export-directory DLL name in place (same length)."""
    d = bytearray(open(path, "rb").read())
    lf = struct.unpack_from("<I", d, 0x3c)[0]
    nsec = struct.unpack_from("<H", d, lf + 6)[0]
    opt = struct.unpack_from("<H", d, lf + 20)[0]
    secs = [struct.unpack_from("<IIII", d, lf + 24 + opt + i * 40 + 8) for i in range(nsec)]

    def off(rva):
        for vsize, va, rsize, raw in secs:
            if va <= rva < va + max(vsize, rsize):
                return rva - va + raw
    no = off(struct.unpack_from("<I", d, off(struct.unpack_from("<I", d, lf + 24 + 112)[0]) + 12)[0])
    old = bytes(d[no:d.index(0, no)])
    assert len(old) == len(new), (old, new)
    d[no:no + len(new)] = new.encode()
    open(path, "wb").write(d)


def strip_builtin_marker(src, dst):
    d = bytearray(open(src, "rb").read())
    if d[0x40:0x50] == b"Wine builtin DLL":
        d[0x40:0x50] = bytes(16)
    open(dst, "wb").write(d)


# ------------------------------------------------------------------------------------------------- install
def install_wine(archive):
    status("Setting up Wine 11", "Unpacking Wine 11")
    staging = os.path.join(W.ROOT, "engines", "wine.new")
    extract(archive, staging)
    app = os.path.join(staging, "Wine Devel.app")
    if not os.path.isdir(app):
        raise RuntimeError("Unexpected Wine archive layout.")
    lib = os.path.join(app, "Contents", "Resources", "wine", "lib", "wine")
    want = open(os.path.join(W.KIT, "WINE_VERSION")).read().strip()
    have = run(["plutil", "-extract", "CFBundleShortVersionString", "raw", os.path.join(app, "Contents", "Info.plist")]).strip()
    if have != want:
        raise RuntimeError("Wine %s doesn't match the engine kit (built for %s)." % (have, want))
    shutil.copy2(os.path.join(lib, "x86_64-unix", "winemac.so"), os.path.join(lib, "x86_64-unix", "winemac.so.orig"))
    shutil.copy2(os.path.join(W.KIT, "unix", "winemac.so"), os.path.join(lib, "x86_64-unix", "winemac.so"))
    run(["xattr", "-cr", app])
    final = os.path.join(W.ROOT, "engines", "wine")
    if os.path.isdir(final):
        shutil.rmtree(final)
    os.rename(staging, final)
    return os.path.join(final, "Wine Devel.app", "Contents", "Resources", "wine", "lib", "wine")


def install_graphics(lib, dxvk_archive, dxmt_archive):
    status("Setting up Wine 11", "Installing DXVK and DXMT")
    gfx = os.path.join(W.ROOT, "gfx")
    extract(dxvk_archive, os.path.join(gfx, "dxvk.tmp"))
    if os.path.isdir(W.DXVK_FULL):
        shutil.rmtree(W.DXVK_FULL)
    os.rename(single_child(os.path.join(gfx, "dxvk.tmp")), W.DXVK_FULL)
    shutil.rmtree(os.path.join(gfx, "dxvk.tmp"), ignore_errors=True)
    extract(dxmt_archive, os.path.join(gfx, "dxmt"))
    dxmt = single_child(os.path.join(gfx, "dxmt"))
    shutil.copy2(os.path.join(dxmt, "x86_64-unix", "winemetal.so"), os.path.join(lib, "x86_64-unix", "winemetal.so"))
    for arch in ("x86_64-windows", "i386-windows"):
        shutil.copy2(os.path.join(dxmt, arch, "winemetal.dll"), os.path.join(lib, arch, "winemetal.dll"))
    os.makedirs(W.DXMT_NATIVE, exist_ok=True)  # per-game DXMT: the release DLLs, loadable as native
    for dll in W.GFX_DLLS:
        strip_builtin_marker(os.path.join(dxmt, "x86_64-windows", dll), os.path.join(W.DXMT_NATIVE, dll))


def install_d3dmetal():
    status("Setting up D3DMetal engine", "Cloning Wine 11")
    src = os.path.join(W.ROOT, "engines", "wine")
    dst = os.path.join(W.ROOT, "engines", "wine-d3dmetal")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    run(["cp", "-cR", src, dst])
    lib = os.path.join(dst, "Wine Devel.app", "Contents", "Resources", "wine", "lib")
    unix, win = os.path.join(lib, "wine", "x86_64-unix"), os.path.join(lib, "wine", "x86_64-windows")
    g = gptk_lib()
    status("Setting up D3DMetal engine", "Importing D3DMetal from Game Porting Toolkit")
    run(["cp", "-cR", os.path.join(g, "external"), os.path.join(lib, "external")])
    for name in D3DM_DLLS:
        pe = os.path.join(g, "wine", "x86_64-windows", name + ".dll")
        if not os.path.exists(pe):
            continue
        target = "d3dmt" if name == "d3d12" else name  # D3DMetal's d3d12 sits behind our wrapper
        so = os.path.join(unix, target + ".so")
        if os.path.lexists(so):
            os.remove(so)
        os.symlink("../../external/libd3dshared.dylib", so)
        shutil.copy2(pe, os.path.join(win, target + ".dll"))
        kit_tool("patch_imports.py", os.path.join(win, target + ".dll"))
        if target == "d3dmt":
            set_export_name(os.path.join(win, "d3dmt.dll"), "d3dmt.dll")
    status("Setting up D3DMetal engine", "Installing the Wine 11 bridges")
    for f in ("d3d12.so",):
        if os.path.lexists(os.path.join(unix, f)):
            os.remove(os.path.join(unix, f))
    shutil.copy2(os.path.join(W.KIT, "unix", "d3d12.so"), os.path.join(unix, "d3d12.so"))
    shutil.copy2(os.path.join(W.KIT, "windows", "d3d12.dll"), os.path.join(win, "d3d12.dll"))
    shutil.copy2(os.path.join(W.KIT, "windows", "ntdlx.dll"), os.path.join(win, "ntdlx.dll"))
    shutil.copy2(os.path.join(W.KIT, "unix", "ntdll-cx.so"), os.path.join(unix, "ntdll.so"))
    kit_tool("patch_peb.py", os.path.join(win, "ntdll.dll"))
    kit_tool("patch_tls.py", os.path.join(win, "ntdll.dll"))


def create_prefix():
    status("Creating the Windows drive", "Running Windows setup (wineboot), about a minute")
    W.ensure_engine("d3dmetal")   # wineboot --init (first time) + D3DMetal files in system32 + W: drive
    sys32 = os.path.join(W.DRIVE_C, "windows")
    for arch, d in (("x64", "system32"), ("x32", "syswow64")):   # DXVK, used by launchers' own windows
        for dll in W.GFX_DLLS:
            src = os.path.join(W.DXVK_FULL, arch, dll)
            if os.path.exists(src) and os.path.isdir(os.path.join(sys32, d)):
                shutil.copy2(src, os.path.join(sys32, d, dll))


def install():
    try:
        status("Checking this Mac")
        bad = [c for c in preflight() if not c["ok"]]
        if bad:
            raise RuntimeError("; ".join("%s (%s)" % (c["name"], c["fix"] or c["detail"]) for c in bad))
        wine_tar = download("wine", "Downloading Wine 11")
        status("Downloading graphics layers")
        dxvk_tar = download("dxvk", "Downloading graphics layers")
        dxmt_tar = download("dxmt", "Downloading graphics layers")
        lib = install_wine(wine_tar)
        install_graphics(lib, dxvk_tar, dxmt_tar)
        install_d3dmetal()
        create_prefix()
        status("Finishing", "Done", 1.0, done=True)
        return {"ok": True, "message": "MacX is ready."}
    except Exception as e:  # noqa: BLE001 - reported to the app
        status("Finishing", str(e), error=str(e))
        return {"ok": False, "error": str(e)}


def install_steam():
    W.ensure_engine(W.steam_engine())
    os.makedirs(DOWNLOADS, exist_ok=True)
    setup = os.path.join(DOWNLOADS, "SteamSetup.exe")
    urllib.request.urlretrieve(STEAM_SETUP_URL, setup)
    W.wine([setup, "/S"], timeout=600, engine=W.steam_engine())
    if not os.path.exists(os.path.join(W.STEAM_DIR, "steam.exe")):
        return {"ok": False, "error": "Steam's installer didn't finish."}
    W.start_steam()
    return {"ok": True, "message": "Steam is installed and starting (its first start downloads an update)."}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "preflight":
        W.out({"checks": preflight()})
    elif cmd == "install":
        W.out(install())
    elif cmd == "install-steam":
        W.out(install_steam())
    elif cmd == "status":
        try:
            W.out(json.load(open(STATUS)))
        except OSError:
            W.out({"step": "", "done": False})
    else:
        W.fail("usage: macxinstall.py preflight|install|install-steam|status")
