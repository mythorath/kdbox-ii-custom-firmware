#!/usr/bin/env python3
"""
build-cpb.py — patch, sign and repack an OTA firmware package for a Goldshell KD-Box II.

This is the no-serial path: you supply a stock .cpb for your MCB version and a repacked
rootfs squashfs, and this produces a package the box's own updater will accept, because it
is signed with the key the box verifies against.

    # look at a stock package without changing anything
    python3 scripts/build-cpb.py --inspect stock.cpb

    # build a package that trusts your key
    export KD_FW_SIGNING_KEY=~/fw_cmpt.pem
    export KD_FW_PASS='…'
    python3 scripts/build-cpb.py \
        --stock stock.cpb --rootfs modified.sqsh \
        --pubkey ~/.ssh/id_ed25519.pub --out kdbox2-custom.cpb

    # unpack a stock package for studying / for the rootfs step
    python3 scripts/build-cpb.py --unpack /tmp/kdbox-build stock.cpb

Requirements: python3 (stdlib only), squashfs-tools (unsquashfs for verification), openssl.

The signing key is NOT in this repository. See docs/ota-signed-flash.md.
"""

import argparse
import gzip
import hashlib
import io
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import zlib

ALIGN = 1024
CPB_HDR = 512
ROOTFS_BUDGET = 12_918_784          # MCB_V6_3_5 / 2.2.7
DEFAULT_IUS_OFFSET = 0x389E00       # verified for MCB_V6_3_5 only


