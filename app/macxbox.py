"""MacX boxes: one folder = one self-contained Windows PC.

    ~/MacX Boxes/<Name>/            the user's files (drive W: inside Windows)
    ~/MacX Boxes/<Name>/.macx/      hidden: the box's Wine prefix (C:), settings, logs

Deleting the folder removes everything the box installed or created. New boxes are APFS clones of a template
prefix built once (near-instant, almost no disk until they diverge). Containment: no Z: drive, the Windows user
folders (Desktop, Documents, ...) are real folders inside the box, and every box program runs under a macOS
sandbox profile that denies access to the home folder outside the box. This contains ordinary programs; it is not
a guarantee against deliberately malicious software.

Anything can be dropped into a box, as many at once as wanted: game folders, single programs, installers
(including "repack" style setup.exe + data-N.bin folders and .msi), archives (.zip .7z .rar .tar, split .001 parts)
and disc images (.iso .img). "Set up" works through them in the background, one after another: archives are
unpacked, discs inserted and their setup run, installers run. Whatever ends up installed (Start Menu and Desktop
shortcuts, Windows' list of installed programs, Steam games) is listed as a game ready to play, with the way to
Metal picked from the DirectX version it uses.
"""
import glob
import json
import os
import plistlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid

import macxctl as M

BOXES = os.environ.get("MACX_BOXES") or os.path.join(M.HOME, "MacX Boxes")
TEMPLATE = os.path.join(M.ROOT, "box-template")
TEMPLATE_VERSION = "4"   # bump when build_template() changes, so the template is rebuilt
ENGINES_DIR = os.path.join(M.ROOT, "engines")
META = ".macx"
SHELL_FOLDERS = ("Desktop", "Documents", "Downloads", "Music", "Pictures", "Videos", "Templates")
STEAM_EXE = "C:\\Program Files (x86)\\Steam\\steam.exe"
STEAM_ARGS = ["-no-cef-sandbox", "-cef-disable-gpu", "-noverifyfiles", "-norepairfiles"]


# ------------------------------------------------------------------------------------------------- paths
def box_path(name):
    return os.path.join(BOXES, name)


def meta(name, *parts):
    return os.path.join(box_path(name), META, *parts)


def prefix(name):
    return meta(name, "prefix")


def is_box(path):
    return os.path.isdir(os.path.join(path, META, "prefix", "drive_c"))


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    with open(path + ".tmp", "w") as f:
        json.dump(data, f, indent=2)
    os.replace(path + ".tmp", path)


def load_box(name):
    """Settings the user makes (engine per game, ...) and the DirectX-detection cache."""
    data = read_json(meta(name, "box.json"), {})
    data.setdefault("items", {})
    data.setdefault("detect", {})
    return data


def save_box(name, data):
    data.pop("_dirty", None)
    write_json(meta(name, "box.json"), data)


def load_state(name):
    """What "Set up" did (item -> installed/unpacked/failed) and inserted discs. Written by the setup worker, so it
    is kept apart from box.json, which the app rewrites while the worker runs."""
    st = read_json(meta(name, "state.json"), {})
    st.setdefault("items", {})
    st.setdefault("disks", {})
    return st


def save_state(name, st):
    write_json(meta(name, "state.json"), st)


def safe_name(s):
    return re.sub(r"[^\w.-]+", "_", s)[:80]


def unique_path(folder, name):
    stem, ext = (name, "") if os.path.isdir(os.path.join(folder, name)) else os.path.splitext(name)
    path, n = os.path.join(folder, name), 2
    while os.path.lexists(path):
        path, n = os.path.join(folder, "%s (%d)%s" % (stem, n, ext)), n + 1
    return path


# ------------------------------------------------------------------------------------------------- containment
def contain_prefix(pfx, box_folder=None, keep=None):
    """No Z: drive, real (in-box) user folders, and W: -> the box folder. Safe to run on every launch.
    keep: {letter: mount point} of disc images inserted in this box, which stay."""
    keep = keep or {}
    dd = os.path.join(pfx, "dosdevices")
    for letter in os.listdir(dd) if os.path.isdir(dd) else []:
        link = os.path.join(dd, letter)
        if letter.endswith(":") and letter not in ("c:", "w:") and os.path.islink(link):
            target = os.path.realpath(link)
            if letter[0] in keep and target == os.path.realpath(keep[letter[0]]):
                continue
            if box_folder is None or not target.startswith(os.path.realpath(box_folder)):
                os.remove(link)   # z: (the whole Mac) and anything else pointing outside the box
    w = os.path.join(dd, "w:")
    if box_folder:
        if os.path.islink(w) and os.readlink(w) != box_folder:
            os.remove(w)
        if not os.path.lexists(w):
            os.symlink(box_folder, w)
    elif os.path.lexists(w):
        os.remove(w)
    users = os.path.join(pfx, "drive_c", "users")
    for user in os.listdir(users) if os.path.isdir(users) else []:
        if user.startswith(".") or not os.path.isdir(os.path.join(users, user)) or os.path.islink(os.path.join(users, user)):
            continue   # .DS_Store and the like
        for sf in SHELL_FOLDERS:
            p = os.path.join(users, user, sf)
            if os.path.islink(p):         # Wine links these to the Mac's own folders
                os.remove(p)
            os.makedirs(p, exist_ok=True)


def sandbox_profile(name):
    """macOS sandbox for a box's Wine processes: the home folder is off limits except the box itself and the
    MacX engines (read-only). Everything else (system, network, GPU, temp, inserted discs) works as usual."""
    def q(p):
        return '"%s"' % os.path.realpath(p).replace("\\", "\\\\").replace('"', '\\"')
    home, box = os.path.realpath(M.HOME), os.path.realpath(box_path(name))
    # The allows must name the same operations as the denies: a wildcard allow (file-read*) loses to a
    # specific deny (file-read-data) no matter the order.
    read = "file-read-data file-read-metadata file-read-xattr"
    return "\n".join([
        "(version 1)",
        "(allow default)",
        "(deny file-write* (subpath %s))" % q(home),
        "(deny file-read-data (subpath %s))" % q(home),
        "(allow %s file-write* (subpath %s))" % (read, q(box)),
        "(allow %s (subpath %s))" % (read, q(ENGINES_DIR)),
        # keyboard layouts and input methods the user installed, so typing works with their layout
        "(allow %s (subpath %s))" % (read, q(os.path.join(M.HOME, "Library", "Keyboard Layouts"))),
        "(allow %s (subpath %s))" % (read, q(os.path.join(M.HOME, "Library", "Input Methods"))),
    ])


# ------------------------------------------------------------------------------------------------- graphics
# The three ways a game's graphics reach Metal:
#   d3dmetal  Apple's D3DMetal (Game Porting Toolkit): DirectX 10/11/12, 64-bit only. What GTA V Enhanced uses.
#   dxmt      DXMT: DirectX 10/11 straight to Metal, 32- and 64-bit. Covers the 32-bit games D3DMetal can't run.
#   wine      Wine's own: DirectX 9 and older through OpenGL (which Apple runs on Metal), Vulkan through MoltenVK
#             (Vulkan -> Metal), and anything without 3D such as installers.
# DXVK (DirectX -> Vulkan -> MoltenVK) stays in each box's Windows folders, as in the shared setup, for programs the
# registry sets to "native" DirectX 11 (the Steam and Rockstar launchers' browser windows). It is not offered as a
# choice: the macOS DXVK build dates from 2023 and its 32-bit and DirectX 9 paths fail on the MoltenVK that ships with
# Wine 11. An old "dxvk" setting is treated as "dxmt".
CHOICES = ("auto", "d3dmetal", "dxmt", "wine")
DXMT_DLLS = ("d3d11.dll", "dxgi.dll", "d3d10core.dll")


