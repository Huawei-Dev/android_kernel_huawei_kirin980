#!/usr/bin/env python3
"""Build a Schumann FDT-of-DTBs catalog from kernel-compiled .dtb files.

Run from Kbuild after standard DTS->DTB compilation.  Each board DTB is
embedded without modification as the dtb-data property of its catalog entry.
The catalog is an FDT container, NOT a DTB that can be booted by Linux until
uniLoader selects and extracts a member.
"""

import argparse
from pathlib import Path
import struct
import subprocess
import sys

MAGIC = 0xD00DFEED
EXPECTED = {
    (8, 1, 0, 2): "SCM_W09_VA",
}

def fdt_identity(blob):
    if len(blob) < 56:
        raise ValueError("DTB header or reservation table truncated")
    (magic, total, off_struct, off_strings, off_mem, version, last,
     _bootcpu, len_strings, len_struct) = struct.unpack_from(">10I", blob)
    if magic != MAGIC or total != len(blob) or version < 16 or last > 17:
        raise ValueError("invalid FDT magic/header/totalsize")
    if (off_struct + len_struct > total or off_strings + len_strings > total
            or off_mem + 16 > total):
        raise ValueError("FDT section outside totalsize")
    strings = blob[off_strings:off_strings + len_strings]
    pos, end = off_struct, off_struct + len_struct
    nodes = []
    boardid, boardname = None, None
    saw_end = False
    while pos + 4 <= end:
        token, = struct.unpack_from(">I", blob, pos)
        pos += 4
        if token == 1:  # FDT_BEGIN_NODE
            zero = blob.find(b"\0", pos, end)
            if zero < 0:
                raise ValueError("unterminated FDT node")
            nodes.append(blob[pos:zero].decode("ascii"))
            pos = (zero + 4) & ~3
        elif token == 2:  # FDT_END_NODE
            if not nodes:
                raise ValueError("unbalanced FDT node")
            nodes.pop()
        elif token == 3:  # FDT_PROP
            if pos + 8 > end:
                raise ValueError("truncated FDT property")
            length, nameoff = struct.unpack_from(">II", blob, pos)
            pos += 8
            if pos + length > end or nameoff >= len(strings):
                raise ValueError("FDT property out of bounds")
            nameend = strings.find(b"\0", nameoff)
            if nameend < 0:
                raise ValueError("unterminated FDT property name")
            key = strings[nameoff:nameend]
            val = blob[pos:pos + length]
            pos = (pos + length + 3) & ~3
            if nodes == ["", "rootparam"]:
                if key == b"hisi,boardid":
                    if boardid is not None or length != 16:
                        raise ValueError("duplicate/malformed boardid")
                    boardid = struct.unpack(">4I", val)
                elif key == b"hisi,boardname":
                    if (boardname is not None or not val.endswith(b"\0")
                            or val.count(b"\0") != 1):
                        raise ValueError("duplicate/malformed boardname")
                    boardname = val[:-1].decode("ascii")
        elif token == 4:  # FDT_NOP
            continue
        elif token == 9:  # FDT_END
            saw_end = True
            break
        else:
            raise ValueError("invalid FDT token")
    if not saw_end or nodes or boardid is None or boardname is None:
        raise ValueError("missing FDT END or /rootparam identity")
    return boardid, boardname


def generate_catalog(output, dtbs, dtc, max_size):
    if len(dtbs) != len(EXPECTED):
        raise ValueError("expected exactly %d DTB inputs, received %d" % (len(EXPECTED), len(dtbs)))
    found = {}
    for path in dtbs:
        raw = path.read_bytes()
        boardid, name = fdt_identity(raw)
        if EXPECTED.get(boardid) != name:
            raise ValueError("%s has unexpected board %r / %r" % (path, boardid, name))
        if boardid in found:
            raise ValueError("duplicate boardid %r" % (boardid,))
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("%s exceeds 2 MiB per-board workspace" % path)
        found[boardid] = (name, path, len(raw))
    if set(found) != set(EXPECTED):
        raise ValueError("incomplete catalog: %r" % (set(EXPECTED) - set(found)))

    # Generate alongside the output so dtc's /incbin/ uses the compiled
    # DTB basenames in this same Kbuild object directory, not a source DTS.
    dts = output.with_suffix(".dts")
    lines = [
        "/dts-v1/;", "", "/ {",
        '\tcompatible = "huawei,schumann-dtb-catalog-v1";',
        '\tmodel = "Schumann EMUI10 DTB catalog";',
        "\tschumann,dtb-catalog {",
        '\t\tcompatible = "huawei,schumann-dtb-catalog-v1";',
    ]
    for boardid, (name, path, size) in sorted(found.items()):
        if path.parent.resolve() != output.parent.resolve():
            raise ValueError("input DTB not beside catalog: %s" % path)
        node = "-".join(map(str, boardid))
        lines.extend([
            "\t\tboard-%s {" % node,
            "\t\t\thisi,boardid = <%s>;" % " ".join(map(str, boardid)),
            '\t\t\tboard-name = "%s";' % name,
            '\t\t\tdtb-data = /incbin/("%s");' % path.name,
            "\t\t};",
        ])
    lines.extend(["\t};", "};", ""])
    dts.write_text("\n".join(lines))

    # DTC compiles only the catalog wrapper. Every member DTB is included
    # byte-for-byte using /incbin/; no second DTS->DTB compilation occurs.
    result = subprocess.run(
        [str(dtc), "-I", "dts", "-O", "dtb", "-o", str(output), str(dts)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        output.unlink(missing_ok=True)
        raise RuntimeError("catalog dtc failed:\n%s" % result.stderr)
    size = output.stat().st_size
    if max_size and size > max_size:
        output.unlink()
        raise ValueError("catalog exceeds limit: %d > %d bytes" % (size, max_size))
    print("Schumann catalog: %d boards, %d bytes" % (len(found), size))
    for boardid, (name, _path, n) in sorted(found.items()):
        print("  %-16s %s %d bytes" % (name, ".".join(map(str, boardid)), n))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--dtc", required=True, type=Path)
    p.add_argument("--dtb", required=True, action="append", type=Path)
    p.add_argument("--max-size", type=int, default=0,
                   help="optional maximum total catalog size in bytes")
    args = p.parse_args()
    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    generate_catalog(out, args.dtb, args.dtc, args.max_size)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        sys.exit("ERROR: %s" % exc)
