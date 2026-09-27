"""Encode the game archive containing a BSL Lua entry."""
import struct

ARCHIVE = '9ba626afa44a3aa3.patch_0'
TYPE = 0xA14E8DFA2CD117E2

def resource_hash(name):
    data = name.encode('utf-8')
    mask, mix = (1 << 64) - 1, 0xC6A4A7935BD1E995
    value = len(data) * mix & mask
    end = len(data) // 8 * 8
    for (word,) in struct.iter_unpack('<Q', data[:end]):
        word = word * mix & mask
        word ^= word >> 47
        value = (value ^ (word * mix & mask)) * mix & mask
    if data[end:]:
        value = (value ^ int.from_bytes(data[end:], 'little')) * mix & mask
    value ^= value >> 47
    value = value * mix & mask
    return value ^ (value >> 47)


def make_archive(resources):
    if not resources:
        raise ValueError('An archive needs at least one resource')
    count = len(resources)
    offset = (104 + 80 * count + 15) & ~15
    entries, body = bytearray(), bytearray(offset)
    for index, (name, resource) in enumerate(sorted(resources.items())):
        entries += struct.pack('<7Q6I', name, TYPE, offset, 0, 0, 0, 0,
                               len(resource), 0, 0, 16, 16, index)
        body += resource
        body += b'\0' * (-len(body) % 16)
        offset = len(body)
    header = struct.pack('<III20sQQ24s', 0xF0000011, 1, count, b'', offset, 0, b'')
    types = struct.pack('<IIQIIII', 0, 0, TYPE, count, 0, 16, 16)
    body[:104 + len(entries)] = header + types + entries
    return bytes(body)