def game_info(exe, data):
    """pe_info for a game's .exe; when the .exe itself names no graphics API (engine games such as Unity, Unreal
    or Unigine load it from their engine DLL), the DLLs next to it are checked too."""
    info = M.pe_info(exe, data)
    if info.get("apis"):
        return info
    apis = set()
    folder = os.path.dirname(exe)
    try:
        dlls = [f for f in os.listdir(folder) if f.lower().endswith(".dll")]
    except OSError:
        dlls = []
    for f in sorted(dlls)[:40]:
        path = os.path.join(folder, f)
        if f.lower().startswith(("d3d", "dxgi", "opengl", "vulkan", "msvc", "vcruntime", "api-ms")):
            continue   # the graphics libraries themselves and runtimes say nothing about the game
        try:
            if os.path.getsize(path) > 96 << 20:
                continue
        except OSError:
            continue
        apis |= set(M.pe_info(path, data).get("apis", []))
    return dict(info, apis=[n for _, n in M.API_PATTERNS if n in apis])


def auto_choice(info):
    apis, bits = set(info.get("apis", [])), info.get("bits")
    if bits != 32 and apis & {"dx10", "dx11", "dx12"} and M.engine_ok("d3dmetal"):
        return "d3dmetal"
    if apis & {"dx10", "dx11"} and dxmt_dir():
        return "dxmt"
    return "wine"


def norm_choice(c):
    c = {"wine11": "wine", "dxvk": "dxmt"}.get(c, c)
    return c if c in CHOICES else "auto"


def engine_env(choice):
    """(engine id, extra environment) for a graphics choice."""
    if choice == "d3dmetal" and M.engine_ok("d3dmetal"):
        return "d3dmetal", {}
    if choice == "dxmt":
        return "wine11", {"WINEDLLOVERRIDES": M.BASE_OVERRIDES + ";d3d11,dxgi,d3d10core=n,b"}
    return "wine11", {}


def dxmt_dir():
    found = sorted(glob.glob(os.path.join(M.ROOT, "gfx", "dxmt", "v*")))
    return found[-1] if found else None


def copy_dxvk(win_dir):
    """DXVK's d3d11/dxgi/d3d10core in the Windows folders, as in the shared setup: programs that are set to use
    "native" DirectX 11 (e.g. the Steam and Rockstar launchers' browser windows) get DXVK; everything else keeps
    Wine's builtin (or D3DMetal's) versions, because Wine prefers builtins for DLLs in the Windows folders."""
    for arch, d in (("x64", "system32"), ("x32", "syswow64")):
        for dll in M.GFX_DLLS:
            src, dst = os.path.join(M.DXVK_FULL, arch, dll), os.path.join(win_dir, d, dll)
            if os.path.exists(src) and os.path.isdir(os.path.dirname(dst)) and M.sha(src) != M.sha(dst):
                shutil.copy2(src, dst)


def dxmt_bytes(arch, dll):
    src_root = dxmt_dir()
    src = os.path.join(src_root, arch, dll) if src_root else ""
    if not os.path.exists(src):
        return None
    with open(src, "rb") as f:
        data = bytearray(f.read())
    if data[0x40:0x50] == b"Wine builtin DLL":
        data[0x40:0x50] = bytes(16)
    return bytes(data)


def remove_dxmt(exe_dir):
    """Takes our DXMT copies away from a program's folder again (only files identical to ours), because Wine
    loads DLLs from a program's own folder first, whatever the engine."""
    for dll in DXMT_DLLS:
        dst = os.path.join(exe_dir, dll)
        if not os.path.isfile(dst):
            continue
        with open(dst, "rb") as f:
            data = f.read()
        if any(data == dxmt_bytes(arch, dll) for arch in ("x86_64-windows", "i386-windows")):
            os.remove(dst)


def place_dxmt(exe_dir, bits):
    """DXMT's DLLs next to a program that runs with the dxmt choice (32- or 64-bit build, with Wine's "builtin"
    marker removed so they load as native). Only that program sees them; remove_dxmt() takes them away again
    when it runs another way."""
    if not os.path.isdir(exe_dir):
        return
    arch = "i386-windows" if bits == 32 else "x86_64-windows"
    for dll in DXMT_DLLS:
        data, dst = dxmt_bytes(arch, dll), os.path.join(exe_dir, dll)
        if data is None:
            continue
        try:
            with open(dst, "rb") as f:
                if f.read() == data:
                    continue
        except OSError:
            pass
        with open(dst, "wb") as f:
            f.write(data)


# ------------------------------------------------------------------------------------------------- template
def template_stamp():
    """Changes when the engines change, so the template is rebuilt."""
    parts = [M.sha(os.path.join(M.D3DM_APP, "Contents", "Resources", "wine", "lib", "wine", "x86_64-unix",
                                "ntdll.so")) or "", M.sha(M.NTDLX) or ""]
    return "-".join([TEMPLATE_VERSION] + [p[:12] for p in parts])


