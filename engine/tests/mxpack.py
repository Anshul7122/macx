#!/usr/bin/env python3
"""Packs a folder into data-1.bin, data-2.bin, ... for engine/tests/mxsetup.c (the stand-in repack installer).

    mxpack.py <folder> <game name> <main exe, relative> <output dir> [part size in MB, default 64]
"""
import os
import struct
import sys


def main():
    src, game, main_exe, out = sys.argv[1:5]
    part_mb = int(sys.argv[5]) if len(sys.argv) > 5 else 64
    files = []
    for dirpath, _, names in os.walk(src):
        for n in sorted(names):
            if n.startswith("."):
                continue
            p = os.path.join(dirpath, n)
            files.append((os.path.relpath(p, src).replace("/", "\\"), p))

    def s(text):
        b = text.encode("utf-8")
        return struct.pack("<I", len(b)) + b

    os.makedirs(out, exist_ok=True)
    limit, part, written = part_mb << 20, 1, 0
    f = open(os.path.join(out, "data-%d.bin" % part), "wb")

    def put(data):
        nonlocal f, part, written
        while data:
            room = limit - written
            f.write(data[:room])
            written += min(room, len(data))
            data = data[room:]
            if written >= limit:
                f.close()
                part, written = part + 1, 0
                f = open(os.path.join(out, "data-%d.bin" % part), "wb")

    put(b"MXPK" + struct.pack("<I", 1) + s(game) + s(main_exe.replace("/", "\\")) + struct.pack("<I", len(files)))
    for rel, p in files:
        put(s(rel) + struct.pack("<Q", os.path.getsize(p)))
        with open(p, "rb") as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                put(chunk)
    f.close()
    if os.path.getsize(f.name) == 0:
        os.remove(f.name)
        part -= 1
    print("%s: %d files in %d part(s)" % (game, len(files), part))


if __name__ == "__main__":
    main()
