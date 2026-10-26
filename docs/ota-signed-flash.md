# No-serial install: signed OTA flash

This is the path for a **stock, sealed KD-Box II** — no serial header, no case opening, no
`dd`, no soldering. It works because the box's own firmware update path accepts any package
whose signature verifies, and the key it verifies against ships inside the box.

Two ways to use this document:

- **You have a root shell already** (serial, or a previous build) → read on, you can do the
  whole thing.
- **You only have the web UI** → read it anyway. Everything up to and including flashing is
  done from the web UI; the only part that needs a PC is *building* the image.

> **Read [safety-and-recovery.md](safety-and-recovery.md) first.** The irreversible step is
> the flash itself. A bad rootfs leaves a box that needs serial to recover, and serial is
> exactly what this procedure is trying to avoid.

---

## Why this works

The management daemon (`minerd`) verifies update packages like this:

```c
sprintf(cmd, "openssl dgst -sha256 -verify %sfw_cmpt.verify.pem -signature %s.sig %s",
        "/mnt/config/minerd/settings/", ius_path, ius_path);
system(cmd);
```

- **Signature only.** No CRC, no length check, no table validation in that path.
- `fw_cmpt.verify.pem` is the public half of the vendor's OTA key.
- The **private** half (`fw_cmpt.pem`) ships inside the rootfs at `/root/settings/`.

So a package you build and sign with that key is accepted exactly like an official one.

### Where the signing key comes from

This repository does **not** ship the private key or its passphrase. You supply them, from
your own hardware or your own copy of an official package:

1. Take the official `firmware-<model>-<ver>.cpb` for your model (Goldshell publishes these).
2. Unpack the rootfs as described in [firmware-structure.md](firmware-structure.md).
3. `/root/settings/fw_cmpt.pem` is a 4096-bit RSA private key, AES-encrypted PEM.

You still need its passphrase to use it. That passphrase is a single vendor-chosen string,
the same on every unit, and it is deliberately **not** reproduced here: publishing it,
together with a key that is extractable from any public package, is equivalent to publishing
the signing key for **every Goldshell model**, not just this one. Treat it as a disclosure
decision, not a build step.

If you cannot obtain the passphrase, the alternatives are:

- use a prebuilt signed image from someone who has one and trusts you with their SSH key, or
- ask that person to sign a build that carries **your** public key, or
- use the serial route (see [serial-and-root.md](serial-and-root.md)), which needs no signing.

---

## What you need

| item | why |
|---|---|
| Linux host (or WSL) | `squashfs-tools`, `openssl`, `python3` |
| the stock `.cpb` for **your** MCB version | source of the container, firmware and the second member |
| the vendor signing key + passphrase | see above |
| your SSH public key | becomes the only key the image trusts |
| a browser or `curl` on the same LAN | to upload the package |

Check the version first:

```sh
curl -s http://<miner-ip>/mcb/status
# {"hardware":"B2.CS.SA","model":"Goldshell-KDBoxⅡ","mcbversion":"MCB_V6_3_5","firmware":"2.2.7"}
```

**`mcbversion` decides everything.** `MCB_V6_3_5` is what the reference build was made for.
A different value means a different internal image and a different rootfs offset — rebuild
from *that unit's* stock package. Do not rename ours.

---

## The container, so you know what you are editing

```
+0x000  512-byte header: "firmware-MCB_V6_3_5.tgz" NUL-padded
+0x200  gzip member 0 → tar{ firmware.ius (16,630,272), firmware.ius.sig (512) }
        …padded to the next 1024-byte boundary (filler is high-entropy, not zeros)
+…      gzip member 1 → tar{ firmware.ius (44,570,112), firmware.ius.sig (512) }
+…      trailer, file padded to 1024
```

Rules that bite:

- **Both members are required.** Ship only member 0 and `minerd` crashes and respawns
  instead of updating — the log shows `Minerd start !!!` and the box stays on the old image.
- Member 1 is the hashrate-board image. Copy it **byte-identical**, trailer included.
- Member 1 is located by scanning for the next gzip magic after member 0, *not* by
  arithmetic: the stock packer inserts filler beyond the minimum alignment.
- After decompression, member 0's tar must be exactly 16,640,000 bytes for 2.2.7.

Inside `firmware.ius`:

```
0x00      "+ius"
0x04      format version (2)
0x10      version string ("2.2.7")
0x1c      image count (6 for MCB_V6_3_5)
0x30      16-byte entries (tag, index, 0x40000, size)
0x389E00  rootfs squashfs   ← patch here, in place
          region 12,919,808 bytes to EOF. The stock image occupies 12,918,848 of
          them, so you have ~960 bytes of slack, not kilobytes.
```

---

## Procedure

`scripts/build-cpb.py` and `scripts/flash-ota.sh` implement the steps below. Read them
before running them — they are short and they check everything they claim to check.

### 1. Unpack

```sh
python3 scripts/build-cpb.py --inspect firmware-MCB_V6_3_5-stock.cpb
```

It prints the header name, member sizes, `.ius` version, image count, rootfs region and the
squashfs magic. If that does not look right, stop.

### 2. Modify the rootfs

`unsquashfs`, then apply the minimum set (the same set `scripts/mods/` applies for the serial
route):

| change | why |
|---|---|
| `root/.ssh/authorized_keys` ← **your** public key (700/600) | key-based root login |
| `etc/init.d/S50sshd`: replace the body of `stop()` with an echo | `minerd` runs `S50sshd stop` at boot, which is `killall sshd`. This one call *is* the "SSH disabled" mechanism. |
| `etc/sshd_config`: append `PermitRootLogin yes`, `PasswordAuthentication no`, `UseDNS no` | root login allowed, keys only; `UseDNS no` avoids a 10 s stall |
| `etc/kdbox-custom-fw` marker | tells you from a shell which image booted |

