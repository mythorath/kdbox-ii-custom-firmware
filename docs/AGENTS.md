# AGENTS.md — guidance for AI agents working in this repository

You are reading a documentation-and-tooling repo about modifying **Goldshell KD-Box II**
miners. This file exists so an agent can act correctly without rediscovering the hardware,
and without doing something irreversible on a device someone owns.

Read this whole file before issuing commands against a miner. Read
[ota-signed-flash.md](ota-signed-flash.md) before building or flashing anything.

---

## 1. Scope and posture

- The device owner has physical possession of the miner and is asking for help with **their
  own hardware**. That is the entire mandate.
- Nothing here is about accessing a device you were not asked to touch. If the human has not
  named a specific miner IP and confirmed it is theirs, stop and ask.
- You are working with firmware. A wrong step can brick a box that then needs a serial
  console to recover. Prefer read-only inspection, then a reversible step, then the
  irreversible one — in that order, with the human's confirmation before the last.

## 2. What this repo is, and is not

| is | is not |
|---|---|
| procedures, scripts, and RE notes written by this project | Goldshell firmware, their binaries, or extracted images |
| tooling that operates on firmware **you already have** | a download mirror |
| documentation of a vendor design flaw, for owners | a weaponised exploit kit |

Two things are **deliberately absent** and must stay absent:

1. **The vendor OTA private key** (`fw_cmpt.pem`) — it ships inside every unit's rootfs.
2. **Its passphrase.** The key is extractable from any public official package; the passphrase
   is the only secret. Publishing it is equivalent to publishing a signing key that is valid
   for *every Goldshell model*, not just this one.

If a task appears to require printing either, stop and confirm with the human that they want
an irreversible, fleet-wide disclosure. Do not paste them into a file, a commit, a log, or
chat "for convenience".

## 3. Verified system facts

Treat these as ground truth for `MCB_V6_3_5` / firmware 2.2.7. They were established by
running the box, not by reading marketing material.

**Hardware**

| item | value |
|---|---|
| SoC | InfoTM iMAPx910, quad Cortex-A9, ARMv7 |
| kernel | `Linux 3.10.0-infotm`, Buildroot 2014, uClibc 0.9.33.2 |
| flash | 32 MB SPI NOR (`spiblock0` = SPL+kernel, `spiblock1` = rootfs, `spiblock2` = config) |
| ASIC | `ICA585` ×36, 18 chains of 2, `/dev/spidev1.0`, plugin id 114 |
| hash engine | **blake2s only** — see §7 |
| sshd | OpenSSH 6.4, RSA only, no ed25519, no modern KEX |
| web auth | AES-128-CBC, static key `!!!!!!!!!!!!!!!!`, zero IV, zero padding, hex |

**Update path**

- Endpoint: `POST /mcb/uploadimage`, multipart field `file`, `Authorization: Bearer <JWT>`.
- JWT from `GET /user/login?username=admin&password=<hex>&cipher=true` → `{"JWT Token": …}`.
  A wrong password returns **HTTP 500**, not 401.
- Filename must be `firmware-<mcbversion>.tgz`. The daemon renames whatever you send, so the
  *name* is cosmetic; the *contents* are not.
- Verification is **signature only**: `openssl dgst -sha256 -verify fw_cmpt.verify.pem
  -signature firmware.ius.sig firmware.ius`. No CRC, no table check.
- Typical flash: POST returns in ~7 s, box leaves the network ~2.5 min, back at **~3.5 min**.
- The flash **rewrites the config partition**: mining pools are wiped and the web admin
  password returns to `123456789`.

**Container (`.cpb`)**

```
+0x000  512-byte header "firmware-MCB_V6_3_5.tgz", NUL-padded
+0x200  gzip member 0 → tar{ firmware.ius (16,630,272), firmware.ius.sig (512) }, padded to 1024
+…      gzip member 1 → tar{ firmware.ius (44,570,112), firmware.ius.sig (512) } + trailer
```

- **Both members required.** Member 1 is the hashrate-board image — copy byte-identical.
- Member 1 starts on a 1024-byte boundary. Find it by **scanning for the next gzip magic**
  after member 0; the stock packer adds filler beyond the minimum padding, so arithmetic
  alignment is wrong.

**Inner image (`firmware.ius`)**

```
0x00  "+ius"   0x04 fmt=2   0x10 version "2.2.7"   0x1c count=6
0x30  16-byte entries (tag, index, 0x40000, size)
0x389E00  rootfs squashfs — patch in place, region 12,919,808 B to EOF
          stock image = 12,918,848 B → only ~960 B of slack
```

**Rootfs**

- squashfs 4.0, gzip, block 131072, no xattrs.
- stock image 12,918,848 of a 12,919,808-byte region → ~960 B of slack (unsquashfs'
  "filesystem size" of 12,917,584 is the logical size, not the space used).
- repack: `mksquashfs root out.sqfs -comp gzip -b 131072 -no-xattrs -noappend -all-root -nopad -Xcompression-level 9`.

## 4. Non-negotiable rules

1. **Never flash an image you have not verified** against the checklist in
   [ota-signed-flash.md](ota-signed-flash.md) §4. If the build script reports a failed check,
   stop; do not "fix it after".
2. **Never flash a package built for a different `mcbversion`.** Renaming does nothing; the
   inner image and member 1 are version-bound. Ask for the unit's stock package instead.
