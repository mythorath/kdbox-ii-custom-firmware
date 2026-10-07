# KD-Box II Custom Firmware Project

Reverse engineering and custom firmware for the **Goldshell KD-Box II** ASIC miner, so a box whose original coin is dead can be put back to use.

The KD-Box II was built to mine Kadena (KDA, blake2s). When that stopped being worthwhile the stock firmware left the hardware locked to a coin nobody wants, which turns a capable little blake2s machine into an expensive space heater. This project documents how to get root on your own box, how its firmware is laid out, and how to build and flash a modified rootfs, all without needing a vendor account or a signed update.

The chip in this box is a fixed function blake2s engine. That means the realistic repurposing target is another blake2s coin (Verge / XVG is the obvious one, same algorithm), plus some non mining experiments described later. It is not a general purpose compute board.

## Status

What works today, verified on real hardware:

- Full serial console and root shell over the J2 header (needs a small driver circuit, see below).
- Full flash backup of your own device.
- Complete map of the firmware: partitions, the squashfs rootfs, the init flow, and the InfoTM sector remapping.
- A reproducible modify -> rebuild -> flash pipeline for the rootfs, validated end to end: a modified image was built, written to the flash chip, and the box rebooted cleanly on it.
- Permanent root SSH baked into a custom rootfs that survives power cycles.
- Proof the hardware can mine a different blake2s coin (XVG) with the miner binaries already present on the device.

What is still in progress:

- A no-serial installer (an SD card or offline update image) so people who do not want to open the case and solder can install a custom build.
- Permanent, auto starting coin conversion as a clean packaged build.
- Exploring how much direct control of the ASICs is possible and whether they are useful for anything besides mining.

See [docs/](docs/) for the detail behind each of these.

## What is in here

This repo contains **our own tools, scripts, and documentation only**. It does **not** contain any Goldshell firmware, their miner binaries, or any extracted image. Those are Goldshell's copyrighted code and are not ours to redistribute. Everything here operates on the firmware that already lives on **your** device.

```
docs/        How the hardware and firmware work, and the step by step procedures
hardware/    The serial bridge (ESP32 sketch) and a signal test script
scripts/     Backup, build, and flash scripts (run some on a PC, some on the box)
helpers/     Convenience wrappers for talking to the box from a Windows PC
```

## Hardware summary

- SoC: InfoTM iMAPx910, quad core ARM Cortex-A9 (ARMv7).
- Flash: Winbond W25Q256JW, 32 MB SPI NOR.
- OS: Linux 3.10.0-infotm, Buildroot 2014. Root shell on the serial console, no login.
- Hash engine: InfoTM "intchains_qomo" blake2s ASIC, driven by a kernel module plus a BFGMiner derived userspace miner.

Full detail in [docs/hardware.md](docs/hardware.md).

## Quick start (high level)

1. **Back up first.** Open serial, get a root shell, and dump your flash. If anything ever goes wrong, this is what saves you. See [docs/serial-and-root.md](docs/serial-and-root.md) and `scripts/backup-flash.sh`.
2. **Extract and modify the rootfs** on a PC. See [docs/build-and-flash.md](docs/build-and-flash.md) and `scripts/build-rootfs.sh`.
3. **Flash it back** and verify the write before you reboot. See `scripts/flash-rootfs.sh`.

Do not skip step 1.

## Safety, warranty, and legal

- This modifies your own device. It will void any warranty and it can brick the box if you are careless. You accept that risk.
- Always keep a full flash backup. The flash write scripts verify the write by reading it back before you are told it is safe to reboot.
- This project does not redistribute Goldshell firmware or binaries. You work only on the image already on your hardware.
- Repurposing hardware you own is yours to do. Mining any coin, and any power or tax implications of doing so, are your responsibility.
- No affiliation with Goldshell or InfoTM.

## Why serial is needed (for now)

The stock firmware's online update path is cryptographically signed, so you cannot push a modified image that way. The route this project uses is to get a root shell over the serial console and write the new rootfs directly to the flash partition. That is reliable and fully under your control, but it does require the small driver circuit in [hardware/](hardware/), because the console lines sit behind a level shifter that a plain USB-serial adapter cannot drive. Removing the serial requirement is the main open task. See [docs/feasibility.md](docs/feasibility.md).

## Contributing

Issues and pull requests welcome, especially from anyone with the same hardware who can confirm findings or help with the no-serial installer. Please do not attach any Goldshell firmware images or binaries to issues or PRs.
