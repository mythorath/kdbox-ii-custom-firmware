# Custom firmware feasibility

Short version: a modified rootfs is feasible and proven. A no-serial installer is feasible in principle and is the main open task.

## The two update paths

The stock firmware can be updated two ways, and they have very different security:

1. **Online / over the air update**, driven by the management daemon. This path is cryptographically signed (an RSA signature verified against public keys on the device) and the payload is encrypted. You cannot push a modified image through it. This is a dead end for custom firmware, by design.

2. **Offline / SD card install**, driven by a separate upgrade tool and library. This path validates only a magic marker and a CRC32 over the payload. It does **not** link the crypto libraries and does **not** verify a signature. This is the opening.

In addition, the kernel mounts the root filesystem with no dm-verity and no root filesystem signature check, so a rootfs you write directly to the flash partition will boot.

## What is proven

Writing a modified rootfs directly to `/dev/spiblock1` from a root shell, then rebooting, works. The box boots the modified image. This is the method in [build-and-flash.md](build-and-flash.md). It requires serial (or a temporary SSH set up over serial) to get the first root shell.

## What is still open: removing the serial requirement

For a firmware "anyone can install," opening the case and attaching a serial bridge is too much to ask. The offline install path above is the route to a no-serial installer. The remaining work:

- Build a repacker that takes the stock offline image, swaps in a modified rootfs image, and fixes the CRC32 and any length fields so the upgrade tool accepts it.
- Pin down exactly which byte range the CRC32 covers.
- Pin down how the box is told to install from SD (a button held at power on, an auto detect of a specific file on the card, or a flag set in the config partition).

None of this redistributes vendor code. The installer would carry a patch or a rebuilt rootfs that the user generates from their own device, not a copy of Goldshell's image.

## Realistic envelope

The ASIC is a fixed function blake2s engine. The honest limits:

- Coins: another blake2s coin is in reach because the miner binary and chip driver are already present. Verge (XVG) is the obvious one and has been shown to hash on this hardware. Coins on other algorithms (blake2b, eaglesong, and so on) are not, because the silicon does not do those, regardless of firmware.
- General compute: no. This is not a CPU or GPU you can repoint at arbitrary workloads. It finds nonces whose blake2s hash meets a target. Anything you want it to do has to fit that shape.

Non mining experiments that do fit that shape are discussed in the project notes as they are explored.