3. **Never assume offsets across versions.** `0x389E00` is a verified fact for `MCB_V6_3_5`
   only. `build-cpb.py` locates the superblock by validation instead of trusting the
   constant, but never assume it for a new `mcbversion`.
4. **Keep the stock package** on disk before flashing. It is the only rollback that does not
   require a serial cable.
5. **Do not open the case, solder, or ask for serial wiring** unless the human explicitly
   wants the serial route. The whole point of the OTA path is avoiding it.
6. **Do not write secrets to disk**: no key material, no passphrase, no tokens in files,
   commits, or logs.
7. **Do not claim success from a log line.** Success is: box answers `/mcb/status`, SSH
   returns `uid=0(root)`, and the marker file exists. See §6.

## 5. Which path to use

```
Do you have a root shell on the box already?
├─ yes → either path. dd/rootfs-swap (build-and-flash.md) is fine and needs no signing.
└─ no  → OTA signed flash (ota-signed-flash.md). Needs:
          • the stock .cpb for this MCB version
          • the vendor signing key + passphrase   ← if absent, STOP and report
          • your SSH public key
```

If the signing key or passphrase is unavailable, the honest options are a prebuilt signed
image from a trusted party, a per-person build signed by whoever holds the key, or the serial
route. Say that plainly rather than improvising a workaround.

## 6. Verification gates

Run these in order and quote the actual output when reporting.

```sh
# 1. did it come back, and on what firmware?
curl -s http://<ip>/mcb/status
#   want: mcbversion MCB_V6_3_5, firmware 2.2.7

# 2. is it root, and is it our image?
ssh -i <key> -o PubkeyAcceptedKeyTypes=+ssh-rsa -o HostKeyAlgorithms=+ssh-rsa \
    root@<ip> 'id; cat /etc/kdbox-custom-fw'
#   want: uid=0(root) … and the marker line

# 3. does it survive a reboot?
ssh … 'sync; reboot -f'  → wait for /mcb/status 200 → repeat step 2
#   want: same output; this is the difference between "works now" and "works"
```

Local build checks (`build-cpb.py` enforces them): same length as stock, all differing bytes
inside the rootfs region, signature verifies against the vendor public key, member 1 +
trailer byte-identical, member 1 starts 1024-aligned, packaged squashfs lists the
authorized_keys and marker.

## 7. Failure signatures → diagnosis

| symptom | meaning | action |
|---|---|---|
| log shows `Minerd start !!!`, box stays on old firmware | package malformed — almost always a **single-member** `.cpb` | rebuild with stock member 1 + trailer byte-identical |
| POST returns 200, nothing happens, box stays up | updater rejected the package without writing | check header name, member alignment, signature |
| `openssl … verify` says `Verification failure` | wrong key, wrong passphrase, or signed after patching | sign the **patched** `.ius`, verify before wrapping |
| box never returns after flash | rootfs did not mount | serial console (J2) — do not retry uploads blindly |
| SSH `no matching host key type` / `connection refused` | legacy OpenSSH 6.4 | add `-o PubkeyAcceptedKeyTypes=+ssh-rsa -o HostKeyAlgorithms=+ssh-rsa` |
| miner reports ~0 h/s with `Auto addressing failed` | wrong algorithm for this silicon | see §8 — this chip is blake2s only |

## 8. What this hardware cannot do

`ICA585` (KD-Box II) is a fixed-function **blake2s** engine. Verified by attempting it on
hardware:

| attempt | result |
|---|---|
| `blake2s` (KDA) via `kdaminer` | works, ~3.4 TH/s |
| `blake2b(SC)` via `intminer` (SCBox II binary) | `SCBOX2 device init… Set TSENSOR_MODE Failed` → `Auto addressing failed` ×5 → exits |
| `blake2b` via `xvgminer` | parses, then `unexpected echo for cmd 0x0200` → `Auto addressing failed` |
| `blake2s(XVG)` via `xvgminer` | clock walk-down `30→20→10→0 MHz`, 0 h/s even with work available |

Blake2b lives on different parts: `ICT580` (SCBox II) and `ICA586` (original KD Box, KD5,
KD5 Pro). Do not promise a blake2b conversion on a KD-Box II, with or without root.

One open discrepancy: the top-level README lists a proven XVG (blake2s) conversion from
earlier work in this project, while the runs above — on fw 2.2.7 / ICA585 — stalled before
the chips produced hashrate. Both can be true (different firmware generation, different
miner build). If you reproduce XVG mining successfully, record the firmware version, the
`mcbversion`, the exact miner command line and a hashrate sample in
`experiments/`, and reconcile the README.

## 9. Escalate to the human before

- flashing anything, or re-flashing a box that is currently mining;
- publishing the signing key or passphrase anywhere;
- contacting the vendor or filing a disclosure;
- deleting or overwriting a stock package or a flash backup;
- anything that requires opening the case.

## 10. Glossary

| term | meaning |
|---|---|
| `.cpb` | the package the web UI accepts; 512-byte header + two gzip members |
| `firmware.ius` | inner signed image; carries the rootfs |
| `fw_cmpt.pem` / `.verify.pem` | vendor OTA key pair; private half ships in the rootfs |
| `spiblock0/1/2` | kernel+SPL / rootfs / config partitions |
| `minerd` | management daemon: web UI, auth, OTA verify, spawns `xminerd` |
| `xminerd` | supervisor that launches the miner binary for the active algorithm plan |
| `Minerd start !!!` | log line meaning `minerd` crashed and respawned — malformed package |