def build_template():
    if os.path.isfile(os.path.join(TEMPLATE, ".stamp")) and open(os.path.join(TEMPLATE, ".stamp")).read() == template_stamp():
        return
    if not (M.engine_ok("d3dmetal") and M.engine_ok("wine11")):
        M.fail("Set up MacX first (the engines aren't installed).")
    tmp = TEMPLATE + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    env = M.wine_env({"WINEPREFIX": tmp}, "d3dmetal")
    subprocess.run([M.ENGINES["d3dmetal"]["wine"], "wineboot", "--init"], env=env, timeout=600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([M.ENGINES["d3dmetal"]["server"], "-w"], env=env, timeout=600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sys32 = os.path.join(tmp, "drive_c", "windows", "system32")
    lib = os.path.join(M.D3DM_APP, "Contents", "Resources", "wine", "lib", "wine", "x86_64-windows")
    shutil.copy2(M.NTDLX, os.path.join(sys32, "ntdlx.dll"))
    for dll in ("nvapi64.dll", "nvngx.dll", "d3dmt.dll"):   # loaded by full path by some games
        if os.path.exists(os.path.join(lib, dll)):
            shutil.copy2(os.path.join(lib, dll), os.path.join(sys32, dll))
    copy_dxvk(os.path.join(tmp, "drive_c", "windows"))
    contain_prefix(tmp)
    with open(os.path.join(tmp, ".stamp"), "w") as f:
        f.write(template_stamp())
    shutil.rmtree(TEMPLATE, ignore_errors=True)
    os.rename(tmp, TEMPLATE)


# ------------------------------------------------------------------------------------------------- boxes
def box_names():
    if not os.path.isdir(BOXES):
        return []
    return sorted((n for n in os.listdir(BOXES) if not n.startswith(".") and is_box(box_path(n))), key=str.lower)


def check_box(name):
    if not name or "/" in name or not is_box(box_path(name)):
        M.fail("There's no box called “%s”." % name)


def new_box(name=None):
    build_template()
    os.makedirs(BOXES, exist_ok=True)
    if not name:
        n = 1
        while os.path.exists(box_path("Box %d" % n)):
            n += 1
        name = "Box %d" % n
    name = re.sub(r'[/:\\]', "-", name).strip() or "Box"
    if os.path.exists(box_path(name)):
        M.fail("A box called “%s” already exists." % name)
    os.makedirs(meta(name))
    subprocess.run(["cp", "-cR", TEMPLATE, prefix(name)], check=True)   # APFS clone: instant, shares blocks
    os.remove(os.path.join(prefix(name), ".stamp"))
    new_machine_guid(prefix(name))
    finish_box(name)
    return name


def finish_box(name, extra=None):
    contain_prefix(prefix(name), box_path(name))
    with open(os.path.join(box_path(name), ".windows-label"), "w") as f:
        f.write(name[:32])
    save_box(name, dict({"name": name, "created": time.time(), "items": {}, "detect": {}}, **(extra or {})))


def clone_main(name=None):
    """A box that starts as a copy of the shared setup (Steam, installed games, saves). It is an APFS clone:
    instant and taking no extra disk until either side changes, and the shared setup is not touched."""
    src = os.path.realpath(M.PREFIX)
    if not os.path.isdir(os.path.join(src, "drive_c")):
        M.fail("There is no shared setup to copy.")
    if prefix_processes(src):
        M.fail("Quit Steam and any running programs first, so the copy is consistent.")
    os.makedirs(BOXES, exist_ok=True)
    name = os.path.basename(unique_path(BOXES, re.sub(r'[/:\\]', "-", name or "My Setup").strip() or "My Setup"))
    os.makedirs(meta(name))
    r = subprocess.run(["cp", "-cR", src, prefix(name)], stderr=subprocess.PIPE)
    if r.returncode != 0:
        shutil.rmtree(box_path(name), ignore_errors=True)
        M.fail("Couldn't copy the setup: %s" % r.stderr.decode("utf-8", "replace")[-300:])
    for junk in ("dosdevices/z:",):
        p = os.path.join(prefix(name), junk)
        if os.path.islink(p):
            os.remove(p)
    finish_box(name, {"clonedFrom": src})   # same PC as the original, so the MachineGuid is kept
    return name


def new_machine_guid(pfx):
    """Clones share the template's MachineGuid; a separate PC gets its own (Windows makes one per install)."""
    reg = os.path.join(pfx, "system.reg")
    try:
        with open(reg, encoding="utf-8", errors="surrogateescape") as f:
            text = f.read()
    except OSError:
        return
    text = re.sub(r'^"MachineGuid"="[^"]*"$', '"MachineGuid"="%s"' % uuid.uuid4(), text, count=1, flags=re.M)
    with open(reg + ".tmp", "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)
    os.replace(reg + ".tmp", reg)   # replaces the clone's copy only; the template keeps its own file


def add_files(name, paths):
    """Copies files/folders into the box (APFS clones when on the same disk, so big games copy instantly)."""
    check_box(name)
    added = []
    for p in paths:
        p = os.path.abspath(p)
        if not os.path.exists(p):
            M.fail("Not found: %s" % p)
        if os.path.realpath(p).startswith(os.path.realpath(box_path(name)) + os.sep):
            continue   # already in this box
        dest = unique_path(box_path(name), os.path.basename(p.rstrip("/")))
        r = subprocess.run(["cp", "-cR", p, dest], stderr=subprocess.PIPE)
        if r.returncode != 0:
            r = subprocess.run(["cp", "-R", p, dest], stderr=subprocess.PIPE)   # other disk: a real copy
        if r.returncode != 0:
            M.fail("Couldn't copy %s: %s" % (os.path.basename(p), r.stderr.decode("utf-8", "replace")[-200:]))
        added.append(os.path.basename(dest))
    return added


# ------------------------------------------------------------------------------------------------- processes
def processes_by_prefix(procs=None):
    """{real prefix path: [wine process dicts]} for every Wine process."""
    procs = procs if procs is not None else M.wine_processes()
    owner = M.process_prefixes(procs)
    res = {}
    for p in procs:
        if p["pid"] in owner:
            res.setdefault(owner[p["pid"]], []).append(p)
    return res


def prefix_processes(pfx):
    return [p["pid"] for p in processes_by_prefix().get(os.path.realpath(pfx), [])]


def box_processes(name):
    """pids of Wine processes running in this box."""
    return prefix_processes(prefix(name))


def kill(pids, sig=signal.SIGKILL):
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


def stop_box(name):
    env = M.wine_env({"WINEPREFIX": prefix(name)}, "d3dmetal")
    subprocess.run([M.ENGINES["d3dmetal"]["server"], "-k"], env=env, timeout=30,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    kill(box_processes(name))
    task = read_task(name)
    if task and not task.get("finished"):
        kill([task["pid"]])


def orphan_cleanup():
    """Wine processes whose box folder was deleted (e.g. moved to the Trash in Finder) are stopped, and their
    Wine server files and inserted disc images are cleaned up."""
    live = [os.path.realpath(prefix(n)) for n in box_names()]
    killed = []
    for pfx, procs in processes_by_prefix().items():
        if "/%s/prefix" % META in pfx and pfx not in live:
            kill([p["pid"] for p in procs])
            killed += [p["pid"] for p in procs]
    stale_server_dirs(live)
    stale_disc_images(live)
    return killed


server_dir_prefix = M.server_dir_prefix


def stale_server_dirs(live):
    """Remove the server dirs of deleted boxes (folder gone, or sitting in the Trash), so a deleted box leaves
    nothing behind outside its folder. Dirs of other Wine prefixes are left alone."""
    base = "/private/tmp/.wine-%d" % os.getuid()
    try:
        entries = os.listdir(base)
    except OSError:
        return
    for d in entries:
        p = server_dir_prefix(d)
        if p == "":
            continue
        if p is not None and not ("/%s/prefix" % META in p and p not in live):
            continue
        sock = os.path.join(base, d, "socket")
        if os.path.exists(sock) and subprocess.run(["lsof", "-t", sock], stdout=subprocess.PIPE,
                                                   stderr=subprocess.DEVNULL).stdout.strip():
            continue   # a wineserver is still listening
        shutil.rmtree(os.path.join(base, d), ignore_errors=True)


def stale_disc_images(live):
    """Eject disc images that were inserted into a box which has since been deleted."""
    r = subprocess.run(["hdiutil", "info", "-plist"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        images = plistlib.loads(r.stdout).get("images", [])
    except Exception:
        return
    live_boxes = [os.path.dirname(os.path.dirname(p)) for p in live]
    for im in images:
        path = os.path.realpath(im.get("image-path", ""))
        in_boxes = path.startswith(os.path.realpath(BOXES) + os.sep)
        in_trash = path.startswith(os.path.join(os.path.realpath(M.HOME), ".Trash") + os.sep)
        if not (in_boxes or in_trash) or any(path.startswith(b + os.sep) for b in live_boxes):
            continue
        top = path.split(os.sep)[:len((os.path.realpath(BOXES) if in_boxes else os.path.join(
            os.path.realpath(M.HOME), ".Trash")).split(os.sep)) + 1]
        if in_trash and not os.path.isdir(os.path.join(os.sep.join(top), META)):
            continue   # some other disc image the user trashed, not one of ours
        devs = [e["dev-entry"] for e in im.get("system-entities", []) if e.get("dev-entry")]
        if devs:
            subprocess.run(["hdiutil", "detach", min(devs, key=len), "-force"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=60)


def delete_box(name):
    check_box(name)
    stop_box(name)
    for iid in list(load_state(name)["disks"]):
        eject(name, iid)
    dest = os.path.join(M.HOME, ".Trash", "%s %s" % (name, time.strftime("%H%M%S")))
    shutil.move(box_path(name), dest)


def rename_box(name, new):
    new = re.sub(r'[/:\\]', "-", new).strip()
    if not new or os.path.exists(box_path(new)):
        M.fail("That name is empty or already used.")
    stop_box(name)
    os.rename(box_path(name), box_path(new))
    contain_prefix(prefix(new), box_path(new))
    data = load_box(new)
    data["name"] = new
    save_box(new, data)


# ------------------------------------------------------------------------------------------------- running things
def win_to_unix(name, win):
    """C:\\..., W:\\... or D:\\... (an inserted disc) inside this box -> Mac path, or None."""
    win = win.strip().strip('"')
    if len(win) < 3 or win[1] != ":":
        return None
    root = os.path.join(prefix(name), "dosdevices", win[0].lower() + ":")
    if not os.path.exists(root):
        return None
    return os.path.join(os.path.realpath(root), *[s for s in win[3:].split("\\") if s])


def unix_to_win(name, path):
    real = os.path.realpath(path)
    for root, letter in ((os.path.realpath(os.path.join(prefix(name), "drive_c")), "C"),
                         (os.path.realpath(box_path(name)), "W")):
        if real == root or real.startswith(root + os.sep):
            rest = os.path.relpath(real, root)
            return "%s:\\%s" % (letter, "" if rest == "." else rest.replace(os.sep, "\\"))
    for letter, d in disc_letters(name).items():
        root = os.path.realpath(d)
        if real.startswith(root + os.sep):
            return "%s:\\%s" % (letter.upper(), os.path.relpath(real, root).replace(os.sep, "\\"))
    return None


def disc_letters(name):
    return {d["letter"]: d["mount"] for d in load_state(name)["disks"].values()}


ROCKSTAR_EXES = ("Launcher.exe", "SocialClubHelper.exe", "SocialClubHelper_real.exe", "RockstarService.exe")
ROCKSTAR_OVERRIDES = {"d3d11": "native,builtin", "dxgi": "native,builtin", "d3d10core": "native,builtin",
                      "d3d12": "", "nvapi64": "", "atidxx64": ""}


def launcher_fixes(name):
    """What the Steam and Rockstar launchers need to draw under Wine, the same fixes the shared setup gets from
    Repair: their Chromium helpers are wrapped (--in-process-gpu), and the Rockstar launcher's windows use DXVK
    with D3DMetal's DirectX 12 / GPU-vendor DLLs hidden from it (the game itself keeps D3DMetal). Applied when
    those launchers get installed into a box, e.g. by a game's installer."""
    c = os.path.join(prefix(name), "drive_c")
    M.apply_cef_wrappers(c)
    if not os.path.isdir(os.path.join(c, "Program Files", "Rockstar Games", "Launcher")):
        return
    try:
        with open(os.path.join(prefix(name), "user.reg"), encoding="utf-8", errors="replace") as f:
            reg = f.read()
    except OSError:
        reg = ""
    missing = [e for e in ROCKSTAR_EXES if "AppDefaults\\\\%s\\\\DllOverrides" % e not in reg]   # doubled in .reg
    if not missing:
        return
    lines = ["Windows Registry Editor Version 5.00", ""]
    for e in missing:
        lines.append("[HKEY_CURRENT_USER\\Software\\Wine\\AppDefaults\\%s\\DllOverrides]" % e)
        lines += ['"%s"="%s"' % kv for kv in ROCKSTAR_OVERRIDES.items()]
        lines.append("")
    with open(meta(name, "launcher-fixes.reg"), "w", encoding="utf-16") as f:
        f.write("\r\n".join(lines))
    subprocess.run([M.ENGINES["wine11"]["wine"], "regedit", "/S", "W:\\%s\\launcher-fixes.reg" % META],
                   env=M.wine_env({"WINEPREFIX": prefix(name)}, "wine11"), stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120)


def exe_dirs(folder, limit=12):
    """Folders inside a game that hold programs (a launcher in one, the game itself in another)."""
    dirs = []
    for e in M.list_exes(folder)[:200]:
        d = os.path.dirname(os.path.join(folder, e))
        if d not in dirs:
            dirs.append(d)
    return dirs[:limit]


def spawn(name, choice, cmd, cwd, log_name, bits=None, game_dir=None):
    """Runs a Windows command in the box: sandboxed, on the engine for this graphics choice. Returns the Popen."""
    eng, extra = engine_env(choice)
    contain_prefix(prefix(name), box_path(name), keep=disc_letters(name))
    copy_dxvk(os.path.join(prefix(name), "drive_c", "windows"))
    launcher_fixes(name)
    dirs = [cwd] + (exe_dirs(game_dir) if game_dir and os.path.isdir(game_dir) and game_dir != box_path(name) else [])
    for d in dict.fromkeys(dirs):
        if choice == "dxmt":
            place_dxmt(d, bits)
        elif os.path.isdir(d):
            remove_dxmt(d)
    os.makedirs(meta(name, "logs"), exist_ok=True)
    env = M.wine_env(dict({"WINEPREFIX": prefix(name), "WINEDEBUG": "fixme-all"},
                          **({"MTL_HUD_ENABLED": "1"} if M.load_config().get("hud") else {}), **extra), eng)
    profile = meta(name, "sandbox.sb")
    with open(profile, "w") as f:
        f.write(sandbox_profile(name))
    log = open(meta(name, "logs", safe_name(log_name) + ".log"), "wb")
    log.write(("$ [%s, %s] %s\n" % (M.ENGINES[eng]["short"], choice, " ".join(cmd))).encode())
    log.flush()
    return subprocess.Popen(["/usr/bin/sandbox-exec", "-f", profile, M.ENGINES[eng]["wine"]] + cmd,
                            cwd=cwd if os.path.isdir(cwd) else box_path(name), env=env, stdout=log, stderr=log,
                            stdin=subprocess.DEVNULL, start_new_session=True)


# ------------------------------------------------------------------------------------------------- files on W:
ARCHIVE_RE = re.compile(r"\.(zip|7z|rar|tar|tgz|tbz2?|txz|cab|tar\.(gz|bz2|xz))$|\.(7z|zip)\.001$", re.I)
ARCHIVE_STEM_RE = re.compile(r"(\.part0*1)?\.(zip|7z|rar|tar|tgz|tbz2?|txz|cab|tar\.(gz|bz2|xz))(\.001)?$", re.I)
MORE_PARTS_RE = re.compile(r"\.(7z|zip)\.(?!001$)\d{3}$|\.part(?!0*1\.rar$)\d+\.rar$|\.r\d\d$", re.I)
DISK_RE = re.compile(r"\.(iso|img)$", re.I)
DISC_SETUP_RE = re.compile(r"(setup|install|autorun)\.(exe|msi)$", re.I)


INSTALLER_MARKS = [m for t in ("Inno Setup", "Nullsoft", "InstallShield", "Setup Factory", "Smart Install Maker",
                                 "Wise Installation") for m in (t.encode(), t.encode("utf-16-le"))] + [
    b".wixburn", b";!@Install@!UTF-8!", b"NullsoftInst"]


def looks_like_installer(path, data):
    """True when a program was made with a common installer tool (Inno Setup, which repacks use, NSIS,
    InstallShield, WiX, 7-Zip SFX, ...), found by the tool's marks in the first and last 2 MB. Cached."""
    try:
        st = os.stat(path)
    except OSError:
        return False
    key = "inst:" + path
    c = data["detect"].get(key)
    if c and c.get("mtime") == int(st.st_mtime) and c.get("size") == st.st_size:
        return c["installer"]
    with open(path, "rb") as f:
        blob = f.read(2 << 20)
        if st.st_size > 4 << 20:
            f.seek(st.st_size - (2 << 20))
            blob += f.read()
    found = any(m in blob for m in INSTALLER_MARKS)
    data["detect"][key] = {"mtime": int(st.st_mtime), "size": st.st_size, "installer": found}
    return found


def pick_setup(setups):
    return sorted(setups, key=lambda e: (e.count(os.sep), not re.match(r"setup\.exe$", os.path.basename(e), re.I),
                                         e.lower()))[0]


def file_items(name, data, st, running):
    """Everything in the box folder (drive W:), classified."""
    folder = box_path(name)
    items = []
    for entry in sorted(os.listdir(folder), key=str.lower):
        if entry.startswith(".") or entry in M.HIDDEN or MORE_PARTS_RE.search(entry) or entry.lower() in DXMT_DLLS:
            continue
        path = os.path.join(folder, entry)
        cfg, state = data["items"].get(entry, {}), st["items"].get(entry, {})
        stem, ext = os.path.splitext(entry)
        launch_bat = None
        exes, main, base = [], None, folder
        if os.path.isdir(path):
            base = path
            exes = M.list_exes(path) + sorted(os.path.relpath(p, path) for p in glob.glob(os.path.join(path, "*.msi")))
            playable = [e for e in exes if e.lower().endswith(".exe") and not M.SKIP_EXE.search(os.path.basename(e))]
            setups = [e for e in exes if e.lower().endswith(".msi") or M.INSTALLER_RE.search(os.path.basename(e))]
            if playable and len(playable) <= 3 and all(looks_like_installer(os.path.join(path, e), data) for e in playable):
                setups, playable = playable + setups, []   # e.g. "Game Installer.exe" + its data files
            top_setups = [e for e in setups if os.sep not in e]
            if playable and top_setups and (glob.glob(os.path.join(glob.escape(path), "*.bin")) or
                                            not any(os.sep not in e for e in playable)):
                # repack / GOG layout: setup.exe + data-1.bin… at the top, helpers such as MD5\QuickSFV.exe below
                setups, playable = top_setups + [e for e in setups if e not in top_setups], []
            if cfg.get("kind") == "installer" and (playable or setups):
                setups, playable = setups or playable, []
            if playable:
                kind = "folder"
                main = cfg.get("exe") if cfg.get("exe") in exes else M.guess_main_exe(path, playable)
                bats = [b for b in os.listdir(path) if b.lower().endswith((".bat", ".cmd"))]
                if not cfg.get("exe") and len(bats) == 1 and not any(os.sep not in e for e in playable):
                    try:
                        with open(os.path.join(path, bats[0]), encoding="latin-1") as f:
                            text = f.read(4096).lower()
                    except OSError:
                        text = ""
                    if any(os.path.basename(e).lower() in text for e in playable):
                        launch_bat = bats[0]   # e.g. heaven.bat: cd bin, start browser_x86.exe -config ...
            elif setups:
                kind = "installer"
                main = cfg.get("exe") if cfg.get("exe") in exes else pick_setup(setups)
            else:
                kind = "files"
        elif ARCHIVE_RE.search(entry):
            kind = "archive"
        elif DISK_RE.search(entry):
            kind = "disk"
        else:
            kind = M.EXT_KIND.get(ext.lower(), "file")
            if kind == "program" and (M.INSTALLER_RE.search(entry) or cfg.get("kind") == "installer"
                                      or looks_like_installer(path, data)):
                kind = "installer"
            if kind == "installer" and cfg.get("kind") == "program" and ext.lower() == ".exe":
                kind = "program"   # the user says it's a program after all
            if kind in ("program", "installer"):
                exes, main = [entry], entry
        info = {"apis": []}
        if main and main.lower().endswith(".exe") and kind in ("program", "folder"):
            info = game_info(os.path.join(base, main), data)
        win = ("W:\\" + os.path.relpath(os.path.join(base, main), folder).replace(os.sep, "\\")) if main else None
        procs = [p for p in running if win and p["path"].lower() == win.lower()]
        disk = st["disks"].get(entry)
        s = state.get("state")
        if kind == "archive":
            status = ("Unpacked into “%s”" % state["into"]) if s == "unpacked" and os.path.exists(
                os.path.join(folder, state.get("into", ""))) else (state.get("message") if s == "failed" else "Not unpacked yet")
        elif kind in ("installer", "disk"):
            status = {"installed": "Installed", "failed": state.get("message", "Setup failed"),
                      "unpacked": state.get("message", "Unpacked")}.get(s, "Not installed yet")
            if disk:
                status += " · in drive %s:" % disk["letter"].upper()
        else:
            status = ""
        items.append({
            "id": entry, "name": stem if os.path.isfile(path) and kind not in ("archive", "disk") else entry,
            "kind": kind, "path": path, "winPath": win, "mainExe": main, "exes": exes,
            "api": M.api_label(info.get("apis", [])), "bits": info.get("bits"),
            "choice": norm_choice(cfg.get("engine", "auto")), "auto": auto_choice(info),
            "args": cfg.get("args", ""), "kindSetting": cfg.get("kind", "auto"),
            "running": bool(procs), "pids": [p["pid"] for p in procs],
            "state": s or "", "status": status, "pending": kind in ("archive", "installer", "disk") and s not in (
                "unpacked", "installed"),
            "playable": kind in ("program", "folder") and bool(main),
            "launch": launch_bat,
            "log": meta(name, "logs", safe_name(entry) + ".log"),
        })
    return items


# ------------------------------------------------------------------------------------------------- installed games
def read_lnk(path):
    """(target path, arguments, working dir) from a Windows .lnk shortcut, or None."""
    try:
        with open(path, "rb") as f:
            b = f.read(1 << 16)
    except OSError:
        return None
    if len(b) < 0x4C or b[:4] != b"\x4c\x00\x00\x00":
        return None
    u32 = lambda o: int.from_bytes(b[o:o + 4], "little")
    u16 = lambda o: int.from_bytes(b[o:o + 2], "little")
    flags, pos, target = u32(0x14), 0x4C, None
    if flags & 0x01:                          # HasLinkTargetIDList
        pos += 2 + u16(pos)
    if flags & 0x02:                          # HasLinkInfo
        li = pos
        size, hsize, liflags = u32(li), u32(li + 4), u32(li + 8)
        if liflags & 1:
            if hsize >= 0x24 and u32(li + 0x1C):
                o = li + u32(li + 0x1C)
                e = o
                while e + 1 < len(b) and b[e:e + 2] != b"\0\0":
                    e += 2
                target = b[o:e].decode("utf-16-le", "replace").split("\x00", 1)[0]
            else:
                o = li + u32(li + 0x10)
                target = b[o:b.index(b"\0", o)].decode("mbcs" if os.name == "nt" else "latin-1", "replace")
        pos += size
    unicode = flags & 0x80
    strings = {}
    for bit, key in ((0x04, "name"), (0x08, "rel"), (0x10, "workdir"), (0x20, "args"), (0x40, "icon")):
        if flags & bit:
            n = u16(pos)
            pos += 2
            raw = b[pos:pos + (n * 2 if unicode else n)]
            # Wine's shortcut writer counts a terminating NUL that Windows' doesn't; drop it either way
            strings[key] = raw.decode("utf-16-le" if unicode else "latin-1", "replace").split("\x00", 1)[0]
            pos += n * 2 if unicode else n
    if not target and strings.get("rel"):
        target = strings["rel"]
    return (target, strings.get("args", ""), strings.get("workdir", "")) if target else None


def reg_unescape(v):
    return re.sub(r"\\(x[0-9a-fA-F]{1,4}|.)", lambda m: chr(int(m.group(1)[1:], 16)) if m.group(1)[0] == "x"
                  and len(m.group(1)) > 1 else m.group(1), v)


UNINSTALL_SKIP = re.compile(r"^(wine\b|microsoft (visual c\+\+|\.net)|directx|steamworks|vulkan|nvidia|amd )", re.I)


def uninstall_entries(pfx):
    """Programs from Windows' "installed programs" list (both the 64-bit and 32-bit halves of the registry)."""
    try:
        with open(os.path.join(pfx, "system.reg"), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    res = []
    for m in re.finditer(r"^\[Software\\\\(?:Wow6432Node\\\\)?Microsoft\\\\Windows\\\\CurrentVersion\\\\Uninstall\\\\"
                         r"([^\]]+)\][^\n]*\n(.*?)(?=^\[|\Z)", text, re.M | re.S):
        body = m.group(2)
        if re.search(r'^"SystemComponent"=dword:0*1\s*$', body, re.M):
            continue
        vals = {k: reg_unescape(v) for k, v in re.findall(r'^"([^"]+)"=(?:str\(2\):)?"((?:[^"\\]|\\.)*)"', body, re.M)}
        if vals.get("DisplayName") and not UNINSTALL_SKIP.search(vals["DisplayName"]):
            res.append(vals)
    return res


def steam_manifests(pfx):
    """{appid: (name, install folder)} for Steam games installed in this box."""
    res = {}
    for acf in glob.glob(os.path.join(pfx, "drive_c", "Program Files (x86)", "Steam", "steamapps", "appmanifest_*.acf")):
        try:
            with open(acf, encoding="utf-8", errors="replace") as f:
                t = f.read()
        except OSError:
            continue
        aid = re.search(r'"appid"\s+"(\d+)"', t)
        nm = re.search(r'"name"\s+"([^"]*)"', t)
        inst = re.search(r'"installdir"\s+"([^"]*)"', t)
        if aid and nm and inst:
            res[aid.group(1)] = (nm.group(1), os.path.join(os.path.dirname(acf), "common", inst.group(1)))
    return res


def installed_apps(name, data, running):
    """Games and programs installed inside the box: from Start Menu / Desktop shortcuts, Windows' installed
    programs list, and Steam."""
    pfx = prefix(name)
    c = os.path.join(pfx, "drive_c")
    users = [u for u in os.listdir(os.path.join(c, "users")) if u != "Public"] if os.path.isdir(os.path.join(c, "users")) else []
    roots = [os.path.join(c, "ProgramData", "Microsoft", "Windows", "Start Menu", "Programs"),
             os.path.join(c, "users", "Public", "Desktop")]
    for u in users:
        roots += [os.path.join(c, "users", u, "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs"),
                  os.path.join(c, "users", u, "Desktop")]
    found, steam_games = {}, {}
    manifests = steam_manifests(pfx)

    def add(exe_unix, title, args="", workdir="", source=""):
        if not exe_unix or not exe_unix.lower().endswith(".exe") or not os.path.isfile(exe_unix):
            return
        base = os.path.basename(exe_unix)
        if M.SKIP_EXE.search(base) and base.lower() != "steam.exe":
            return
        key = os.path.realpath(exe_unix).lower()
        if key in found:
            return
        win = unix_to_win(name, exe_unix)
        if not win or win.upper().startswith("W:"):
            return   # programs on W: are listed with the box's files
        found[key] = {"exe": exe_unix, "win": win, "name": title, "args": args, "workdir": workdir, "source": source}

    for root in roots:
        for dirpath, _, files in os.walk(root):
            for fn in sorted(files):
                p = os.path.join(dirpath, fn)
                low = fn.lower()
                if M.UNWANTED_LNK.search(fn):
                    continue
                if low.endswith(".lnk"):
                    lk = read_lnk(p)
                    if lk:
                        add(win_to_unix(name, lk[0]), fn[:-4], lk[1], lk[2], "shortcut")
                elif low.endswith(".url"):
                    try:
                        with open(p, encoding="utf-8", errors="replace") as f:
                            m = re.search(r"^URL=steam://rungameid/(\d+)", f.read(), re.M)
                    except OSError:
                        m = None
                    if m:
                        steam_games[m.group(1)] = fn[:-4]
    for vals in uninstall_entries(pfx):
        icon = re.sub(r",\s*-?\d+$", "", vals.get("DisplayIcon", "")).strip('"')
        exe = win_to_unix(name, icon) if icon.lower().endswith(".exe") and not re.search(r"unins", icon, re.I) else None
        if not exe and vals.get("InstallLocation"):
            d = win_to_unix(name, vals["InstallLocation"].rstrip("\\") + "\\")
            if d and os.path.isdir(d):
                playable = [e for e in M.list_exes(d) if not M.SKIP_EXE.search(os.path.basename(e))]
                g = M.guess_main_exe(d, playable) if playable else None
                exe = os.path.join(d, g) if g else None
        add(exe, vals["DisplayName"], source="installed")
    for aid, (title, _) in manifests.items():
        if aid not in steam_games and aid != "228980":   # 228980 = Steamworks redistributables
            steam_games[aid] = title

    apps = []
    for a in found.values():
        cfg = data["items"].get(a["win"], {})
        info = game_info(a["exe"], data)
        procs = [p for p in running if p["path"].lower() == a["win"].lower()]
        is_steam = os.path.basename(a["exe"]).lower() == "steam.exe"
        apps.append({"id": a["win"], "name": a["name"], "kind": "steam" if is_steam else "app", "path": a["exe"],
                     "winPath": a["win"], "api": M.api_label(info.get("apis", [])), "bits": info.get("bits"),
                     "choice": norm_choice(cfg.get("engine", "auto")),
                     "auto": "d3dmetal" if is_steam and M.engine_ok("d3dmetal") else auto_choice(info),
                     "args": cfg.get("args", a["args"]), "running": bool(procs), "pids": [p["pid"] for p in procs],
                     "source": a["source"], "log": meta(name, "logs", safe_name(a["name"]) + ".log")})
    for aid, title in steam_games.items():
        folder = manifests.get(aid, (None, None))[1]
        win_dir = unix_to_win(name, folder) if folder else None
        procs = [p for p in running if win_dir and p["path"].lower().startswith(win_dir.lower() + "\\")]
        cfg = data["items"].get("steam:" + aid, {})
        apps.append({"id": "steam:" + aid, "name": title, "kind": "steamgame", "path": folder or "",
                     "winPath": win_dir, "api": "Steam", "bits": None, "choice": norm_choice(cfg.get("engine", "auto")),
                     "auto": "d3dmetal" if M.engine_ok("d3dmetal") else "wine", "args": "", "running": bool(procs),
                     "pids": [p["pid"] for p in procs], "source": "steam",
                     "log": meta(name, "logs", "steam.log")})
    return sorted(apps, key=lambda a: (a["kind"] == "steam", a["name"].lower()))


# ------------------------------------------------------------------------------------------------- actions
def box_view(name, procs_by_prefix=None):
    data, st = load_box(name), load_state(name)
    pbp = procs_by_prefix if procs_by_prefix is not None else processes_by_prefix()
    running = pbp.get(os.path.realpath(prefix(name)), [])
    before = json.dumps(data["detect"], sort_keys=True)
    files = file_items(name, data, st, running)
    apps = installed_apps(name, data, running)
    if json.dumps(data["detect"], sort_keys=True) != before:
        save_box(name, data)   # only when the detection cache changed (the app watches this folder)
    for it in files + apps:
        it["effective"] = it["auto"] if it["choice"] == "auto" else it["choice"]
    return {"name": name, "path": box_path(name), "running": bool(running), "files": files, "apps": apps,
            "task": read_task(name), "pending": sum(1 for f in files if f["pending"])}


def find(name, item_id):
    v = box_view(name)
    it = next((i for i in v["files"] + v["apps"] if i["id"] == item_id), None)
    if not it:
        M.fail("“%s” isn't in %s any more." % (item_id, name))
    return it


def play(name, item_id, extra_args=None):
    check_box(name)
    it = find(name, item_id)
    if it["running"]:
        return {"message": "%s is already running." % it["name"]}
    choice = it["auto"] if it["choice"] == "auto" else it["choice"]
    try:
        args = shlex.split(it.get("args") or "") + list(extra_args or [])
    except ValueError:
        M.fail("The launch options have an unmatched quote.")
    if it["kind"] == "steamgame":
        M.apply_cef_wrappers(os.path.join(prefix(name), "drive_c"))
        cmd, cwd = [STEAM_EXE] + STEAM_ARGS + ["steam://rungameid/%s" % item_id.split(":", 1)[1]], box_path(name)
    elif it["kind"] == "steam":
        M.apply_cef_wrappers(os.path.join(prefix(name), "drive_c"))
        cmd, cwd = [it["winPath"]] + STEAM_ARGS + args, os.path.dirname(it["path"])
    elif it["kind"] == "folder" and it.get("launch"):
        bat = os.path.join(it["path"], it["launch"])
        cmd, cwd = ["cmd", "/c", unix_to_win(name, bat)] + args, it["path"]
    elif it["kind"] in ("program", "folder", "app"):
        exe = it["path"] if it["kind"] == "app" else os.path.join(
            it["path"] if it["kind"] == "folder" else box_path(name), it["mainExe"])
        cmd, cwd = [it["winPath"]] + args, os.path.dirname(exe)
    elif it["kind"] in ("shortcut", "file"):
        cmd, cwd, choice = ["start", "/unix", it["path"]], box_path(name), "wine"
    elif it["kind"] == "script":
        cmd, cwd, choice = ["wineconsole", "cmd", "/c", it["winPath"] or ""], box_path(name), "wine"
    elif it["kind"] in ("installer", "archive", "disk"):
        return start_setup(name, [item_id])
    else:
        M.fail("Nothing to run in “%s”." % it["name"])
    game_dir = it["path"] if it["kind"] == "folder" else (os.path.dirname(it["path"]) if it["kind"] == "app" else None)
    spawn(name, choice, cmd, cwd, "steam" if it["kind"] in ("steam", "steamgame") else it["name"] if it["kind"] in (
        "app",) else it["id"], bits=it.get("bits"), game_dir=game_dir)
    how = {"d3dmetal": "D3DMetal → Metal", "dxmt": "DXMT → Metal", "wine": "Wine"}[choice]
    return {"message": "Starting %s in %s (%s). The first start can take a minute." % (it["name"], name, how)}


def stop_item(name, item_id):
    it = find(name, item_id)
    kill(it["pids"], signal.SIGTERM)
    time.sleep(2)
    kill(find(name, item_id)["pids"])
    return {"message": "Closed %s." % it["name"]}


def set_item(name, item_id, field, value):
    check_box(name)
    if field not in ("engine", "args", "exe", "kind"):
        M.fail("unknown setting")
    if field == "kind" and value not in ("auto", "installer", "program"):
        M.fail("kind must be auto, installer or program")
    if field == "engine" and norm_choice(value) != value:
        M.fail("unknown engine")
    data = load_box(name)
    entry = data["items"].setdefault(item_id, {})
    if value in ("", "auto") and field != "args":
        entry.pop(field, None)
    else:
        entry[field] = value
    save_box(name, data)
    return {"message": "Saved."}


# ---- discs
def mount(name, item_id):
    st = load_state(name)
    d = st["disks"].get(item_id)
    if d and os.path.isdir(d["mount"]):
        return d
    path = os.path.join(box_path(name), item_id)
    r = subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-plist", path], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=180)
    if r.returncode != 0:
        raise RuntimeError("macOS couldn't open the disc image: %s" % r.stderr.decode("utf-8", "replace").strip()[:200])
    ents = plistlib.loads(r.stdout).get("system-entities", [])
    mnt = next((e["mount-point"] for e in ents if e.get("mount-point")), None)
    dev = next((e["dev-entry"] for e in sorted(ents, key=lambda e: len(e.get("dev-entry", ""))) if e.get("dev-entry")), None)
    if not mnt:
        subprocess.run(["hdiutil", "detach", dev], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raise RuntimeError("The disc image has no files macOS can read.")
    dd = os.path.join(prefix(name), "dosdevices")
    used = {n[0] for n in os.listdir(dd) if len(n) == 2 and n[1] == ":"} | {x["letter"] for x in st["disks"].values()}
    letter = next((l for l in M.DISK_LETTERS if l not in used), None)
    if not letter:
        raise RuntimeError("No free drive letters.")
    os.symlink(mnt, os.path.join(dd, letter + ":"))
    st = load_state(name)
    st["disks"][item_id] = {"letter": letter, "mount": mnt, "dev": dev}
    save_state(name, st)
    return st["disks"][item_id]


def eject(name, item_id):
    st = load_state(name)
    d = st["disks"].pop(item_id, None)
    if not d:
        return {"message": "Not inserted."}
    link = os.path.join(prefix(name), "dosdevices", d["letter"] + ":")
    if os.path.islink(link):
        os.remove(link)
    if os.path.isdir(d.get("mount", "")):
        subprocess.run(["hdiutil", "detach", d.get("dev") or d["mount"], "-force"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=60)
    save_state(name, st)
    return {"message": "Ejected %s." % item_id}


def disc_setup_exe(root):
    target = None
    try:
        with open(os.path.join(root, "autorun.inf"), encoding="utf-8", errors="replace") as f:
            m = re.search(r"^\s*open\s*=\s*(\S+)", f.read(), re.I | re.M)
            if m:
                target = m.group(1).replace("\\", "/")
    except OSError:
        pass
    if not target or not os.path.exists(os.path.join(root, target)):
        target = next((n for n in sorted(os.listdir(root)) if DISC_SETUP_RE.fullmatch(n)), None)
    return target


# ---- archives
def unpack(name, item_id):
    """Unpacks an archive into a folder next to it (one top-level folder inside is not doubled up)."""
    folder = box_path(name)
    src = os.path.join(folder, item_id)
    stem = ARCHIVE_STEM_RE.sub("", item_id) or item_id
    dest = unique_path(folder, stem)
    tmp = meta(name, "unpacking")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    joined = None
    try:
        if re.search(r"\.(7z|zip)\.001$", item_id, re.I):   # split archive: the parts are plain pieces of one file
            joined = meta(name, "joined-" + safe_name(stem))
            with open(joined, "wb") as out:
                for part in sorted(glob.glob(glob.escape(src[:-4]) + ".[0-9][0-9][0-9]")):
                    with open(part, "rb") as f:
                        shutil.copyfileobj(f, out, 8 << 20)
            src = joined
        r = subprocess.run(["/usr/bin/tar", "-xf", src, "-C", tmp], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace").strip().splitlines()
            hint = (" Multi-part .rar archives need unpacking with an app such as The Unarchiver or Keka first."
                    if re.search(r"\.part\d+\.rar$", item_id, re.I) else "")
            raise RuntimeError("Couldn't unpack: %s.%s" % ((err[-1] if err else "unknown error")[:200], hint))
        inner = [n for n in os.listdir(tmp) if n not in M.HIDDEN and n != "__MACOSX"]
        if len(inner) == 1 and os.path.isdir(os.path.join(tmp, inner[0])):
            os.rename(os.path.join(tmp, inner[0]), dest)
        else:
            os.rename(tmp, dest)
        return os.path.basename(dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if joined and os.path.exists(joined):
            os.remove(joined)


# ---- old installers Wine can't run
def innoextract_path():
    return shutil.which("innoextract") or next(
        (p for p in ("/opt/homebrew/bin/innoextract", "/usr/local/bin/innoextract") if os.path.exists(p)), None)


def is_inno(path):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            blob = f.read(2 << 20)
            if size > 4 << 20:
                f.seek(size - (2 << 20))
                blob += f.read()
    except OSError:
        return False
    return b"Inno Setup" in blob or "Inno Setup".encode("utf-16-le") in blob


def inno_unpack(name, exe, label):
    """Unpacks an Inno Setup installer (and its setup-N.bin parts) with innoextract, without running it: the
    fallback for installers that crash under Wine (old 32-bit Inno Setup 5 ones do on Wine 11). The program's
    files end up in a folder in the box, ready to play; what the installer would have done besides copying
    files (shortcuts, registry entries, redistributables) is skipped."""
    tmp = meta(name, "unpacking")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    try:
        r = subprocess.run([innoextract_path(), "-s", "-e", "-d", tmp, exe], stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE)
        if r.returncode != 0:
            raise RuntimeError("innoextract couldn't unpack it: %s" % r.stderr.decode("utf-8", "replace")[-200:])
        out = os.path.join(tmp, "app") if os.path.isdir(os.path.join(tmp, "app")) else tmp
        nice = re.sub(r"(?i)[ _-]*(setup|installer|install)\b", "", label).strip(" _-") or label
        dest = unique_path(box_path(name), nice)
        os.rename(out, dest)
        return os.path.basename(dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- the setup queue
def read_task(name):
    t = read_json(meta(name, "task.json"), None)
    if t and not t.get("finished"):
        try:
            os.kill(t["pid"], 0)
        except OSError:
            t.update(finished=True, label="Stopped")
    return t


def start_setup(name, ids=None):
    """Runs "Set up" for the given items (default: everything not set up yet) in a background worker."""
    check_box(name)
    t = read_task(name)
    if t and not t.get("finished"):
        M.fail("%s is already being set up: %s" % (name, t.get("label", "")))
    pending = [f["id"] for f in box_view(name)["files"] if f["pending"]]
    ids = [i for i in (ids or pending)]
    if not ids:
        return {"message": "Everything in %s is already set up." % name}
    write_json(meta(name, "task.json"), {"pid": 0, "label": "Starting…", "done": 0, "total": len(ids),
                                          "finished": False, "results": []})
    p = subprocess.Popen([sys.executable, os.path.abspath(M.__file__), "box", "_work", name] + ids,
                         stdout=subprocess.DEVNULL, stderr=open(meta(name, "logs", "setup-worker.log"), "ab")
                         if os.path.isdir(meta(name, "logs")) else subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    t = read_json(meta(name, "task.json"), {})
    t["pid"] = p.pid
    write_json(meta(name, "task.json"), t)
    return {"message": "Setting up %d item%s in %s. Installers open their own windows." % (
        len(ids), "" if len(ids) == 1 else "s", name)}


def setup_message(code):
    if code == 0:
        return "Installed"
    if code < 0:
        return "Stopped before it finished"
    return "Setup ended with error code %d" % code


def work(name, ids):
    """The setup worker: unpacks, inserts discs, runs installers, one after another, waiting for each."""
    os.makedirs(meta(name, "logs"), exist_ok=True)
    queue, results, done = list(ids), [], 0
    task = {"pid": os.getpid(), "label": "", "done": 0, "total": len(queue), "finished": False, "results": results}

    def update(label):
        task.update(label=label, done=done, total=done + len(queue))
        write_json(meta(name, "task.json"), task)

    def record(iid, state, message, **kw):
        st = load_state(name)
        st["items"][iid] = dict({"state": state, "message": message, "at": time.time()}, **kw)
        save_state(name, st)
        results.append({"id": iid, "state": state, "message": message})

    while queue:
        iid = queue.pop(0)
        it = next((f for f in box_view(name)["files"] if f["id"] == iid), None)
        if not it:
            continue
        try:
            if it["kind"] == "archive":
                update("Unpacking %s" % iid)
                before = set(os.listdir(box_path(name)))
                into = unpack(name, iid)
                record(iid, "unpacked", "Unpacked into “%s”" % into, into=into)
                # what came out may itself need setting up (an installer, a disc image, another archive)
                new = [f["id"] for f in box_view(name)["files"] if f["id"] not in before and f["pending"]]
                queue[:0] = new
            elif it["kind"] == "disk":
                update("Inserting %s" % iid)
                d = mount(name, iid)
                exe = disc_setup_exe(d["mount"])
                if not exe:
                    record(iid, "installed", "In drive %s: (no setup program on it)" % d["letter"].upper())
                else:
                    update("Installing from %s (drive %s:)" % (iid, d["letter"].upper()))
                    win = "%s:\\%s" % (d["letter"].upper(), exe.replace("/", "\\"))
                    cmd = ["msiexec", "/i", win] if exe.lower().endswith(".msi") else [win]
                    code = spawn(name, "wine", cmd, d["mount"], iid).wait()
                    record(iid, "installed" if code == 0 else "failed",
                           setup_message(code))
            elif it["kind"] == "installer":
                update("Installing %s" % it["name"])
                exe = os.path.join(it["path"], it["mainExe"]) if os.path.isdir(it["path"]) else it["path"]
                cmd = ["msiexec", "/i", it["winPath"]] if exe.lower().endswith(".msi") else [it["winPath"]]
                try:
                    cmd += shlex.split(it.get("args") or "")   # e.g. /S (NSIS) or /VERYSILENT (Inno Setup)
                except ValueError:
                    pass
                code = spawn(name, "wine", cmd, os.path.dirname(exe), iid).wait()
                if code > 0 and exe.lower().endswith(".exe") and is_inno(exe) and innoextract_path():
                    update("Unpacking %s instead (its installer didn't run)" % it["name"])
                    into = inno_unpack(name, exe, os.path.splitext(it["id"])[0])
                    record(iid, "unpacked", "Its installer didn't run under Wine (error code %d), so MacX unpacked "
                                            "it into “%s”" % (code, into), into=into)
                else:
                    record(iid, "installed" if code == 0 else "failed", setup_message(code))
        except Exception as e:   # one bad item must not stop the rest
            record(iid, "failed", str(e)[:300])
        done += 1
    task.update(label="Done", done=done, total=done, finished=True)
    write_json(meta(name, "task.json"), task)


# ------------------------------------------------------------------------------------------------- migration
MAIN = "Main"


def can_migrate():
    """The pre-boxes setup (one shared prefix + the Desktop "MacX" folder) exists and could become a box."""
    return (not os.path.islink(M.PREFIX) and os.path.isdir(os.path.join(M.PREFIX, "drive_c"))
            and not os.path.lexists(box_path(MAIN)))


def migrate_main():
    """Opt-in (the user presses "Move into a box"): the shared setup becomes the box "Main". Prefix and drive
    folder are renamed into ~/MacX Boxes/Main - instant on the same disk, nothing is copied or deleted - and
    the old paths are left as symlinks, so the Steam view and installed games keep working unchanged."""
    if not can_migrate():
        M.fail("There is no shared setup to move, or a box called “%s” already exists." % MAIN)
    if prefix_processes(M.PREFIX):
        M.fail("Quit Steam and any running programs first.")
    os.makedirs(BOXES, exist_ok=True)
    if os.stat(BOXES).st_dev != os.stat(M.PREFIX).st_dev:
        M.fail("MacX Boxes is on a different disk than the shared setup; moving it would mean copying it.")
    dest = box_path(MAIN)
    if os.path.isdir(M.DROP) and not os.path.islink(M.DROP) and os.stat(M.DROP).st_dev == os.stat(BOXES).st_dev:
        os.rename(M.DROP, dest)            # the drive folder (and its icon) becomes the box folder
    else:
        os.makedirs(dest)
    os.makedirs(meta(MAIN), exist_ok=True)
    os.rename(M.PREFIX, prefix(MAIN))
    os.symlink(prefix(MAIN), M.PREFIX)
    if not os.path.lexists(M.DROP):
        os.symlink(dest, M.DROP)
    contain_prefix(prefix(MAIN), dest)
    with open(os.path.join(dest, ".windows-label"), "w") as f:
        f.write(MAIN)
    save_box(MAIN, {"name": MAIN, "created": time.time(), "migrated": True, "items": {}, "detect": {}})


def list_boxes():
    orphan_cleanup()
    pbp = processes_by_prefix()
    return [box_view(n, pbp) for n in box_names()]


def main(argv):
    cmd, a = (argv[0] if argv else ""), argv[1:]
    if cmd == "list":
        return {"boxes": list_boxes(), "root": BOXES, "canMigrate": can_migrate(),
                "canClone": os.path.isdir(os.path.join(os.path.realpath(M.PREFIX), "drive_c"))}
    if cmd == "show":
        check_box(a[0])
        return {"box": box_view(a[0])}
    if cmd == "new":
        n = new_box(a[0] if a else None)
        return {"message": "Created “%s”. Drop Windows games, installers, archives or disc images into it." % n,
                "name": n, "path": box_path(n)}
    if cmd == "add":           # add <box> [--setup] <path>...
        setup = "--setup" in a
        paths = [p for p in a[1:] if p != "--setup"]
        added = add_files(a[0], paths)
        msg = "Added %d item%s to %s." % (len(added), "" if len(added) == 1 else "s", a[0])
        if setup and any(f["pending"] for f in box_view(a[0])["files"] if f["id"] in added):
            msg += " " + start_setup(a[0], [f["id"] for f in box_view(a[0])["files"]
                                            if f["id"] in added and f["pending"]])["message"]
        return {"message": msg, "added": added}
    if cmd == "setup":         # setup <box> [item...]
        return start_setup(a[0], a[1:])
    if cmd == "_work":
        work(a[0], a[1:])
        return {"message": "done"}
    if cmd in ("play", "launch"):
        return play(a[0], a[1], a[2:])
    if cmd == "stop":
        if len(a) > 1:
            return stop_item(a[0], a[1])
        stop_box(a[0])
        return {"message": "Stopped everything in “%s”." % a[0]}
    if cmd == "eject":
        return eject(a[0], a[1])
    if cmd == "set":           # set <box> <item> engine|args|exe <value>
        return set_item(a[0], a[1], a[2], a[3] if len(a) > 3 else "")
    if cmd == "set-engine":
        return set_item(a[0], a[1], "engine", a[2])
    if cmd == "delete":
        delete_box(a[0])
        return {"message": "Moved “%s” to the Trash." % a[0]}
    if cmd == "rename":
        rename_box(a[0], a[1])
        return {"message": "Renamed to “%s”." % a[1]}
    if cmd == "clone-main":
        n = clone_main(a[0] if a else None)
        return {"message": "Copied your setup into the box “%s”. The original is unchanged." % n, "name": n}
    if cmd == "migrate":
        migrate_main()
        return {"message": "Moved your existing setup into the box “%s”." % MAIN, "name": MAIN}
    if cmd == "template":
        build_template()
        return {"message": "Box template ready.", "path": TEMPLATE}
    M.fail("usage: box list|show|new|add|setup|play|stop|eject|set|delete|rename|clone-main|migrate|template")
