# Firmware structure

## Root filesystem

The rootfs on `/dev/spiblock1` is a SquashFS 4.0 image with these parameters:

- Compression: gzip
- Block size: 131072 (128 KB)
- Exportable (NFS) flag set
- No xattrs

Matching these exactly when you rebuild is important: the 3.10 kernel's squashfs driver reads a standard gzip 4.0 image fine, but you want the rebuilt image to be a clean match for the stock one. The build script in `scripts/` uses these parameters.

The rootfs mounts as the running system. It is read only at runtime, so persistent changes have to be baked into the image and flashed.

## Init flow (how things start)

BusyBox init, driven by `/etc/inittab`:

1. sysinit mounts /proc, /dev/pts, /dev/shm, runs `/etc/init.d/rcS`.
2. `rcS` runs the `S??*` scripts in order. Relevant ones:
   - `S38initdir` mounts the writable config partition at /mnt/config.
   - `S40network` brings up lo and eth0.
   - `S50sshd` starts the SSH server (host keys are already present in /etc).
3. inittab then respawns these on the console tty: a getty running /bin/sh (the root shell), the wifi helper, the fan controller, the miner supervisor (`xminerd`), and the management daemon (`minerd`).

Key behavior: a couple of seconds into boot, `minerd` calls `/etc/init.d/S50sshd stop`, which does `killall sshd`. That is why SSH is up briefly and then gone on a stock box. It calls that script path specifically; it does not kill sshd by any other route. Neutralizing the `stop()` in that one script is enough to keep SSH alive permanently.

## The mining launch path

- `minerd` is the management daemon. It reads the hashboard's barcode to decide which coin the box is for, and launches the matching per coin miner.
- `xminerd` is the miner supervisor. It launches the actual miner as `/usr/bin/bfgminer` (a symlink to the per coin binary) inside a screen session, using a JSON config.
- The per coin miner is a BFGMiner derivative. Both a KDA miner and an XVG miner ship on the stock image. They share the same blake2s chip driver; they differ in the pool/stratum handling for each coin.
- Pools are configured under the writable config partition. With no pools set, the box reports "Stay Idle" and the chip is left free.
- Chip tuning is passed to the miner as a device string of the form `intchains_qomo:<voltage/limit>:<freq>:<a>:<b>`. A conservative, known stable profile on this board uses a 550 MHz frequency setting.

## InfoTM sector remapping

The raw flash is scrambled by a sector remapping layer, with map tables at logical offsets inside the chip. This is why:

- A raw `/dev/mtd0` dump is a valid whole chip restore image, but you cannot slice partitions out of it by offset.
- You should read and write the **logical** `/dev/spiblockN` devices, which the driver presents already de-mapped, for anything partition specific.

## Offline update container (for the no-serial goal)

The stock offline/SD update file is a container (the vendor uses a `.cpb` wrapper around an inner `.ius` image). The inner image begins with an ASCII magic marker and carries a simple CRC32 over the payload, an image count, and an image table. The rootfs is one of the images in that table. Notably, the offline install tool validates only the magic and the CRC32; it does not do a cryptographic signature check (that check exists only on the online update path). That asymmetry is what makes a no-serial installer feasible. Turning that into a working, distributable installer is tracked in [feasibility.md](feasibility.md) and is still open.
