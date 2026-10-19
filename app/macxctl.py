#!/usr/bin/python3
"""MacX backend: the Wine engines, the Windows C: drive and the "MacX" Desktop folder (drive W:).
Data lives in ~/Library/Application Support/MacX (or $MACX_ROOT).

Every command prints one JSON object to stdout:  {"ok": true, ...} or {"ok": false, "error": "..."}
"""
import glob
import hashlib
import json
import os
import plistlib
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
USER = os.environ.get("USER") or os.path.basename(HOME)
HERE = os.path.dirname(os.path.abspath(__file__))
# Engine kit: our compiled bridge (see scripts/build-engine-kit.sh). Inside the app bundle it sits next to this file.
KIT = os.environ.get("MACX_KIT") or next(
    (p for p in (os.path.join(HERE, "engine-kit"), os.path.join(HERE, "..", "build", "engine-kit")) if os.path.isdir(p)),
    os.path.join(HERE, "engine-kit"))
SUPPORT = os.path.join(HOME, "Library", "Application Support", "MacX")
ROOT = os.environ.get("MACX_ROOT") or SUPPORT
PREFIX = os.path.join(ROOT, "prefix")
WINE_APP = os.path.join(ROOT, "engines", "wine", "Wine Devel.app")
D3DM_APP = os.path.join(ROOT, "engines", "wine-d3dmetal", "Wine Devel.app")
GPTK_PREFIX = os.path.join(ROOT, "prefix-gptk77")
DXVK_FULL = os.path.join(ROOT, "gfx", "dxvk")
STEAM_WRAP = CEF_WRAP = os.path.join(KIT, "windows", "cefwrap.exe")
NTDLX = os.path.join(KIT, "windows", "ntdlx.dll")
CONFIG = os.path.join(ROOT, "config.json")
DRIVE_C = os.path.join(PREFIX, "drive_c")
WINE_RES = os.path.join(WINE_APP, "Contents", "Resources", "wine")
WINEBIN = os.path.join(WINE_RES, "bin")
WINE_LIB = os.path.join(WINE_RES, "lib", "wine")
D3DM_BIN = os.path.join(D3DM_APP, "Contents", "Resources", "wine", "bin")
GPTK_APP = os.environ.get("MACX_GPTK") or next(
    (p for p in ("/Applications/Game Porting Toolkit.app", os.path.join(HOME, "Applications", "Game Porting Toolkit.app"))
     if os.path.isdir(p)), "/Applications/Game Porting Toolkit.app")
GPTK_BIN = os.path.join(GPTK_APP, "Contents", "Resources", "wine", "bin")
STEAM_DIR = os.path.join(DRIVE_C, "Program Files (x86)", "Steam")
STEAMAPPS = os.path.join(STEAM_DIR, "steamapps")
SC_DIR = os.path.join(DRIVE_C, "Program Files", "Rockstar Games", "Social Club")
RGL_DIR = os.path.join(DRIVE_C, "Program Files", "Rockstar Games", "Launcher")
LOGS = os.path.join(ROOT, "logs")
DROP_NAME = "MacX"
DROP = os.path.join(HOME, "Desktop", DROP_NAME)
DROP_LETTER = "w"
DROP_LABEL = DROP_NAME
BASE_OVERRIDES = "mscoree,mshtml=;winemenubuilder.exe=d"

# Wine engines. All share the W: drive. "wine11" and "d3dmetal" are the same Wine 11 build and share one C: drive
# (with Steam); "d3dmetal" adds Apple's D3DMetal through the bridges in engine/. "gptk77" (Game Porting Toolkit's
# own Wine 7.7, separate C: drive) only appears where an earlier setup created it.
ENGINES = {
    "wine11": {"name": "Wine 11 (DXMT / DXVK)", "short": "Wine 11", "wine": os.path.join(WINEBIN, "wine"),
               "server": os.path.join(WINEBIN, "wineserver"), "prefix": PREFIX},
    "d3dmetal": {"name": "Wine 11 + Apple D3DMetal (DirectX 11/12 → Metal)", "short": "D3DMetal",
                 "wine": os.path.join(D3DM_BIN, "wine"), "server": os.path.join(D3DM_BIN, "wineserver"),
                 "prefix": PREFIX},
}
if os.path.isdir(GPTK_PREFIX):
    ENGINES["gptk77"] = {"name": "Game Porting Toolkit's Wine 7.7 (separate C: drive)", "short": "GPTK 7.7",
                         "wine": os.path.join(GPTK_BIN, "wine64"), "server": os.path.join(GPTK_BIN, "wineserver"),
                         "prefix": GPTK_PREFIX}
STEAM_LOG = os.path.join(LOGS, "steam.log")
DXMT_NATIVE = os.path.join(ROOT, "gfx", "dxmt-native")
GFX_DLLS = ["d3d11.dll", "dxgi.dll", "d3d10core.dll"]
SKIP_EXE = re.compile(r"(unins|setup|install|redist|vcredist|dxsetup|crash|report|_be\.exe$|battleye|beservice|"
                      r"launcherpatcher|uninstall|easyanticheat|eac|ue4prereq|dotnet|directx|helper|update)", re.I)


# ----------------------------------------------------------------------------- helpers
def out(obj):
    obj.setdefault("ok", True)
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def fail(msg, **extra):
    extra.update(ok=False, error=msg)
    out(extra)
    sys.exit(0)


def load_config():
    cfg = None
    for path in (CONFIG,):
        try:
            with open(path) as f:
                cfg = json.load(f)
            break
        except Exception:
            continue
    cfg = cfg or {}
    for key, default in (("games", {}), ("items", {}), ("detect", {}), ("disks", {}), ("hud", False)):
        cfg.setdefault(key, default)
    return cfg


def save_config(cfg):
    tmp = CONFIG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG)


def engine_ok(engine):
    return os.path.exists(ENGINES[engine]["wine"])


def wine_env(extra=None, engine="wine11"):
    env = dict(os.environ)
    env.update(WINEPREFIX=ENGINES[engine]["prefix"], WINEESYNC="1", WINEMSYNC="1",
               WINEDLLOVERRIDES=BASE_OVERRIDES, WINEDEBUG="-all",
               ROSETTA_ADVERTISE_AVX="1")  # lets games that require AVX/AVX2 see it under Rosetta
    if engine == "d3dmetal":
        env.update(D3DM_ENABLE_METALFX="1")  # DLSS requests -> MetalFX; D3DMetal keeps its own GPU identity
    if extra:
        env.update(extra)
    return env


