"""Rewrite ntdll.dll's three `mov %gs:0x60,%rax` (PEB via TSD slot 12, which macOS libc owns) into
`call stub` where stub = mov %gs:0x30,%rax ; mov 0x60(%rax),%rax ; ret  (PEB via TEB->Self)."""
import struct, sys
path = sys.argv[1]
d = bytearray(open(path, 'rb').read())
lf = struct.unpack_from('<I', d, 0x3c)[0]
nsec = struct.unpack_from('<H', d, lf + 6)[0]
opt = struct.unpack_from('<H', d, lf + 20)[0]
image_base = struct.unpack_from('<Q', d, lf + 24 + 24)[0]
text = None
for i in range(nsec):
    o = lf + 24 + opt + i * 40
    name = d[o:o + 8].rstrip(b'\0')
    vsize, va, rsize, raw = struct.unpack_from('<IIII', d, o + 8)
    if name == b'.text':
        text = (va, vsize, raw)
va, vsize, raw = text
OLD = bytes.fromhex('65488b042560000000')
STUB = bytes.fromhex('65488b042530000000' '488b4060' 'c3')
body = bytes(d[raw:raw + vsize])
sites = [i for i in range(len(body)) if body.startswith(OLD, i)]
print('sites', [hex(image_base + va + s) for s in sites])
assert len(sites) == 3, sites
cave = -1
for pad in (b'\xcc' * 16, b'\x90' * 16, b'\x00' * 16):
    cave = body.find(pad)
    if cave != -1:
        break
assert cave != -1
cave += 1  # keep a byte of padding before the stub
d[raw + cave:raw + cave + len(STUB)] = STUB
for s in sites:
    rel = cave - (s + 5)
    d[raw + s:raw + s + 9] = b'\xe8' + struct.pack('<i', rel) + bytes.fromhex('0f1f4000')
open(path, 'wb').write(d)
print('stub at', hex(image_base + va + cave))