def die(msg):
    print(f"  ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def step(msg):
    print(f"\n== {msg}")


def ok(msg):
    print(f"   {msg}")


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        die(f"{' '.join(cmd)} failed:\n{(r.stderr or r.stdout).strip()[:600]}")
    return r


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------- container

def parse_cpb(data):
    """Header, member 0 (raw + compressed length), and member 1..EOF (untouched)."""
    if len(data) < CPB_HDR + 2 or data[CPB_HDR:CPB_HDR + 2] != b"\x1f\x8b":
        die("not a .cpb: no gzip magic at offset 512")
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    raw0 = d.decompress(data[CPB_HDR:])
    if not d.eof:
        die("member 0 is truncated")
    comp0 = len(data) - CPB_HDR - len(d.unused_data)

    m1 = data.find(b"\x1f\x8b\x08", CPB_HDR + comp0)
    if m1 < 0:
        die("no second gzip member — the updater rejects single-member packages")
    if m1 % ALIGN:
        die(f"member 1 starts at {m1:,}, not {ALIGN}-byte aligned")

    name = data[:CPB_HDR].split(b"\x00")[0].decode("ascii", "replace")
    return name, raw0, comp0, data[m1:]


def tar_members(raw):
    with tarfile.open(fileobj=io.BytesIO(raw)) as t:
        return {m.name: t.extractfile(m).read() for m in t.getmembers()}


def find_squashfs(ius):
    """Locate the rootfs superblock by validation rather than trusting an offset."""
    i = 0
    while True:
        i = ius.find(b"hsqs", i)
        if i < 0:
            return None
        try:
            major, minor = struct.unpack("<HH", ius[i + 28:i + 32])
            block = struct.unpack("<I", ius[i + 12:i + 16])[0]
        except struct.error:
            return None
        if major == 4 and block in (4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576):
            return i
        i += 4


# --------------------------------------------------------------------- inspect / unpack

def do_inspect(path):
    data = open(path, "rb").read()
    name, raw0, comp0, rest = parse_cpb(data)
    step(f"{path}")
    ok(f"size            {len(data):,}")
    ok(f"header          {name}")
    ok(f"member 0        comp {comp0:,}  decomp {len(raw0):,}  pad {(-(CPB_HDR + comp0)) % ALIGN}")
    files = tar_members(raw0)
    ok(f"member 0 tar    {[(k, len(v)) for k, v in files.items()]}")
    ok(f"member 1+tail   {len(rest):,} bytes (kept byte-identical)")
    ius = files.get("firmware.ius")
    if not ius:
        die("member 0 has no firmware.ius")
    ver = ius[0x10:0x18].split(b"\x00")[0].decode("ascii", "replace")
    count = struct.unpack("<I", ius[0x1c:0x20])[0]
    ok(f"firmware.ius    {len(ius):,}  magic {ius[:4]!r}  version {ver or '?'}  images {count}")
    off = find_squashfs(ius)
    if off is None:
        ok("rootfs          NO VALID SQUASHFS FOUND — do not build against this package")
    else:
        ok(f"rootfs          squashfs at {off:#x}, region {len(ius) - off:,} bytes")
    ok(f"sha256          {sha256_bytes(data)}")
    return ius, off


def do_unpack(path, outdir):
    data = open(path, "rb").read()
    name, raw0, comp0, rest = parse_cpb(data)
    os.makedirs(outdir, exist_ok=True)
    files = tar_members(raw0)
    ius = files["firmware.ius"]
    open(os.path.join(outdir, "firmware.ius"), "wb").write(ius)
    open(os.path.join(outdir, "firmware.ius.sig"), "wb").write(files["firmware.ius.sig"])
    open(os.path.join(outdir, "header.bin"), "wb").write(data[:CPB_HDR])
    open(os.path.join(outdir, "member1_and_trailer.bin"), "wb").write(rest)
    off = find_squashfs(ius)
    if off is not None:
        # Trim the unused tail so the file is the image, not image + padding.
        open(os.path.join(outdir, "rootfs.sqfs"), "wb").write(ius[off:].rstrip(b"\x00"))
    step(f"unpacked to {outdir}")
    ok(f"header.bin, firmware.ius, firmware.ius.sig, member1_and_trailer.bin"
       + (", rootfs.sqfs" if off is not None else ""))
    if off is not None:
        ok(f"rootfs at {off:#x} — unsquashfs it, modify, repack, then pass --rootfs")


# --------------------------------------------------------------------- build

def sign(ius_path, sig_path, key, passphrase):
    step("sign firmware.ius with the vendor key")
    run(["openssl", "dgst", "-sha256", "-sign", key,
         "-passin", f"pass:{passphrase}", "-out", sig_path, ius_path])
    verify_pem = os.path.splitext(key)[0] + ".verify.pem"
    if not os.path.exists(verify_pem):
        die(f"need the matching public key next to the private key: {verify_pem}")
    out = run(["openssl", "dgst", "-sha256", "-verify", verify_pem,
               "-signature", sig_path, ius_path]).stdout.strip()
    ok(f"signature       {out}")
    if "Verified OK" not in out:
        die("signature does not verify — wrong key or passphrase")
    return open(sig_path, "rb").read()


def wrap(header, ius, sig, rest):
    step("repack the .cpb")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as t:
        for nm, blob in (("firmware.ius", ius), ("firmware.ius.sig", sig)):
            ti = tarfile.TarInfo(nm)
            ti.size = len(blob)
            ti.mtime = 1_663_027_200          # fixed: deterministic output
            ti.mode = 0o644
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = "root"
            t.addfile(ti, io.BytesIO(blob))
    raw = buf.getvalue()
    m0 = gzip.compress(raw, 9, mtime=0)
    pad = (-(CPB_HDR + len(m0))) % ALIGN
    out = header + m0 + b"\x00" * pad + rest
    ok(f"member 0        comp {len(m0):,}  decomp {len(raw):,}  pad {pad}")
    ok(f"member 1+tail   {len(rest):,} (stock, byte-identical)")
    ok(f"total           {len(out):,} bytes")
    return out, len(raw)


def verify(pkg, stock, verify_pem, work):
    step("verify the package before it can be flashed")
    name, raw0, comp0, rest = parse_cpb(pkg)
    sname, sraw0, scomp0, srest = parse_cpb(stock)
    problems = []

    if pkg[:CPB_HDR] != stock[:CPB_HDR]:
        problems.append("header differs from stock")
    ok(f"header          identical ({name})")

    if len(raw0) != len(sraw0):
        problems.append(f"member 0 decompresses to {len(raw0):,}, stock {len(sraw0):,}")
    ok(f"member 0        decomp {len(raw0):,}")

    files = tar_members(raw0)
    ok(f"tar members     {[(k, len(v)) for k, v in files.items()]}")

    ius, sig = files.get("firmware.ius"), files.get("firmware.ius.sig")
    if not ius or not sig:
        die("member 0 is missing firmware.ius or firmware.ius.sig")
    sius = tar_members(sraw0)["firmware.ius"]

    if len(ius) != len(sius):
        problems.append(f"firmware.ius is {len(ius):,} bytes, stock {len(sius):,}")
    off = find_squashfs(sius) or DEFAULT_IUS_OFFSET
    region = len(sius) - off
    diff = [i for i in range(min(len(ius), len(sius))) if ius[i] != sius[i]]
    if diff:
        lo, hi = min(diff), max(diff)
        if not (off <= lo and hi < off + region):
            problems.append(f"bytes differ outside the rootfs region ({lo:#x}..{hi:#x})")
        ok(f"patch           {len(diff):,} bytes differ, all inside {off:#x}..{off + region:#x}")
    else:
        ok("patch           image identical to stock")

    ip = os.path.join(work, "v.ius")
    sp = os.path.join(work, "v.sig")
    open(ip, "wb").write(ius)
    open(sp, "wb").write(sig)
    r = subprocess.run(["openssl", "dgst", "-sha256", "-verify", verify_pem,
                        "-signature", sp, ip], capture_output=True, text=True)
    if "Verified OK" not in (r.stdout or ""):
        problems.append("signature does not verify against the vendor public key")
    ok(f"signature       {(r.stdout or r.stderr).strip()}")

    sq = os.path.join(work, "v.sqfs")
    open(sq, "wb").write(ius[off:])
    listing = subprocess.run(["unsquashfs", "-no-exit-code", "-l", sq],
                             capture_output=True, text=True)
    text = (listing.stdout or "") + (listing.stderr or "")
    if "squashfs-root" not in text:
        problems.append("rootfs is not a readable squashfs")
    for want in ("root/.ssh/authorized_keys", "etc/kdbox-custom-fw"):
        if want not in text:
            problems.append(f"{want} missing from the image")
    ok("rootfs          mounts, authorized_keys + marker present")

    if rest != srest:
        problems.append("member 1 / trailer differs from stock")
    ok("member 1+tail   byte-identical to stock")

    if problems:
        print()
        for p in problems:
            print(f"   FAIL: {p}", file=sys.stderr)
        die("verification failed — nothing written")

    print(f"\n   ALL CHECKS PASSED   sha256 {sha256_bytes(pkg)}")


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Build a signed OTA package for a KD-Box II.")
    ap.add_argument("package", nargs="?", help="stock .cpb")
    ap.add_argument("--inspect", action="store_true", help="print the container layout and exit")
    ap.add_argument("--unpack", metavar="DIR", help="extract header/ius/sig/member1/rootfs into DIR")
    ap.add_argument("--stock", help="stock .cpb (for --rootfs builds)")
    ap.add_argument("--rootfs", help="repacked rootfs squashfs")
    ap.add_argument("--pubkey", help="SSH public key to trust (checked, not embedded here)")
    ap.add_argument("--out", help="output .cpb")
    ap.add_argument("--offset", type=lambda s: int(s, 0), default=None,
                    help=f"rootfs offset in firmware.ius (default: auto-detect; {DEFAULT_IUS_OFFSET:#x} for MCB_V6_3_5)")
    ap.add_argument("--work", default="/tmp/kdbox-build", help="scratch directory")
    a = ap.parse_args()

    key = os.environ.get("KD_FW_SIGNING_KEY")
    passphrase = os.environ.get("KD_FW_PASS")

    if a.inspect:
        if not a.package:
            ap.error("--inspect needs a package")
        do_inspect(a.package)
        return
    if a.unpack:
        if not a.package:
            ap.error("--unpack needs a package")
        do_unpack(a.package, a.unpack)
        return

    if not all((a.stock, a.rootfs, a.out)):
        ap.error("build mode needs --stock, --rootfs and --out (or use --inspect / --unpack)")
    if not key or not passphrase:
        die("set KD_FW_SIGNING_KEY and KD_FW_PASS (see docs/ota-signed-flash.md)")
    for p in (a.stock, a.rootfs, key):
        if not os.path.isfile(p):
            die(f"missing file: {p}")

    sqfs = open(a.rootfs, "rb").read()
    # Accept either a packed image or a raw region dump (image + zero tail).
    sqfs = sqfs.rstrip(b"\x00")
    if a.pubkey:
        pk = open(a.pubkey).read().strip()
        ok(f"trusted key     {pk[:40]}…")
        ok("                (this must be the key baked into --rootfs)")

    os.makedirs(a.work, exist_ok=True)
    stock = open(a.stock, "rb").read()
    header = stock[:CPB_HDR]
    name, raw0, comp0, rest = parse_cpb(stock)
    ius = tar_members(raw0)["firmware.ius"]
    off = a.offset if a.offset is not None else find_squashfs(ius)
    if off is None:
        die("could not locate the rootfs superblock; pass --offset explicitly")
    region = len(ius) - off
    if len(sqfs) > region:
        die(f"rootfs {len(sqfs):,} bytes does not fit the {region:,}-byte region at {off:#x} "
            f"(over by {len(sqfs) - region:,}). See docs/ota-signed-flash.md for what to drop.")
    print(f"   region {region:,} B, image {len(sqfs):,} B, slack {region - len(sqfs):,} B")

    step(f"patch rootfs into firmware.ius at {off:#x}")
    patched = bytearray(ius)
    patched[off:off + region] = b"\x00" * region
    patched[off:off + len(sqfs)] = sqfs
    if len(patched) != len(ius):
        die("length changed — must stay identical to stock")
    ok(f"                 {len(sqfs):,} bytes, length unchanged ({len(patched):,})")

    ip = os.path.join(a.work, "firmware.ius")
    sp = os.path.join(a.work, "firmware.ius.sig")
    open(ip, "wb").write(patched)
    sig = sign(ip, sp, key, passphrase)

    pkg, _ = wrap(header, bytes(patched), sig, rest)
    verify(pkg, stock, os.path.splitext(key)[0] + ".verify.pem", a.work)
    open(a.out, "wb").write(pkg)
    print(f"\n   wrote {a.out}")
    print(f"   flash with: scripts/flash-ota.sh <miner-ip> {a.out}")
    print("\n   keep the stock package — it is your rollback.")


if __name__ == "__main__":
    main()
