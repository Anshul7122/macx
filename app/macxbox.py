"""MacX boxes: one folder = one self-contained Windows environment.

    ~/MacX Boxes/<Name>/            the user's files (drive W: inside Windows)
    ~/MacX Boxes/<Name>/.macx/      hidden: the box's Wine prefix (C:), settings, logs

Deleting the folder removes everything the box installed or created. New boxes are APFS clones of a template
prefix built once (near-instant, almost no disk until they diverge). Containment: no Z: drive, the Windows user
folders (Desktop, Documents, ...) are real folders inside the box, and every box program runs under a macOS
sandbox profile that denies access to the home folder outside the box. This contains ordinary programs; it is not
a guarantee against deliberately malicious software.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import time
import uuid

import macxctl as M

BOXES = os.environ.get("MACX_BOXES") or os.path.join(M.HOME, "MacX Boxes")
TEMPLATE = os.path.join(M.ROOT, "box-template")
ENGINES_DIR = os.path.join(M.ROOT, "engines")
META = ".macx"
SHELL_FOLDERS = ("Desktop", "Documents", "Downloads", "Music", "Pictures", "Videos", "Templates")


# ------------------------------------------------------------------------------------------------- paths
def box_path(name):
    return os.path.join(BOXES, name)


def meta(name, *parts):
    return os.path.join(box_path(name), META, *parts)


def prefix(name):
    return meta(name, "prefix")


def is_box(path):
    return os.path.isdir(os.path.join(path, META, "prefix", "drive_c"))


def load_box(name):
    try:
        with open(meta(name, "box.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"items": {}, "detect": {}}


def save_box(name, data):
    p = meta(name, "box.json")
    with open(p + ".tmp", "w") as f:
        json.dump(data, f, indent=2)
    os.replace(p + ".tmp", p)


# ------------------------------------------------------------------------------------------------- containment
def contain_prefix(pfx, box_folder=None):
    """No Z: drive, real (in-box) user folders, and W: -> the box folder. Safe to run on every launch."""
    dd = os.path.join(pfx, "dosdevices")
    for letter in os.listdir(dd) if os.path.isdir(dd) else []:
        link = os.path.join(dd, letter)
        if letter.endswith(":") and letter not in ("c:", "w:") and os.path.islink(link):
            target = os.path.realpath(link)
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
        for sf in SHELL_FOLDERS:
            p = os.path.join(users, user, sf)
            if os.path.islink(p):         # Wine links these to the Mac's own folders
                os.remove(p)
            os.makedirs(p, exist_ok=True)


def sandbox_profile(name):
    """macOS sandbox for a box's Wine processes: the home folder is off limits except the box itself and the
    MacX engines (read-only). Everything else (system, network, GPU, temp) works as usual."""
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
    ])


# ------------------------------------------------------------------------------------------------- template
def template_stamp():
    """Changes when the engines change, so the template is rebuilt."""
    parts = [M.sha(os.path.join(M.D3DM_APP, "Contents", "Resources", "wine", "lib", "wine", "x86_64-unix",
                                "ntdll.so")) or "", M.sha(M.NTDLX) or ""]
    return "-".join(p[:12] for p in parts)


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
    for arch, d in (("x64", "system32"), ("x32", "syswow64")):   # DXVK, for launchers' own windows
        for dll in M.GFX_DLLS:
            src = os.path.join(M.DXVK_FULL, arch, dll)
            if os.path.exists(src) and os.path.isdir(os.path.join(tmp, "drive_c", "windows", d)):
                shutil.copy2(src, os.path.join(tmp, "drive_c", "windows", d, dll))
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
    contain_prefix(prefix(name), box_path(name))
    with open(os.path.join(box_path(name), ".windows-label"), "w") as f:
        f.write(name[:32])
    save_box(name, {"name": name, "created": time.time(), "items": {}, "detect": {}})
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


def box_processes(name):
    """pids of Wine processes running in this box (matched by open files under its prefix)."""
    return prefix_processes(prefix(name))


def prefix_processes(pfx):
    pfx = os.path.realpath(pfx)
    pids = []
    for p in M.wine_processes():
        r = subprocess.run(["lsof", "-Fn", "-p", str(p["pid"])], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, errors="replace")
        if any(l[1:].startswith(pfx) for l in r.stdout.splitlines() if l.startswith("n")):
            pids.append(p["pid"])
    return pids


def stop_box(name):
    env = M.wine_env({"WINEPREFIX": prefix(name)}, "d3dmetal")
    subprocess.run([M.ENGINES["d3dmetal"]["server"], "-k"], env=env, timeout=30,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    for pid in box_processes(name):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def orphan_cleanup():
    """Wine processes whose box folder was deleted (e.g. moved to the Trash in Finder) are stopped."""
    live = [os.path.realpath(prefix(n)) for n in box_names()]
    killed = []
    for p in M.wine_processes():
        r = subprocess.run(["lsof", "-Fn", "-p", str(p["pid"])], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, errors="replace")
        paths = [l[1:] for l in r.stdout.splitlines() if l.startswith("n")]
        boxy = [x for x in paths if "/%s/prefix/" % META in x]
        if boxy and not any(x.startswith(lp) for x in boxy for lp in live):
            try:
                os.kill(p["pid"], signal.SIGKILL)
                killed.append(p["pid"])
            except OSError:
                pass
    stale_server_dirs(live)
    return killed


def server_dir_prefix(d):
    """Wine keys its server dir (/tmp/.wine-UID/server-<dev>-<inode>) on the prefix folder. Resolve it back to
    a path through /.vol, or None when that folder no longer exists."""
    m = re.match(r"server-([0-9a-f]+)-([0-9a-f]+)$", d)
    if not m:
        return ""
    try:
        fd = os.open("/.vol/%d/%d" % (int(m.group(1), 16), int(m.group(2), 16)), os.O_RDONLY)
    except OSError:
        return None
    try:
        import fcntl
        return fcntl.fcntl(fd, 50, b"\0" * 1024).split(b"\0", 1)[0].decode(errors="replace")   # F_GETPATH
    except OSError:
        return ""
    finally:
        os.close(fd)


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


def delete_box(name):
    stop_box(name)
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


# ------------------------------------------------------------------------------------------------- programs
def box_items(name):
    data = load_box(name)
    folder = box_path(name)
    items = []
    for entry in sorted(os.listdir(folder), key=str.lower):
        if entry.startswith(".") or entry in M.HIDDEN:
            continue
        path = os.path.join(folder, entry)
        stem, ext = os.path.splitext(entry)
        ext = ext.lower()
        exes, main, base = [], None, folder
        if os.path.isdir(path):
            base = path
            exes = M.list_exes(path)
            playable = [e for e in exes if not M.SKIP_EXE.search(os.path.basename(e))]
            setups = [e for e in exes if M.INSTALLER_RE.search(os.path.basename(e))]
            kind = "folder" if playable else ("installer" if setups else "files")
            main = data["items"].get(entry, {}).get("exe") or (M.guess_main_exe(path, playable) if playable
                                                                else (setups[0] if setups else None))
        else:
            kind = M.EXT_KIND.get(ext, "file")
            if kind == "program" and M.INSTALLER_RE.search(entry):
                kind = "installer"
            if kind in ("program", "installer"):
                exes, main = [entry], entry
        info = M.pe_info(os.path.join(base, main), data) if main and main.lower().endswith(".exe") else {"apis": []}
        apis = info.get("apis", [])
        auto = "d3dmetal" if ({"dx10", "dx11", "dx12"} & set(apis)) and M.engine_ok("d3dmetal") else "wine11"
        engine = data["items"].get(entry, {}).get("engine", "auto")
        items.append({"id": entry, "name": stem if os.path.isfile(path) else entry, "kind": kind, "path": path,
                      "baseDir": base, "mainExe": main, "exes": exes, "api": M.api_label(apis),
                      "bits": info.get("bits"), "engine": engine, "autoEngine": auto,
                      "effectiveEngine": auto if engine == "auto" else engine})
    data.pop("_dirty", None)
    save_box(name, data)
    return items


def launch(name, item_id, args=None):
    item = next((i for i in box_items(name) if i["id"] == item_id), None)
    if not item or not item["mainExe"]:
        M.fail("Nothing to run in “%s”." % item_id)
    engine = item["effectiveEngine"]
    contain_prefix(prefix(name), box_path(name))
    exe = os.path.join(item["baseDir"], item["mainExe"])
    rel = os.path.relpath(exe, box_path(name)).replace("/", "\\")
    win = "W:\\" + rel
    cmd = (["msiexec", "/i", win] if exe.lower().endswith(".msi") else [win]) + list(args or [])
    os.makedirs(meta(name, "logs"), exist_ok=True)
    env = M.wine_env({"WINEPREFIX": prefix(name), "WINEDEBUG": "fixme-all",
                      **({"MTL_HUD_ENABLED": "1"} if M.load_config().get("hud") else {})}, engine)
    profile = meta(name, "sandbox.sb")
    with open(profile, "w") as f:
        f.write(sandbox_profile(name))
    log = open(meta(name, "logs", re.sub(r"[^\w.-]+", "_", item_id) + ".log"), "wb")
    subprocess.Popen(["/usr/bin/sandbox-exec", "-f", profile, M.ENGINES[engine]["wine"]] + cmd,
                     cwd=os.path.dirname(exe), env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    return {"message": "Starting %s in %s (%s)." % (item["name"], name, M.ENGINES[engine]["short"])}


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
    res = []
    for n in box_names():
        procs = box_processes(n)
        res.append({"name": n, "path": box_path(n), "running": bool(procs), "items": box_items(n)})
    return res


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "list":
        return {"boxes": list_boxes(), "root": BOXES, "canMigrate": can_migrate()}
    if cmd == "migrate":
        migrate_main()
        return {"message": "Moved your existing setup into the box “%s”." % MAIN, "name": MAIN}
    if cmd == "new":
        n = new_box(argv[1] if len(argv) > 1 else None)
        return {"message": "Created “%s”. Drop Windows programs into it." % n, "name": n, "path": box_path(n)}
    if cmd == "launch":
        return launch(argv[1], argv[2], argv[3:])
    if cmd == "stop":
        stop_box(argv[1])
        return {"message": "Stopped everything in “%s”." % argv[1]}
    if cmd == "delete":
        delete_box(argv[1])
        return {"message": "Moved “%s” to the Trash." % argv[1]}
    if cmd == "rename":
        rename_box(argv[1], argv[2])
        return {"message": "Renamed to “%s”." % argv[2]}
    if cmd == "set-engine":
        data = load_box(argv[1])
        data["items"].setdefault(argv[2], {})["engine"] = argv[3]
        save_box(argv[1], data)
        return {"message": "Saved."}
    if cmd == "template":
        build_template()
        return {"message": "Box template ready.", "path": TEMPLATE}
    M.fail("usage: box list|new [name]|launch <box> <item>|stop|delete|rename|set-engine|template")
