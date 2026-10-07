# Build and flash a modified rootfs

This is the core procedure, verified end to end on real hardware. You work on your own extracted rootfs. Nothing here ships Goldshell code.

You need:
- A Linux PC (or WSL) with `squashfs-tools` (mksquashfs / unsquashfs 4.x).
- Serial or temporary SSH access to the box (see [serial-and-root.md](serial-and-root.md)).
- A full flash backup already taken.

## 1. Get your rootfs onto the PC

On the box, copy the rootfs partition somewhere you can transfer it from (an SD card, or pull it over the network), then move it to your PC. For example, on the box:

```sh
dd if=/dev/spiblock1 of=/tmp/system.sqsh bs=65536
md5sum /dev/spiblock1 /tmp/system.sqsh   # the two should match
```

Transfer `system.sqsh` to the PC. The partition is 18432 KB; the squashfs inside it is smaller and self sizing, so the file is the full partition and the trailing bytes are unused.

## 2. Unpack, modify, repack

`scripts/build-rootfs.sh` automates this. It:

1. `unsquashfs` your `system.sqsh` into a working tree.
2. Applies the modifications in `scripts/mods/` (see below).
3. Repacks with the stock matching parameters:
   ```
   mksquashfs root modified.sqsh -comp gzip -b 131072 -no-xattrs -noappend
   ```
4. Loop mounts the result read only and checks the tree against the source so you know the repack is clean.

Confirm the result fits: it must be no larger than 18874368 bytes (the partition). A lightly modified image is around 13 MB, well under that.

### The permanent SSH modification (reference build)

The reference build makes SSH permanent and nothing else, to prove the pipeline with minimum risk. The changes, all baked into the squashfs:

- Add `/root/.ssh/authorized_keys` (mode 600, dir mode 700) containing **your own** public key. Do not reuse anyone else's.
- Set a known root password hash in `/etc/shadow` if you want password login as a fallback. The box's crypt supports classic DES hashes.
- Neutralize `stop()` in `/etc/init.d/S50sshd` so the management daemon can no longer kill sshd. sshd is already started at boot by that script and the host keys are already in /etc, so this one change makes SSH persist.
- Drop a marker file like `/etc/kdbox-custom-fw` so you can tell at a glance that a box booted your image.

Keep everything else identical to stock. The build script verifies that every binary in the repacked image is byte identical to the source.

## 3. Flash it back and verify

`scripts/flash-rootfs.sh` runs on the box. Get your `modified.sqsh` onto the box first (SD card, or `wget` from a PC web server on your LAN). Then the script:

1. Confirms the transferred file's md5 matches what you built (gate 1).
2. Freezes the management daemon and miner supervisor so nothing interferes or kills your session mid write.
3. `dd if=modified.sqsh of=/dev/spiblock1 bs=65536`, then `sync`.
4. Reads the written region back and md5s it against your image (gate 2).

Two things that will bite you if you do not know them:

- `dd` returns almost instantly because it only fills the block cache. The real, slow NOR program happens during `sync`, which can take 30 to 60 seconds. **Wait for the script to report the verify result before you reboot.**
- The whole partition md5 will not equal your image md5, because the partition is larger than the image (image plus unused tail). The script verifies only the written region, which is the correct comparison.

## 4. Reboot

Reboot the box. `reboot -f` is the safest choice here because it cannot hang in a shutdown script, and this board has no reliable watchdog to recover a hang. Everything is already on flash and synced at this point.

Watch the boot on serial. A good boot looks completely normal. Then confirm your change, for example SSH in with your key on the fresh boot and check the marker file.

## Recovery

If a build ever fails to boot, see [safety-and-recovery.md](safety-and-recovery.md). The short version: as long as the box still reaches a shell, you reflash the stock `system.sqsh` the exact same way. Keep that backup.
