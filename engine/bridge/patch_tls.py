"""ntdll.dll: when the loader stores the current thread's TLS array (TEB+0x58), also mirror it into
TSD slot 11 (%gs:0x58), which Windows code reads directly in CrossOver mode. TLS callbacks run right
after this store, before any syscall could refresh the slot."""
import struct, sys

path = sys.argv[1]
d = bytearray(open(path, 'rb').read())
lf = struct.unpack_from('<I', d, 0x3c)[0]
nsec = struct.unpack_from('<H', d, lf + 6)[0]
opt = struct.unpack_from('<H', d, lf + 20)[0]
for i in range(nsec):
    o = lf + 24 + opt + i * 40
    if d[o:o + 8].rstrip(b'\0') == b'.text':
        vsize, va, rsize, raw = struct.unpack_from('<IIII', d, o + 8)
body = bytes(d[raw:raw + vsize])

OLD = bytes.fromhex('65488b042530000000'      # mov %gs:0x30,%rax
                    '48897858')               # mov %rdi,0x58(%rax)
STUB = bytes.fromhex('65488b042530000000'     # mov %gs:0x30,%rax
                     '48897858'               # mov %rdi,0x58(%rax)
                     '6548893c2558000000'     # mov %rdi,%gs:0x58
                     'c3')                    # ret

sites = [i for i in range(len(body)) if body.startswith(OLD, i)]
if not sites:
    sys.exit('already patched or pattern not found')
assert len(sites) == 1, sites
cave = body.find(b'\xcc' * 32, body.find(b'\xcc' * 16) + 32)   # a padding run past the PEB stub's
assert cave != -1
cave += 2
d[raw + cave:raw + cave + len(STUB)] = STUB
s = sites[0]
d[raw + s:raw + s + 13] = b'\xe8' + struct.pack('<i', cave - (s + 5)) + bytes.fromhex('0f1f840000000000')
open(path, 'wb').write(d)
print('patched TLS store at .text+%#x, stub at .text+%#x (%d bytes)' % (s, cave, len(STUB)))
