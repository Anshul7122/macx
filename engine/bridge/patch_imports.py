"""Point a PE DLL's ntdll.dll import at ntdlx.dll (same length, patched in place); or mark a DLL as Wine builtin."""
import struct, sys

def sections(d):
    lf = struct.unpack_from('<I', d, 0x3c)[0]
    nsec = struct.unpack_from('<H', d, lf + 6)[0]
    opt = struct.unpack_from('<H', d, lf + 20)[0]
    secs = []
    for i in range(nsec):
        o = lf + 24 + opt + i * 40
        vsize, va, rsize, raw = struct.unpack_from('<IIII', d, o + 8)
        secs.append((va, max(vsize, rsize), raw))
    return lf, secs

def rva2off(secs, rva):
    for va, size, raw in secs:
        if va <= rva < va + size:
            return rva - va + raw
    raise ValueError(hex(rva))

def patch_import(path):
    d = bytearray(open(path, 'rb').read())
    lf, secs = sections(d)
    imp_rva = struct.unpack_from('<I', d, lf + 24 + 120)[0]  # PE32+ data directory 1 (imports)
    off, n = rva2off(secs, imp_rva), 0
    while True:
        name_rva = struct.unpack_from('<I', d, off + 12)[0]
        if not name_rva:
            break
        no = rva2off(secs, name_rva)
        name = bytes(d[no:d.index(0, no)])
        if name.lower() == b'ntdll.dll':
            d[no:no + 9] = b'ntdlx.dll'
            n += 1
        off += 20
    open(path, 'wb').write(d)
    return n

def mark_builtin(path):
    d = bytearray(open(path, 'rb').read())
    sig = b'Wine builtin DLL\0'
    assert struct.unpack_from('<I', d, 0x3c)[0] >= 0x40 + len(sig)
    d[0x40:0x40 + len(sig)] = sig
    open(path, 'wb').write(d)

if __name__ == '__main__':
    if sys.argv[1] == '--builtin':
        mark_builtin(sys.argv[2]); print('marked', sys.argv[2])
    else:
        for p in sys.argv[1:]:
            print(p.split('/')[-1], 'patched imports:', patch_import(p))