**Fit matters.** The stock image occupies 12,918,848 of the 12,919,808-byte region — about
**960 bytes** of slack, and `mksquashfs` output is not byte-stable, so practically any edit
overflows. (`unsquashfs -s` reports a logical filesystem size of 12,917,584; the difference
is block alignment. Trust the region, not that number.) The
reference build drops `root/yottamc/fonts/materialdesignicons-webfont.64d4cf64.eot`
(~1 MB, IE-only format; the woff2/ttf siblings stay) which frees ~470 KB.
Never drop anything `minerd`, `xminerd` or `kdaminer` links against.

Repack with the stock parameters:

```sh
mksquashfs root rootfs.sqfs \
    -comp gzip -b 131072 -no-xattrs -noappend -all-root -nopad -Xcompression-level 9
```

- `-all-root` is mandatory: without it the image is owned by your host uid and daemons
  cannot read their own config.
- `-nopad` keeps the tail from blowing the region.
- Assert the result fits the region (12,919,808 bytes) — and see the note above about why
  you actually need to be at or near the stock size.

### 3. Patch, sign, wrap

```sh
export KD_FW_SIGNING_KEY=/path/to/fw_cmpt.pem
export KD_FW_PASS='…'                       # the vendor passphrase, see above

python3 scripts/build-cpb.py \
    --stock firmware-MCB_V6_3_5-stock.cpb \
    --rootfs rootfs.sqfs \
    --pubkey keys/id_ed25519.pub \
    --out kdbox2-custom-<name>.cpb
```

It will:

1. zero the rootfs region and drop your image at `0x389E00`, leaving length and the image
   table untouched;
2. sign `firmware.ius` with the vendor key and **verify the signature** against the public
   half before continuing;
3. rebuild the `.cpb` with the stock header, your member 0, and the stock member 1 + trailer;
4. run the full verification checklist (see below) and refuse to write the output if any
   check fails.

### 4. Verify before flashing

The script enforces all of this; check it reported success, not just that it exited:

1. header byte-identical to stock;
2. member 0 decompresses to exactly 16,640,000 bytes;
3. that tar contains `firmware.ius` (16,630,272) and `firmware.ius.sig` (512);
4. `firmware.ius` is the same length as stock and **every differing byte** is inside
   `[0x389E00, +12,919,808)`;
5. signature verifies against the vendor public key;
6. the squashfs inside the packaged `.ius` mounts and lists `root/.ssh/authorized_keys` and
   `etc/kdbox-custom-fw`;
7. member 1 + trailer byte-identical to stock;
8. member 1 starts on a 1024-byte boundary.

### 5. Flash from the web UI

```
http://<miner-ip>/  →  System  →  UNLOCK (admin password)  →  Update
                    →  choose the .cpb  →  UPDATE
```

- Default admin password is `123456789` unless it was changed.
- The file field accepts `.tgz` and `.cpb`.
- **There is no confirmation dialog.** UPDATE starts the upload immediately.
- The UI shows `Uploading firmware to miner…`, `Firmware is being verified by miner…`,
  then `Miner is in updating progress…`.
- Expect the tab to stop responding, then the box to disappear for ~2.5 minutes. Total
  **~3.5 minutes** from the click.
- `Update process terminated. Please choose the officially issued update package.` is what a
  *successful* flash looks like from the page's point of view — the socket dies because the
  daemon kills userspace. Do **not** re-upload. Wait, reload, and check the firmware version.

Scripted equivalent: `scripts/flash-ota.sh <miner-ip> <package.cpb>`.

### 6. After it comes back

```sh
ssh -i ~/.ssh/id_ed25519 \
    -o PubkeyAcceptedKeyTypes=+ssh-rsa -o HostKeyAlgorithms=+ssh-rsa \
    root@<miner-ip> 'id; cat /etc/kdbox-custom-fw'
```

The legacy options are **mandatory**: the box runs OpenSSH 6.4, RSA only, no ed25519
signatures and no modern KEX. Expect `uid=0(root)` and the marker line.

The flash rewrites the config partition, so **pools are gone** and the web admin password is
back to `123456789`. Re-add your pool, change the password, and keep the box off the open
internet — `/mcb/wifisetting` hands out the WiFi PSK with no authentication at all.

---

## Rolling back

Re-flash the stock `.cpb` through the same updater. Keep it on disk before you start; it is
your only undo that does not involve a serial cable.

Flashing replaces **the rootfs only** (`spiblock1`). SPL and kernel (`spiblock0`) are never
written by this path, so a bad rootfs still boots far enough to accept an upload in most
cases. If it does not come back on the network, recovery needs the J2 console —
see [serial-and-root.md](serial-and-root.md).

---

## Gotchas

- **Single-member package** → `minerd` crash/respawn (`Minerd start !!!`), no update, box
  stays on the old image. Harmless, but wasted time.
- **`mksquashfs` without `-all-root`** → image owned by your uid; daemons cannot read config.
- **`mksquashfs` without `-nopad`** → image larger than the region.
- **Member not 1024-aligned** → the package scan never finds it and the update silently
  does not run.
- **Wrong `mcbversion`** → the only reliable way to need a serial cable. Rebuild, do not
  rename.
- **A wrong password returns HTTP 500**, not 401. That is the login API rejecting you, not a
  broken server.
- **The GUI remembers your last file.** Open the chooser, pick deliberately, then confirm the
  name *and size* in the field before clicking UPDATE.

---

## What this does not buy you

Root does not change the hash engine. The KD-Box II's `ICA585` chips implement blake2s and
nothing else — see [hardware.md](hardware.md). Blake2b (Sia/Handshake) needs different
silicon (`ICT580` / `ICA586`), and this image does not change that.