def wine(args, wait=True, timeout=90, env_extra=None, engine="wine11"):
    cmd = [ENGINES[engine]["wine"]] + list(args)
    if wait:
        r = subprocess.run(cmd, env=wine_env(env_extra, engine), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=timeout)
        return r.returncode, r.stdout.decode("utf-8", "replace")
    subprocess.Popen(cmd, env=wine_env(env_extra, engine), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    return 0, ""


def sha(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def win_to_unix(p, engine="wine11"):
    p = p.replace("\\\\", "\\")
    if len(p) > 2 and p[1] == ":":
        root = os.path.join(ENGINES[engine]["prefix"], "dosdevices", p[0].lower() + ":")
        if p[0].lower() == DROP_LETTER:
            root = DROP
        if not os.path.exists(root):
            return None
        return os.path.join(os.path.realpath(root), *[s for s in p[3:].split("\\") if s])
    return None


def unix_to_win(path):
    """Windows-style path for a file on the W: drive (or C: of the main engine); Z: otherwise."""
    real = os.path.realpath(path)
    for root, letter in ((os.path.realpath(DROP), "W"), (os.path.realpath(DRIVE_C), "C"),
                         (os.path.realpath(os.path.join(GPTK_PREFIX, "drive_c")), "C")):
        if real == root or real.startswith(root + os.sep):
            rest = os.path.relpath(real, root)
            return "%s:\\%s" % (letter, "" if rest == "." else rest.replace(os.sep, "\\"))
    return "Z:" + real.replace("/", "\\")


def du_bytes(path):
    if not os.path.exists(path):
        return 0
    if os.path.isfile(path) and not os.path.islink(path):
        return os.path.getsize(path)
    try:
        r = subprocess.run(["du", "-sk", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=120)
        return int(r.stdout.split()[0]) * 1024
    except Exception:
        return 0


# ----------------------------------------------------------------------------- VDF (Steam KeyValues text)
def vdf_tokens(text):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j == -1 else j + 1
        elif c in "{}":
            yield c
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j:j + 2])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            yield ("s", "".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n{}\"":
                j += 1
            yield ("s", text[i:j])
            i = j


def vdf_load(text):
    """Returns a list of [key, value] pairs; value is a str or a nested list (keeps order and duplicates)."""
    toks = list(vdf_tokens(text))
    pos = 0

    def parse_block():
        nonlocal pos
        items = []
        while pos < len(toks):
            t = toks[pos]
            if t == "}":
                pos += 1
                return items
            key = t[1]
            pos += 1
            nxt = toks[pos]
            if nxt == "{":
                pos += 1
                items.append([key, parse_block()])
            else:
                items.append([key, nxt[1]])
                pos += 1
        return items

    return parse_block()


def vdf_dump(items, depth=0):
    lines = []
    tab = "\t" * depth
    for k, v in items:
        if isinstance(v, list):
            lines.append('%s"%s"' % (tab, k))
            lines.append(tab + "{")
            lines.append(vdf_dump(v, depth + 1))
            lines.append(tab + "}")
        else:
            lines.append('%s"%s"\t\t"%s"' % (tab, k, v))
    return "\n".join(l for l in lines if l != "")


def vdf_get(items, *path, create=False):
    cur = items
    for key in path:
        found = None
        for kv in cur:
            if kv[0].lower() == key.lower() and isinstance(kv[1], list):
                found = kv[1]
                break
        if found is None:
            if not create:
                return None
            found = []
            cur.append([key, found])
        cur = found
    return cur


def vdf_value(block, key):
    for k, v in block or []:
        if k.lower() == key.lower() and not isinstance(v, list):
            return v
    return None


# ----------------------------------------------------------------------------- processes
def _ps(field):
    r = subprocess.run(["ps", "-ax", "-o", "pid=,%s=" % field], stdout=subprocess.PIPE, text=True, errors="replace")
    res = {}
    for line in r.stdout.splitlines():
        pid, _, rest = line.strip().partition(" ")
        if pid.isdigit():
            res[int(pid)] = rest.strip()
    return res


def wine_processes():
    comms = _ps("comm")
    procs = []
    for pid, cmd in _ps("command").items():
        comm = comms.get(pid, "")
        # only Wine's own processes: their name is a Windows path (C:\...exe) or a wine binary. Anything else
        # (e.g. a shell whose arguments merely mention a .exe path) must never be matched or killed.
        if not (re.match(r"[A-Za-z]:\\", comm) or re.search(r"(^|/)(wine|wine64|wineserver|wine64-preloader|wine-preloader)$", comm)):
            continue
        where = comm + cmd
        engine = "gptk77" if "Game Porting Toolkit" in where else ("d3dmetal" if "wine11-d3dm" in where else "wine11")
        m = re.search(r"([A-Za-z]:\\[^\r\n]*?\.exe)", cmd, re.I)
        if m:
            exe = m.group(1).split("\\")[-1]
            procs.append({"pid": pid, "exe": exe, "path": m.group(1), "engine": engine})
        elif re.search(r"(^|/)wineserver\b", cmd):
            procs.append({"pid": pid, "exe": "wineserver", "path": cmd, "engine": engine})
    return procs


BOXES_DIR = os.environ.get("MACX_BOXES") or os.path.join(HOME, "MacX Boxes")


def server_dir_prefix(d):
    """Wine keys its server dir (/tmp/.wine-UID/server-<dev>-<inode>) on the prefix folder. Resolve it back to
    a path through /.vol, "" if it isn't one, or None when that folder no longer exists."""
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


def lsof_paths(pids, cwd_only=False):
    """{pid: [paths]} for many processes in one lsof call. cwd_only asks only for each process's working folder,
    which is ~15x cheaper than listing every open file (a game keeps thousands open)."""
    res = {}
    if not pids:
        return res
    cmd = ["lsof", "-Fpn"] + (["-a", "-d", "cwd"] if cwd_only else []) + ["-p", ",".join(map(str, pids))]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="replace")
    cur = None
    for line in r.stdout.splitlines():
        if line.startswith("p"):
            cur = int(line[1:])
            res.setdefault(cur, [])
        elif line.startswith("n") and cur is not None:
            res[cur].append(line[1:])
    return res


def process_prefixes(procs):
    """{pid: real path of the Wine prefix it runs in} for Wine processes. Windows programs work inside their
    prefix's C: drive or their box folder (W:), and a wineserver sits in its server dir, so the working folder
    nearly always tells; only processes it doesn't (e.g. one started from a disc) get the full open-files scan."""
    boxes = os.path.realpath(BOXES_DIR) + os.sep
    shared = os.path.realpath(PREFIX)
    drop = os.path.realpath(DROP)
    res, unknown = {}, []

    def classify(path):
        m = re.match(r"(.*/%s/prefix)(/|$)" % re.escape(".macx"), path)
        if m:
            return m.group(1)
        if path.startswith(boxes):
            return os.path.join(boxes, path[len(boxes):].split(os.sep)[0], ".macx", "prefix")
        if path == shared or path.startswith(shared + os.sep) or path == drop or path.startswith(drop + os.sep):
            return shared
        d = os.path.basename(path)
        if d.startswith("server-"):
            p = server_dir_prefix(d)
            return os.path.realpath(p) if p else None
        return None

    for pid, paths in lsof_paths([p["pid"] for p in procs], cwd_only=True).items():
        pfx = next((c for c in map(classify, paths) if c), None)
        if pfx:
            res[pid] = pfx
        else:
            unknown.append(pid)
    for pid, paths in lsof_paths(unknown).items():
        pfx = next((c for c in map(classify, paths) if c and "/drive_c" in "".join(paths)), None) or next(
            (c for c in map(classify, paths) if c), None)
        if pfx:
            res[pid] = pfx
    return res


def box_pids(procs):
    """pids (of these Wine processes) that run inside a MacX box rather than the shared setup."""
    shared = os.path.realpath(PREFIX)
    return {pid for pid, pfx in process_prefixes(procs).items() if pfx != shared}


def shared_processes():
    """Wine processes of the shared setup only (boxes are listed on their own page)."""
    procs = wine_processes()
    boxed = box_pids(procs)
    return [p for p in procs if p["pid"] not in boxed]


def steam_running(procs=None):
    procs = procs if procs is not None else shared_processes()
    return any(p["exe"].lower() == "steam.exe" for p in procs)


# ----------------------------------------------------------------------------- registry (AppDefaults)
def read_user_reg(engine="wine11"):
    try:
        with open(os.path.join(ENGINES[engine]["prefix"], "user.reg"), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def app_overrides(exe, engine="wine11"):
    text = read_user_reg(engine)
    key = "[Software\\\\Wine\\\\AppDefaults\\\\%s\\\\DllOverrides]" % exe
    res = {}
    i = text.lower().find(key.lower())
    if i == -1:
        return res
    for line in text[i:].splitlines()[1:]:
        if not line.strip() or line.startswith("["):
            break
        m = re.match(r'"([^"]+)"="([^"]*)"', line.strip())
        if m:
            res[m.group(1).lower()] = m.group(2)
    return res


def set_overrides(exe, mapping, engine="wine11"):
    key = "HKCU\\Software\\Wine\\AppDefaults\\%s\\DllOverrides" % exe
    if mapping is None:
        wine(["reg", "delete", key, "/f"], engine=engine)
        return
    for dll, val in mapping.items():
        wine(["reg", "add", key, "/v", dll, "/d", val, "/f"], engine=engine)


# ----------------------------------------------------------------------------- games
def manifests():
    games = []
    for f in sorted(glob.glob(os.path.join(STEAMAPPS, "appmanifest_*.acf"))):
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                st = vdf_get(vdf_load(fh.read()), "AppState")
        except Exception:
            continue
        if not st:
            continue
        appid = vdf_value(st, "appid")
        if appid == "228980":  # Steamworks redistributables, not a game
            continue
        flags = int(vdf_value(st, "StateFlags") or 0)
        installdir = vdf_value(st, "installdir") or ""
        games.append({
            "appid": appid,
            "name": vdf_value(st, "name") or appid,
            "installdir": installdir,
            "path": os.path.join(STEAMAPPS, "common", installdir),
            "size": int(vdf_value(st, "SizeOnDisk") or 0),
            "flags": flags,
            "state": "Installed" if flags == 4 else ("Updating / downloading" if flags & 1026 else "Not fully installed"),
            "manifest": f,
        })
    return games


def list_exes(path):
    exes = []
    for depth_glob in ("*.exe", "*/*.exe", "*/*/*.exe"):
        for p in glob.glob(os.path.join(path, depth_glob)):
            rel = os.path.relpath(p, path)
            exes.append(rel)
    return sorted(set(exes), key=lambda r: (r.count(os.sep), r.lower()))


def guess_main_exe(path, exes):
    known = {"GTA5.exe", "GTA5_Enhanced.exe"}
    for e in exes:
        if os.path.basename(e) in known:
            return e
    best, best_size = None, -1
    for e in exes:
        if SKIP_EXE.search(os.path.basename(e)):
            continue
        try:
            s = os.path.getsize(os.path.join(path, e))
        except OSError:
            continue
        if s > best_size:
            best, best_size = e, s
    return best or (exes[0] if exes else None)


def detect_mode(game_path, exe_rel):
    if not exe_rel:
        return "wine"
    exe = os.path.basename(exe_rel)
    exe_dir = os.path.join(game_path, os.path.dirname(exe_rel))
    ov = app_overrides(exe)
    native = ov.get("d3d11", "").startswith("native")
    local_dxmt = all(sha(os.path.join(exe_dir, d)) == sha(os.path.join(DXMT_NATIVE, d)) for d in GFX_DLLS) \
        if all(os.path.exists(os.path.join(exe_dir, d)) for d in GFX_DLLS) else False
    if native and local_dxmt:
        return "dxmt"
    if native:
        return "dxvk"
    return "wine"


def userdata_localconfig():
    files = glob.glob(os.path.join(STEAM_DIR, "userdata", "*", "config", "localconfig.vdf"))
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0] if files else None


def launch_options_all():
    f = userdata_localconfig()
    if not f:
        return {}
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            root = vdf_load(fh.read())
    except Exception:
        return {}
    apps = vdf_get(root, "UserLocalConfigStore", "Software", "Valve", "Steam", "apps") or []
    return {k: (vdf_value(v, "LaunchOptions") or "") for k, v in apps if isinstance(v, list)}


def game_info(g, cfg, lo):
    gcfg = cfg["games"].get(g["appid"], {})
    exes = list_exes(g["path"]) if os.path.isdir(g["path"]) else []
    main = gcfg.get("exe") if gcfg.get("exe") in exes else guess_main_exe(g["path"], exes)
    g.update(exes=exes, mainExe=main, mode=detect_mode(g["path"], main), launchOptions=lo.get(g["appid"], ""),
             dx12=bool(main and re.search(r"enhanced", main, re.I)))
    return g


# ----------------------------------------------------------------------------- commands
def running_drop_items(procs):
    """{item id: [proc, ...]} for programs running from the MacX folder."""
    res = {}
    drop = os.path.realpath(DROP)
    for p in procs:
        if p["exe"] == "wineserver":
            continue
        up = win_to_unix(p["path"], p["engine"]) or ""
        if up.startswith(drop + os.sep) and os.path.exists(up):
            res.setdefault(os.path.relpath(up, drop).split(os.sep)[0], []).append(p)
    return res


def engines_data():
    return [{"id": eid, "name": e["name"], "short": e["short"], "available": engine_ok(eid),
             "ready": os.path.isdir(os.path.join(e["prefix"], "drive_c")),
             "wDrive": drive_linked(eid), "cDrive": os.path.join(e["prefix"], "drive_c")}
            for eid, e in ENGINES.items()]


def status_data():
    procs = shared_processes()
    st = os.statvfs(HOME)
    cfg = load_config()
    running_games = []
    gdirs = {g["path"].lower(): g["name"] for g in manifests()}
    for p in procs:
        up = win_to_unix(p["path"]) or ""
        for d, name in gdirs.items():
            if up.lower().startswith(d + os.sep):
                running_games.append({"name": name, "exe": p["exe"], "pid": p["pid"]})
    running_items = [{"id": iid, "exe": ps[0]["exe"], "pid": ps[0]["pid"], "engine": ps[0]["engine"]}
                     for iid, ps in sorted(running_drop_items(procs).items())]
    return {
        "steamRunning": steam_running(procs),
        "processes": [p for p in procs if p["exe"] != "wineserver"],
        "wineserver": any(p["exe"] == "wineserver" for p in procs),
        "runningGames": running_games,
        "runningItems": running_items,
        "freeBytes": st.f_bavail * st.f_frsize,
        "totalBytes": st.f_blocks * st.f_frsize,
        "hud": bool(cfg.get("hud")),
        "root": ROOT,
        "cDrive": DRIVE_C,
        "drop": DROP,
        "dropExists": os.path.isdir(DROP),
        "engines": engines_data(),
        "setupOK": engine_ok("wine11") and engine_ok("d3dmetal") and os.path.isdir(DRIVE_C),
    }


def cmd_status():
    out(status_data())


def cmd_games():
    cfg = load_config()
    lo = launch_options_all()
    out({"games": [game_info(g, cfg, lo) for g in manifests()]})


def is_cef_wrapper(path):
    """True for any build of our helper wrapper (engine/wrap/wrap.c): small, and it reads wrap_flags.txt."""
    try:
        if os.path.getsize(path) > 2_000_000:
            return False
        with open(path, "rb") as f:
            return "wrap_flags.txt".encode("utf-16-le") in f.read()
    except OSError:
        return False


def apply_cef_wrappers(drive_c=None):
    """Steam's and the Rockstar launcher's Chromium helpers need --in-process-gpu to draw under Wine. Wrap the helper
    exe (helper.exe -> helper_real.exe + our wrapper); re-applied after every update that replaces it. drive_c picks
    another C: drive (a box's); the default is the shared one."""
    steam_dir = os.path.join(drive_c, "Program Files (x86)", "Steam") if drive_c else STEAM_DIR
    sc_dir = os.path.join(drive_c, "Program Files", "Rockstar Games", "Social Club") if drive_c else SC_DIR
    for folder, helper, flags in (
            (os.path.join(steam_dir, "bin", "cef", "cef.win64"), "steamwebhelper", "--in-process-gpu"),
            (sc_dir, "SocialClubHelper", "--in-process-gpu --disable-gpu --disable-gpu-compositing")):
        exe = os.path.join(folder, helper + ".exe")
        wrap = STEAM_WRAP if helper == "steamwebhelper" else CEF_WRAP
        if not os.path.exists(exe) or not os.path.exists(wrap) or sha(exe) == sha(wrap):
            continue
        if not is_cef_wrapper(exe):   # a new real helper from an update: keep it as helper_real.exe
            shutil.move(exe, os.path.join(folder, helper + "_real.exe"))
        shutil.copy2(wrap, exe)       # (an older build of our wrapper is simply replaced)
        flags_file = os.path.join(folder, "wrap_flags.txt")
        if not os.path.exists(flags_file):
            with open(flags_file, "w") as f:
                f.write(flags)


def steam_engine():
    return "d3dmetal" if engine_ok("d3dmetal") else "wine11"


def start_steam(extra_args=None):
    """Windows Steam, on the D3DMetal engine when installed (games inherit Steam's engine)."""
    engine = steam_engine()
    ensure_engine(engine)
    apply_cef_wrappers()
    env = {"WINEDEBUG": "-all"}
    if load_config().get("hud"):
        env["MTL_HUD_ENABLED"] = "1"
    os.makedirs(LOGS, exist_ok=True)
    with open(STEAM_LOG, "ab") as log:
        subprocess.Popen([ENGINES[engine]["wine"], "C:\\Program Files (x86)\\Steam\\steam.exe", "-no-cef-sandbox",
                          "-cef-disable-gpu", "-noverifyfiles", "-norepairfiles"] + (extra_args or []),
                         env=wine_env(env, engine), stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                         start_new_session=True)


def stop_steam(timeout=40):
    if not steam_running():
        return True
    wine(["C:\\Program Files (x86)\\Steam\\steam.exe", "-shutdown"], wait=False)
    end = time.time() + timeout
    while time.time() < end:
        time.sleep(1.5)
        if not steam_running():
            return True
    return False


def own_engine_pids(pids):
    """The subset of pids running one of this install's engines (other Wine setups on the Mac are left alone)."""
    roots = [os.path.realpath(os.path.dirname(e["wine"])).rsplit("/bin", 1)[0] for e in ENGINES.values()]
    mine = []
    for pid in pids:
        r = subprocess.run(["lsof", "-Fn", "-p", str(pid)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, errors="replace")
        if any(line[1:].startswith(root) for line in r.stdout.splitlines() if line.startswith("n") for root in roots):
            mine.append(pid)
    return mine


def kill_all():
    done = set()
    for eid, e in ENGINES.items():
        if e["prefix"] in done:
            continue
        done.add(e["prefix"])
        if engine_ok(eid) and os.path.isdir(e["prefix"]):
            subprocess.run([e["server"], "-k"], env=wine_env(engine=eid), stderr=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, timeout=30)
    time.sleep(1)
    for pid in own_engine_pids([p["pid"] for p in shared_processes()]):   # boxes are stopped from their own page
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def cmd_steam(action):
    if action == "start":
        if steam_running():
            wine(["C:\\Program Files (x86)\\Steam\\steam.exe", "steam://open/main"], wait=False)
            return out({"message": "Steam is already running; bringing its window back."})
        start_steam()
        return out({"message": "Starting Steam (takes ~30 seconds)."})
    if action == "stop":
        clean = stop_steam()
        if not clean:
            kill_all()
        return out({"message": "Steam closed." if clean else "Steam didn't close in time, so it was force-quit."})
    if action == "restart":
        if not stop_steam():
            kill_all()
        start_steam()
        return out({"message": "Restarting Steam."})
    fail("unknown steam action")


def steam_url(url):
    if steam_running():
        wine(["C:\\Program Files (x86)\\Steam\\steam.exe", url], wait=False)
    else:
        start_steam([url])


def cmd_play(appid):
    steam_url("steam://rungameid/%s" % appid)
    out({"message": "Starting the game through Steam. The first launch can take a minute."})


def cmd_install(appid):
    if not re.fullmatch(r"\d+", appid or ""):
        fail("App ID must be a number (find it in the game's Steam store URL).")
    steam_url("steam://install/%s" % appid)
    out({"message": "Steam will ask where to install it and start downloading."})


def cmd_uninstall(appid):
    steam_url("steam://uninstall/%s" % appid)
    out({"message": "Steam will ask you to confirm the uninstall in its own window."})


def cmd_uninstall_force(appid):
    if steam_running():
        fail("Close Steam first (Overview → Quit Steam). Normal 'Uninstall' works while Steam is open.")
    g = next((g for g in manifests() if g["appid"] == appid), None)
    if not g:
        fail("Game not found.")
    trashed = []
    for p in (g["path"], g["manifest"]):
        if os.path.exists(p):
            dest = os.path.join(HOME, ".Trash", "%s %s" % (os.path.basename(p), time.strftime("%H%M%S")))
            shutil.move(p, dest)
            trashed.append(dest)
    out({"message": "Moved %s to the Trash. Empty the Trash to free the space." % g["name"], "trashed": trashed})


def cmd_set_exe(appid, exe_rel):
    cfg = load_config()
    cfg["games"].setdefault(appid, {})["exe"] = exe_rel
    save_config(cfg)
    out({"message": "Main program set to %s." % exe_rel})


def cmd_gfx(appid, mode):
    if mode not in ("dxmt", "dxvk", "wine"):
        fail("mode must be dxmt, dxvk or wine")
    cfg = load_config()
    lo = launch_options_all()
    g = next((game_info(g, cfg, lo) for g in manifests() if g["appid"] == appid), None)
    if not g or not g["mainExe"]:
        fail("Couldn't find the game's program file.")
    st = status_data()
    if any(r["name"] == g["name"] for r in st["runningGames"]):
        fail("Quit the game first, then change graphics.")
    apply_gfx(os.path.join(g["path"], os.path.dirname(g["mainExe"])), os.path.basename(g["mainExe"]), mode)
    cfg["games"].setdefault(appid, {}).update(exe=g["mainExe"], mode=mode)
    save_config(cfg)
    out({"message": "%s will use %s." % (g["name"], GFX_NAMES[mode])})


GFX_NAMES = {"dxmt": "DXMT (DirectX 11 → Metal)", "dxvk": "DXVK (DirectX 11 → Vulkan → Metal)",
             "wine": "D3DMetal (DirectX 11/12 → Metal)"}


def apply_gfx(exe_dir, exe, mode):
    """Per-program DirectX translator on the Wine 11 engine (registry AppDefaults + DXMT DLLs beside the .exe)."""
    # remove our DXMT copies (only files identical to ours)
    for d in GFX_DLLS:
        p = os.path.join(exe_dir, d)
        if os.path.exists(p) and sha(p) == sha(os.path.join(DXMT_NATIVE, d)):
            os.remove(p)
    if mode == "dxmt":
        for d in GFX_DLLS:
            shutil.copy2(os.path.join(DXMT_NATIVE, d), os.path.join(exe_dir, d))
        set_overrides(exe, {"d3d11": "native,builtin", "dxgi": "native,builtin", "d3d10core": "native,builtin"})
    elif mode == "dxvk":
        set_overrides(exe, {"d3d11": "native,builtin", "dxgi": "native,builtin", "d3d10core": "native,builtin"})
    else:
        set_overrides(exe, None)


def cmd_launchopts(appid, opts):
    f = userdata_localconfig()
    if not f:
        fail("Sign in to Steam once first.")
    was_running = steam_running()
    if was_running and not stop_steam():
        kill_all()
    shutil.copy2(f, f + ".macx-backup")
    with open(f, encoding="utf-8", errors="replace") as fh:
        root = vdf_load(fh.read())
    apps = vdf_get(root, "UserLocalConfigStore", "Software", "Valve", "Steam", "apps", create=True)
    entry = vdf_get(apps, appid, create=True)
    for kv in entry:
        if kv[0].lower() == "launchoptions":
            kv[1] = opts
            break
    else:
        entry.append(["LaunchOptions", opts])
    with open(f + ".tmp", "w", encoding="utf-8") as fh:
        fh.write(vdf_dump(root) + "\n")
    os.replace(f + ".tmp", f)
    if was_running:
        start_steam()
    out({"message": "Launch options saved%s." % (" and Steam restarted" if was_running else "")})


def cmd_hud(on):
    cfg = load_config()
    cfg["hud"] = on == "on"
    save_config(cfg)
    out({"message": "FPS overlay %s. It takes effect the next time Steam starts." % ("on" if cfg["hud"] else "off")})


def storage_items():
    games = manifests()
    items = []
    for g in games:
        items.append(dict(id="game:" + g["appid"], group="Games", name=g["name"], path=g["path"], size=g["size"],
                          removable=False,
                          note="Use Games → Uninstall to remove it properly through Steam."))
    common = os.path.join(STEAMAPPS, "common")
    steam_total = du_bytes(STEAM_DIR)
    games_total = du_bytes(common)
    items += [
        dict(id="steam", group="Windows side (C: drive)", name="Steam for Windows (client, caches)", path=STEAM_DIR,
             size=max(steam_total - games_total, 0), removable=False,
             note="The Windows Steam app itself, without the games."),
        dict(id="rockstar", group="Windows side (C: drive)", name="Rockstar Games Launcher + Social Club",
             path=os.path.join(DRIVE_C, "Program Files", "Rockstar Games"),
             size=du_bytes(os.path.join(DRIVE_C, "Program Files", "Rockstar Games")), removable=False,
             note="Needed by GTA V."),
        dict(id="windows", group="Windows side (C: drive)", name="Windows system files (Wine)",
             path=os.path.join(DRIVE_C, "windows"), size=du_bytes(os.path.join(DRIVE_C, "windows")),
             removable=False, note="Wine's stand-in for C:\\Windows."),
        dict(id="saves", group="Windows side (C: drive)", name="Documents (game saves & settings)",
             path=os.path.join(DRIVE_C, "users", USER, "Documents"),
             size=du_bytes(os.path.join(DRIVE_C, "users", USER, "Documents")),
             removable=False, note="GTA V saves: Documents/Rockstar Games/GTA V/Profiles."),
        dict(id="wine", group="Engine", name="Wine 11 (with patched Mac driver)", path=WINE_APP,
             size=du_bytes(WINE_APP), removable=False, note="Runs Windows programs. Don't remove."),
        dict(id="gfx", group="Engine", name="Graphics layers (DXMT, DXVK)", path=os.path.join(ROOT, "gfx"),
             size=du_bytes(os.path.join(ROOT, "gfx")), removable=False, note="DirectX → Metal translators."),
        dict(id="d3dm", group="Engine", name="Wine 11 + D3DMetal engine", path=D3DM_APP,
             size=du_bytes(D3DM_APP), removable=False, note="DirectX 11/12 → Metal (Apple D3DMetal, from your Game Porting Toolkit)."),
        dict(id="drop", group="MacX folder (W:)", name="MacX folder on the Desktop", path=DROP,
             size=du_bytes(DROP), removable=False, note="Everything you put in it; Windows sees it as drive W:."),
    ]
    if os.path.isdir(GPTK_PREFIX):
        items.append(dict(id="gptkc", group="Windows side (C: drive)", name="D3DMetal engine's C: drive",
                          path=os.path.join(GPTK_PREFIX, "drive_c"), size=du_bytes(GPTK_PREFIX), removable=False,
                          note="Programs installed with the D3DMetal engine."))
    return items


def cmd_storage():
    st = os.statvfs(HOME)
    out({"items": storage_items(), "freeBytes": st.f_bavail * st.f_frsize, "totalBytes": st.f_blocks * st.f_frsize,
         "root": ROOT})


def cmd_tool(name, engine="wine11"):
    tools = {"winecfg": ["winecfg"], "regedit": ["regedit"], "explorer": ["explorer", "W:\\"],
             "taskmgr": ["taskmgr"], "cmd": ["wineconsole", "cmd"], "control": ["control"]}
    if name not in tools or engine not in ENGINES:
        fail("unknown tool")
    ensure_engine(engine)
    wine(tools[name], wait=False, engine=engine)
    out({"message": "Opening %s (%s)." % (name, ENGINES[engine]["short"])})


def cmd_killall():
    kill_all()
    out({"message": "All Windows programs were force-quit."})


def cmd_repair():
    checks = []

    def check(name, ok, fix=None):
        if not ok and fix:
            try:
                fix()
                ok = "fixed"
            except Exception as e:  # noqa
                ok = False
                name += " (%s)" % e
        checks.append({"name": name, "status": "ok" if ok is True else ("fixed" if ok == "fixed" else "problem")})

    check("Wine 11 engine present", os.path.exists(os.path.join(WINEBIN, "wine")))
    check("D3DMetal engine present (Game Porting Toolkit)", engine_ok("d3dmetal"))
    check("MacX folder on the Desktop", os.path.isdir(DROP), setup_drop)
    for eid, e in ENGINES.items():
        if os.path.isdir(os.path.join(e["prefix"], "dosdevices")):
            check("Drive W: linked in %s" % e["short"], drive_linked(eid), lambda eid=eid: link_drive(eid))
    mac = os.path.join(WINE_LIB, "x86_64-unix", "winemac.so")
    r = subprocess.run(["nm", "-gU", mac], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    check("Mac driver has DXMT support (patched winemac.so)", "_macdrv_functions" in r.stdout)
    check("DXMT Metal bridge installed",
          os.path.exists(os.path.join(WINE_LIB, "x86_64-unix", "winemetal.so")) and
          os.path.exists(os.path.join(WINE_LIB, "x86_64-windows", "winemetal.dll")))

    def fix_dxvk():
        for arch, d in (("x64", "system32"), ("x32", "syswow64")):
            for dll in GFX_DLLS:
                shutil.copy2(os.path.join(DXVK_FULL, arch, dll), os.path.join(DRIVE_C, "windows", d, dll))
    check("DXVK files in the Windows system folder",
          all(sha(os.path.join(DRIVE_C, "windows", "system32", d)) == sha(os.path.join(DXVK_FULL, "x64", d))
              for d in GFX_DLLS), fix_dxvk)

    cef = os.path.join(STEAM_DIR, "bin", "cef", "cef.win64")

    def fix_steam_wrap():
        if not os.path.exists(os.path.join(cef, "steamwebhelper_real.exe")):
            shutil.move(os.path.join(cef, "steamwebhelper.exe"), os.path.join(cef, "steamwebhelper_real.exe"))
        shutil.copy2(STEAM_WRAP, os.path.join(cef, "steamwebhelper.exe"))
    check("Steam window fix (webhelper wrapper)",
          sha(os.path.join(cef, "steamwebhelper.exe")) == sha(STEAM_WRAP), fix_steam_wrap)

    if os.path.isdir(SC_DIR):
        def fix_sc_wrap():
            if not os.path.exists(os.path.join(SC_DIR, "SocialClubHelper_real.exe")):
                shutil.move(os.path.join(SC_DIR, "SocialClubHelper.exe"),
                            os.path.join(SC_DIR, "SocialClubHelper_real.exe"))
            shutil.copy2(CEF_WRAP, os.path.join(SC_DIR, "SocialClubHelper.exe"))
            with open(os.path.join(SC_DIR, "wrap_flags.txt"), "w") as fh:
                fh.write("--in-process-gpu --disable-gpu --disable-gpu-compositing")
        check("Rockstar launcher window fix (Social Club wrapper)",
              sha(os.path.join(SC_DIR, "SocialClubHelper.exe")) == sha(CEF_WRAP), fix_sc_wrap)

        # DXVK for the launcher's windows; D3DMetal's DirectX 12 / GPU-vendor DLLs hidden from it (its D3D12
        # probe would load D3DMetal's d3d12 next to DXVK's dxgi and crash). The game itself keeps D3DMetal.
        want = {"d3d11": "native,builtin", "dxgi": "native,builtin", "d3d10core": "native,builtin",
                "d3d12": "", "nvapi64": "", "atidxx64": ""}
        for exe in ("Launcher.exe", "SocialClubHelper.exe", "SocialClubHelper_real.exe", "RockstarService.exe"):
            ov = app_overrides(exe)
            check("Rockstar %s uses DXVK, not D3DMetal" % exe, all(ov.get(k) == v for k, v in want.items()),
                  lambda exe=exe: set_overrides(exe, want))
    out({"checks": checks})


def cmd_paths():
    user = USER
    out({"paths": [
        {"name": "MacX folder (drive W:)", "path": DROP},
        {"name": "Everything for this setup", "path": ROOT},
        {"name": "Windows C: drive (Wine 11)", "path": DRIVE_C},

        {"name": "Program logs", "path": LOGS},
        {"name": "Installed Steam games", "path": os.path.join(STEAMAPPS, "common")},
        {"name": "Game saves & settings (Documents)", "path": os.path.join(DRIVE_C, "users", user, "Documents")},
        {"name": "Wine engine", "path": WINE_APP},
        {"name": "Steam log", "path": STEAM_LOG},
        {"name": "Rockstar launcher log",
         "path": os.path.join(DRIVE_C, "users", user, "Documents", "Rockstar Games", "Launcher", "launcher.log")},
        {"name": "Steam's own logs", "path": os.path.join(STEAM_DIR, "logs")},
    ]})


# ----------------------------------------------------------------------------- MacX folder (drive W:)
HIDDEN = {".DS_Store", "Icon\r", ".windows-label", ".windows-serial", ".localized"}
EXT_KIND = {".exe": "program", ".msi": "installer", ".lnk": "shortcut", ".bat": "script", ".cmd": "script",
            ".iso": "disk", ".zip": "archive", ".7z": "archive", ".rar": "archive", ".reg": "registry"}
INSTALLER_RE = re.compile(r"(^setup|setup[_\-. ]|install|^gog_|\binst\b)", re.I)
UNWANTED_LNK = re.compile(r"(unins|uninstall|readme|manual|website|help|support|license|eula|homepage|forum)", re.I)
API_PATTERNS = [(b"d3d12.dll", "dx12"), (b"d3d11.dll", "dx11"), (b"d3d10", "dx10"), (b"d3d9.dll", "dx9"),
                (b"vulkan-1.dll", "vulkan"), (b"opengl32.dll", "opengl")]
DISK_LETTERS = "defghijklmnopqrstuvxy"


def setup_drop():
    os.makedirs(DROP, exist_ok=True)
    label = os.path.join(DROP, ".windows-label")  # Wine reads the drive's volume name from this file
    if not os.path.exists(label):
        with open(label, "w") as f:
            f.write(DROP_LABEL)
    for eid in ENGINES:
        link_drive(eid)


def drive_linked(engine):
    link = os.path.join(ENGINES[engine]["prefix"], "dosdevices", DROP_LETTER + ":")
    return os.path.islink(link) and os.path.realpath(link) == os.path.realpath(DROP)


def link_drive(engine):
    dd = os.path.join(ENGINES[engine]["prefix"], "dosdevices")
    if not os.path.isdir(dd) or drive_linked(engine):
        return
    link = os.path.join(dd, DROP_LETTER + ":")
    if os.path.islink(link):
        os.remove(link)
    if not os.path.exists(link):
        os.symlink(DROP, link)


def ensure_engine(engine):
    if not engine_ok(engine):
        fail("%s isn't installed." % ENGINES[engine]["name"])
    e = ENGINES[engine]
    if not os.path.isdir(os.path.join(e["prefix"], "drive_c")):
        os.makedirs(e["prefix"], exist_ok=True)
        wine(["wineboot", "--init"], engine=engine, timeout=600)
        subprocess.run([e["server"], "-w"], env=wine_env(engine=engine), timeout=600,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if engine == "d3dmetal":
        sys32 = os.path.join(e["prefix"], "drive_c", "windows", "system32")
        if sha(os.path.join(sys32, "ntdlx.dll")) != sha(NTDLX):
            shutil.copy2(NTDLX, os.path.join(sys32, "ntdlx.dll"))
        # Games load NVIDIA's DLLs by full path (C:\windows\system32\nvapi64.dll), which needs a file there;
        # GTA V Enhanced retries forever without one. Install D3DMetal's versions like Wine's own DLLs.
        lib = os.path.join(D3DM_APP, "Contents", "Resources", "wine", "lib", "wine", "x86_64-windows")
        for dll in ("nvapi64.dll", "nvngx.dll", "d3dmt.dll"):
            if sha(os.path.join(sys32, dll)) != sha(os.path.join(lib, dll)):
                shutil.copy2(os.path.join(lib, dll), os.path.join(sys32, dll))
    setup_drop()


def pe_info(path, cfg):
    """64/32-bit and which graphics APIs a Windows program loads (cached until the file changes)."""
    try:
        st = os.stat(path)
    except OSError:
        return {"bits": None, "apis": []}
    c = cfg["detect"].get(path)
    if c and c.get("mtime") == int(st.st_mtime) and c.get("size") == st.st_size:
        return c
    bits, found = None, set()
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
            if head[:2] == b"MZ" and len(head) >= 0x40:
                off = struct.unpack_from("<I", head, 0x3C)[0]
                f.seek(off)
                sig = f.read(6)
                if sig[:4] == b"PE\0\0":
                    bits = 64 if struct.unpack_from("<H", sig, 4)[0] in (0x8664, 0xAA64) else 32
            f.seek(0)
            tail, read = b"", 0
            while read < (1536 << 20):
                chunk = f.read(4 << 20)
                if not chunk:
                    break
                read += len(chunk)
                buf = (tail + chunk).lower()
                for pat, name in API_PATTERNS:
                    if name not in found and pat in buf:
                        found.add(name)
                tail = chunk[-16:]
    except OSError:
        pass
    exe_dir = os.path.dirname(path)
    if os.path.exists(os.path.join(exe_dir, "D3D12", "D3D12Core.dll")):  # DirectX 12 Agility SDK
        found.add("dx12")
    c = {"mtime": int(st.st_mtime), "size": st.st_size, "bits": bits,
         "apis": [n for _, n in API_PATTERNS if n in found]}
    cfg["detect"][path] = c
    cfg["_dirty"] = True
    return c


def api_label(apis):
    for key, label in (("dx12", "DirectX 12"), ("dx11", "DirectX 11"), ("dx10", "DirectX 10"), ("dx9", "DirectX 9"),
                       ("vulkan", "Vulkan"), ("opengl", "OpenGL")):
        if key in apis:
            return label
    return "Unknown"


def auto_engine(info):
    if "dx12" in info.get("apis", []) and info.get("bits") != 32 and engine_ok("d3dmetal"):
        return "d3dmetal"
    return "wine11"


def auto_gfx(info, loose=False):
    """DXMT for DirectX 10/11. A loose .exe (not in its own folder) gets DXVK, so no DLLs are copied next to it."""
    apis = info.get("apis", [])
    if "dx11" in apis or "dx10" in apis:
        return "dxvk" if loose or not os.path.isdir(DXMT_NATIVE) else "dxmt"
    return "wine"


def disk_state(cfg, iid):
    d = cfg["disks"].get(iid)
    if d and os.path.isdir(d.get("mount", "")):
        return d
    return None


def drop_items(cfg=None, with_info=True):
    cfg = cfg or load_config()
    if not os.path.isdir(DROP):
        return []
    running = running_drop_items(wine_processes())
    items = []
    for name in sorted(os.listdir(DROP), key=str.lower):
        if name in HIDDEN or name.startswith(".") or name.lower() in GFX_DLLS:
            continue
        path = os.path.join(DROP, name)
        icfg = cfg["items"].get(name, {})
        stem, ext = os.path.splitext(name)
        ext = ext.lower()
        exes, main, base = [], None, DROP
        if os.path.isdir(path):
            base = path
            exes = list_exes(path) + [os.path.relpath(p, path) for p in glob.glob(os.path.join(path, "*.msi"))]
            playable = [e for e in exes if e.lower().endswith(".exe") and not SKIP_EXE.search(os.path.basename(e))]
            setups = [e for e in exes if e.lower().endswith(".msi") or INSTALLER_RE.search(os.path.basename(e))]
            if playable:
                kind = "folder"
                main = icfg.get("exe") if icfg.get("exe") in exes else guess_main_exe(path, playable)
            elif setups:
                kind = "installer"
                main = icfg.get("exe") if icfg.get("exe") in exes else setups[0]
            else:
                kind = "files"
                main = exes[0] if exes else None
            display = name
        else:
            kind = EXT_KIND.get(ext, "file")
            if kind == "program" and INSTALLER_RE.search(name):
                kind = "installer"
            if kind in ("program", "installer"):
                exes, main = [name], name
            display = stem if kind in ("program", "shortcut") else name
        info = {"bits": None, "apis": []}
        if with_info and main and main.lower().endswith(".exe"):
            info = pe_info(os.path.join(base, main), cfg)
        engine = icfg.get("engine", "auto")
        auto_e = auto_engine(info) if kind in ("program", "folder") else "wine11"
        gfx = icfg.get("gfx", "auto")
        ag = auto_gfx(info, loose=os.path.isfile(path))
        procs = running.get(name, [])
        disk = disk_state(cfg, name) if kind == "disk" else None
        items.append({
            "id": name,
            "name": display,
            "kind": kind,
            "path": path,
            "winPath": "%s:\\%s" % (DROP_LETTER.upper(), name),
            "baseDir": base,
            "exes": exes,
            "mainExe": main,
            "bits": info.get("bits"),
            "apis": info.get("apis", []),
            "api": api_label(info.get("apis", [])),
            "engine": engine,
            "autoEngine": auto_e,
            "effectiveEngine": auto_e if engine == "auto" or not engine_ok(engine) else engine,
            "gfx": gfx,
            "autoGfx": ag,
            "effectiveGfx": ag if gfx == "auto" else gfx,
            "args": icfg.get("args", ""),
            "size": os.path.getsize(path) if os.path.isfile(path) else -1,
            "running": bool(procs),
            "pids": [p["pid"] for p in procs],
            "diskLetter": (disk["letter"].upper() + ":") if disk else None,
            "log": os.path.join(LOGS, re.sub(r"[^\w.-]+", "_", name) + ".log"),
        })
    if cfg.pop("_dirty", False):
        save_config(cfg)
    return items


def find_item(iid, cfg=None):
    it = next((i for i in drop_items(cfg) if i["id"] == iid), None)
    if not it:
        fail("“%s” isn't in the MacX folder any more." % iid)
    return it


def spawn_logged(engine, args, cwd, log_path, env_extra=None):
    os.makedirs(LOGS, exist_ok=True)
    env = {"WINEDEBUG": "fixme-all"}
    if load_config().get("hud"):
        env["MTL_HUD_ENABLED"] = "1"
    env.update(env_extra or {})
    with open(log_path, "wb") as log:
        log.write(("$ %s %s\n" % (ENGINES[engine]["short"], " ".join(args))).encode())
        log.flush()
        subprocess.Popen([ENGINES[engine]["wine"]] + args, cwd=cwd, env=wine_env(env, engine), stdout=log,
                         stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)


def cmd_items():
    out({"items": drop_items(), "drop": DROP, "exists": os.path.isdir(DROP)})


def cmd_setup():
    setup_drop()
    out({"message": "The MacX folder is on your Desktop and shows up as drive W: in Windows.",
         "drop": DROP})


def cmd_launch(iid):
    cfg = load_config()
    it = find_item(iid, cfg)
    if it["running"]:
        fail("%s is already running." % it["name"])
    engine = it["effectiveEngine"]
    ensure_engine(engine)
    kind = it["kind"]
    cwd = DROP
    if kind in ("program", "folder", "installer", "files"):
        if not it["mainExe"]:
            fail("There's no Windows program in “%s”." % it["name"])
        exe = os.path.join(it["baseDir"], it["mainExe"])
        cwd = os.path.dirname(exe)
        if exe.lower().endswith(".msi"):
            args = ["msiexec", "/i", unix_to_win(exe)]
        else:
            if engine == "wine11" and kind != "installer":
                applied = cfg["items"].get(iid, {}).get("appliedGfx")
                if applied != [it["mainExe"], it["effectiveGfx"]]:
                    apply_gfx(cwd, os.path.basename(exe), it["effectiveGfx"])
                    cfg = load_config()
                    cfg["items"].setdefault(iid, {})["appliedGfx"] = [it["mainExe"], it["effectiveGfx"]]
                    save_config(cfg)
            try:
                extra = shlex.split(it["args"])
            except ValueError:
                fail("The launch options have an unmatched quote.")
            args = [unix_to_win(exe)] + extra
        verb = "Installing" if kind == "installer" else "Starting"
    elif kind == "shortcut" or kind == "file":
        args, verb = ["start", "/unix", it["path"]], "Opening"
    elif kind == "script":
        args, verb = ["wineconsole", "cmd", "/k", it["winPath"]], "Running"
    else:
        fail("Use the buttons for this kind of file.")
    spawn_logged(engine, args, cwd, it["log"])
    gfx_label = {"dxmt": "DXMT", "dxvk": "DXVK", "wine": "Wine built-in DirectX"}[it["effectiveGfx"]]
    how = ENGINES[engine]["short"] + ("" if engine != "wine11" or kind not in ("program", "folder")
                                      else " + " + gfx_label)
    out({"message": "%s %s with %s. The first start can take a minute." % (verb, it["name"], how)})


def cmd_stop(iid):
    it = find_item(iid)
    for pid in it["pids"]:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    time.sleep(2)
    for pid in find_item(iid)["pids"]:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    out({"message": "Closed %s." % it["name"]})


def cmd_item_set(iid, field, value):
    if field not in ("exe", "engine", "gfx", "args"):
        fail("unknown setting")
    if field == "engine" and value not in ("auto",) + tuple(ENGINES):
        fail("unknown engine")
    if field == "gfx" and value not in ("auto", "dxmt", "dxvk", "wine"):
        fail("unknown graphics mode")
    cfg = load_config()
    entry = cfg["items"].setdefault(iid, {})
    if value in ("", "auto") and field != "args":
        entry.pop(field, None)
    else:
        entry[field] = value
    save_config(cfg)
    out({"message": "Saved."})


def free_letter():
    used = set()
    for e in ENGINES.values():
        dd = os.path.join(e["prefix"], "dosdevices")
        if os.path.isdir(dd):
            used |= {n[0] for n in os.listdir(dd) if len(n) == 2 and n[1] == ":"}
    return next((l for l in DISK_LETTERS if l not in used), None)


def cmd_mount(iid):
    cfg = load_config()
    it = find_item(iid, cfg)
    if it["diskLetter"]:
        return out({"message": "Already in drive %s." % it["diskLetter"]})
    r = subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-plist", it["path"]],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if r.returncode != 0:
        fail("macOS couldn't open the disc image: %s" % r.stderr.decode("utf-8", "replace").strip())
    ents = plistlib.loads(r.stdout).get("system-entities", [])
    mount = next((e["mount-point"] for e in ents if e.get("mount-point")), None)
    dev = next((e["dev-entry"] for e in ents if e.get("dev-entry")), None)
    if not mount:
        subprocess.run(["hdiutil", "detach", dev], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        fail("The disc image has no readable files.")
    letter = free_letter()
    if not letter:
        fail("No free drive letters.")
    for eid, e in ENGINES.items():
        dd = os.path.join(e["prefix"], "dosdevices")
        if engine_ok(eid) and os.path.isdir(dd):
            os.symlink(mount, os.path.join(dd, letter + ":"))
            wine(["reg", "add", "HKLM\\Software\\Wine\\Drives", "/v", letter + ":", "/d", "cdrom", "/f"], engine=eid)
    cfg["disks"][iid] = {"letter": letter, "mount": mount, "dev": dev}
    save_config(cfg)
    out({"message": "%s is now in disc drive %s:. Open it from the Windows file manager, or run its setup."
                    % (it["name"], letter.upper())})


def unmount(cfg, iid):
    d = cfg["disks"].pop(iid, None)
    if not d:
        return
    for eid, e in ENGINES.items():
        link = os.path.join(e["prefix"], "dosdevices", d["letter"] + ":")
        if os.path.islink(link):
            os.remove(link)
            wine(["reg", "delete", "HKLM\\Software\\Wine\\Drives", "/v", d["letter"] + ":", "/f"], engine=eid)
    if os.path.isdir(d.get("mount", "")):
        subprocess.run(["hdiutil", "detach", d.get("dev") or d["mount"]], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=60)


def cmd_unmount(iid):
    cfg = load_config()
    unmount(cfg, iid)
    save_config(cfg)
    out({"message": "Ejected %s." % iid})


def cmd_disk_setup(iid):
    """Run the setup/autorun program on a mounted disc image."""
    cfg = load_config()
    d = disk_state(cfg, iid)
    if not d:
        fail("Insert the disc first.")
    root = d["mount"]
    target = None
    try:
        with open(os.path.join(root, "autorun.inf"), encoding="utf-8", errors="replace") as f:
            m = re.search(r"^\s*open\s*=\s*(\S+)", f.read(), re.I | re.M)
            if m:
                target = m.group(1).replace("\\", "/")
    except OSError:
        pass
    if not target or not os.path.exists(os.path.join(root, target)):
        target = next((n for n in sorted(os.listdir(root)) if re.fullmatch(r"(setup|install|autorun)\.(exe|msi)", n, re.I)),
                      None)
    if not target:
        fail("No setup program found on the disc. Open the drive in the Windows file manager instead.")
    win = "%s:\\%s" % (d["letter"].upper(), target.replace("/", "\\"))
    engine = cfg["items"].get(iid, {}).get("engine", "wine11")
    engine = engine if engine in ENGINES and engine_ok(engine) else "wine11"
    ensure_engine(engine)
    args = ["msiexec", "/i", win] if target.lower().endswith(".msi") else [win]
    spawn_logged(engine, args, root, os.path.join(LOGS, re.sub(r"[^\w.-]+", "_", iid) + ".log"))
    out({"message": "Running %s from drive %s:." % (os.path.basename(target), d["letter"].upper())})


def cmd_extract(iid):
    it = find_item(iid)
    if it["kind"] != "archive":
        fail("That isn't an archive.")
    stem = os.path.splitext(it["id"])[0]
    dest, n = os.path.join(DROP, stem), 2
    while os.path.exists(dest):
        dest, n = os.path.join(DROP, "%s (%d)" % (stem, n)), n + 1
    os.makedirs(dest)
    r = subprocess.run(["/usr/bin/tar", "-xf", it["path"], "-C", dest], stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, timeout=3600)
    if r.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        fail("Couldn't unpack it: %s" % r.stderr.decode("utf-8", "replace").strip()[:300])
    inner = [n for n in os.listdir(dest) if n not in HIDDEN and n != "__MACOSX"]
    if len(inner) == 1 and os.path.isdir(os.path.join(dest, inner[0])):  # archive had one top folder: flatten it
        tmp = dest + ".wp-tmp"
        os.rename(os.path.join(dest, inner[0]), tmp)
        shutil.rmtree(dest)
        os.rename(tmp, dest)
    out({"message": "Unpacked into “%s”." % os.path.basename(dest)})


def cmd_regimport(iid):
    it = find_item(iid)
    engine = load_config()["items"].get(iid, {}).get("engine", "wine11")
    engine = engine if engine in ENGINES and engine_ok(engine) else "wine11"
    ensure_engine(engine)
    code, _ = wine(["regedit", "/S", it["winPath"]], engine=engine, timeout=120)
    if code != 0:
        fail("The registry import failed.")
    out({"message": "Imported %s into the %s registry." % (it["id"], ENGINES[engine]["short"])})


def cmd_trash(iid):
    cfg = load_config()
    it = find_item(iid, cfg)
    if it["running"]:
        fail("Close it first.")
    if it["kind"] == "disk":
        unmount(cfg, iid)
    cfg["items"].pop(iid, None)
    save_config(cfg)
    dest = os.path.join(HOME, ".Trash", "%s %s" % (iid, time.strftime("%H%M%S")))
    shutil.move(it["path"], dest)
    out({"message": "Moved %s to the Trash." % it["name"]})


def cmd_open(path):
    """A file opened from Finder (Open With → MacX)."""
    real = os.path.realpath(path)
    boxes = os.path.realpath(BOXES_DIR) + os.sep
    if real.startswith(boxes):           # inside a box: install / unpack / play it there, not in the shared setup
        import macxbox
        parts = real[len(boxes):].split(os.sep)
        box, entry = parts[0], parts[1] if len(parts) > 1 else ""
        it = next((f for f in macxbox.box_view(box)["files"] if f["id"] == entry), None)
        if not it:
            fail("MacX can't open that from inside the box.")
        if it["kind"] in ("installer", "archive", "disk"):
            return out(macxbox.start_setup(box, [entry]))
        return out(macxbox.play(box, entry))
    drop = os.path.realpath(DROP)
    if real.startswith(drop + os.sep):
        iid = os.path.relpath(real, drop).split(os.sep)[0]
        it = find_item(iid)
        if it["kind"] in ("program", "folder", "installer", "shortcut", "script", "file") and (
                os.path.isfile(os.path.join(DROP, iid)) or real == os.path.join(drop, iid, it["mainExe"] or "")):
            return cmd_launch(iid)
    if not os.path.exists(path):
        fail("File not found.")
    cfg = load_config()
    info = pe_info(path, cfg) if path.lower().endswith(".exe") else {}
    engine = auto_engine(info) if info else "wine11"
    if engine == "wine11" and {"dx10", "dx11"} & set(info.get("apis", [])) and engine_ok("d3dmetal"):
        engine = "d3dmetal"   # DXMT needs DLLs beside the program; D3DMetal handles DirectX 11 as is
    if cfg.pop("_dirty", False):
        save_config(cfg)
    ensure_engine(engine)
    win = unix_to_win(path)
    args = ["msiexec", "/i", win] if path.lower().endswith(".msi") else (
        [win] if path.lower().endswith(".exe") else ["start", "/unix", path])
    spawn_logged(engine, args, os.path.dirname(path),
                 os.path.join(LOGS, re.sub(r"[^\w.-]+", "_", os.path.basename(path)) + ".log"))
    out({"message": "Started %s with %s." % (os.path.basename(path), ENGINES[engine]["short"])})


# ----------------------------------------------------------------------------- installed programs (Start Menu)
def start_menu():
    progs, seen_prefix = [], set()
    for eid, e in ENGINES.items():
        if e["prefix"] in seen_prefix:
            continue
        seen_prefix.add(e["prefix"])
        if e["prefix"] == PREFIX and engine_ok("d3dmetal"):
            eid, e = "d3dmetal", ENGINES["d3dmetal"]  # same C: drive; the engine Steam runs on
        c = os.path.join(e["prefix"], "drive_c")
        for root in (os.path.join(c, "ProgramData", "Microsoft", "Windows", "Start Menu", "Programs"),
                     os.path.join(c, "users", USER, "AppData", "Roaming", "Microsoft", "Windows", "Start Menu",
                                  "Programs")):
            for dirpath, _, files in os.walk(root):
                for f in sorted(files):
                    if not f.lower().endswith(".lnk") or UNWANTED_LNK.search(f):
                        continue
                    folder = os.path.relpath(dirpath, root)
                    progs.append({"id": eid + ":" + os.path.join(dirpath, f), "name": f[:-4],
                                  "folder": "" if folder == "." else folder, "path": os.path.join(dirpath, f),
                                  "engine": eid, "engineName": e["short"]})
    seen, res = set(), []
    for p in sorted(progs, key=lambda p: (p["engine"], p["name"].lower())):
        if (p["engine"], p["name"].lower()) not in seen:
            seen.add((p["engine"], p["name"].lower()))
            res.append(p)
    return res


def cmd_programs():
    out({"programs": start_menu()})


def cmd_run_lnk(engine, path):
    if engine not in ENGINES or not os.path.exists(path):
        fail("Shortcut not found.")
    ensure_engine(engine)
    spawn_logged(engine, ["start", "/unix", path], os.path.dirname(path),
                 os.path.join(LOGS, re.sub(r"[^\w.-]+", "_", os.path.basename(path)) + ".log"))
    out({"message": "Starting %s." % os.path.basename(path)[:-4]})


def cmd_engine_setup(engine):
    if engine not in ENGINES:
        fail("unknown engine")
    ensure_engine(engine)
    out({"message": "%s is ready, with its own C: drive and the W: drive." % ENGINES[engine]["name"]})


def cmd_desktop(engine, size):
    if engine not in ENGINES or not re.fullmatch(r"\d{3,5}x\d{3,5}", size or ""):
        fail("bad desktop request")
    ensure_engine(engine)
    wine(["explorer", "/desktop=MacX,%s" % size, "explorer.exe", "W:\\"], wait=False, engine=engine)
    out({"message": "Opening the Windows desktop (%s). Close its window to leave it." % ENGINES[engine]["short"]})


def main():
    a = sys.argv[1:]
    if not a:
        fail("no command")
    c = a[0]
    if c == "box":
        import macxbox
        try:
            return out(macxbox.main(a[1:]))
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001 - reported to the app
            fail("%s: %s" % (type(e).__name__, e))
    if c in ("preflight", "install", "install-steam", "install-status"):
        import macxinstall
        sys.argv = [sys.argv[0], "status" if c == "install-status" else c]
        res = {"preflight": lambda: {"checks": macxinstall.preflight()}, "install": macxinstall.install,
               "install-steam": macxinstall.install_steam}.get(c)
        if res:
            return out(res())
        try:
            with open(macxinstall.STATUS) as f:
                return out(json.load(f))
        except OSError:
            return out({"step": "", "done": False})
    try:
        if c == "status": cmd_status()
        elif c == "games": cmd_games()
        elif c == "steam": cmd_steam(a[1])
        elif c == "play": cmd_play(a[1])
        elif c == "install": cmd_install(a[1])
        elif c == "uninstall": cmd_uninstall(a[1])
        elif c == "uninstall-force": cmd_uninstall_force(a[1])
        elif c == "set-exe": cmd_set_exe(a[1], a[2])
        elif c == "gfx": cmd_gfx(a[1], a[2])
        elif c == "launchopts": cmd_launchopts(a[1], a[2] if len(a) > 2 else "")
        elif c == "hud": cmd_hud(a[1])
        elif c == "storage": cmd_storage()
        elif c == "run" or c == "open": cmd_open(a[1])
        elif c == "tool": cmd_tool(a[1], a[2] if len(a) > 2 else "wine11")
        elif c == "setup": cmd_setup()
        elif c == "items": cmd_items()
        elif c == "launch": cmd_launch(a[1])
        elif c == "stop": cmd_stop(a[1])
        elif c == "item-set": cmd_item_set(a[1], a[2], a[3] if len(a) > 3 else "")
        elif c == "mount": cmd_mount(a[1])
        elif c == "unmount": cmd_unmount(a[1])
        elif c == "disk-setup": cmd_disk_setup(a[1])
        elif c == "extract": cmd_extract(a[1])
        elif c == "regimport": cmd_regimport(a[1])
        elif c == "trash": cmd_trash(a[1])
        elif c == "programs": cmd_programs()
        elif c == "run-lnk": cmd_run_lnk(a[1], a[2])
        elif c == "engine-setup": cmd_engine_setup(a[1])
        elif c == "desktop": cmd_desktop(a[1], a[2])
        elif c == "killall": cmd_killall()
        elif c == "repair": cmd_repair()
        elif c == "paths": cmd_paths()
        else: fail("unknown command: " + c)
    except SystemExit:
        raise
    except Exception as e:
        fail("%s: %s" % (type(e).__name__, e))


if __name__ == "__main__":
    main()
