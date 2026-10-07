# Safety and recovery

## Rules that keep you un-bricked

1. **Take a full backup before touching anything.** Dump `/dev/mtd0` (the whole raw chip) and `/dev/spiblock1` (the rootfs), and copy them off the box. See `scripts/backup-flash.sh`.
2. **Never reboot until a write is verified.** The flash write is cached; the real program happens on `sync`. The flash script reads the written region back and compares md5 before telling you it is safe. Wait for that.
3. **Only write what you understand.** The rootfs partition (`spiblock1`) is the safe thing to modify. Leave the boot partition (`spiblock0`, which holds the bootloader and kernel) alone unless you have a way to recover it.

## Why the risk is bounded

The bootloader and kernel live on a separate partition that this project does not touch. The box will always get through early boot and attempt to mount the rootfs. So the common failure mode is "modified rootfs does not boot," not "dead board." You de risk that almost entirely by loop mounting your rebuilt squashfs on the PC and checking it before you flash, which the build script does.

## Recovery ladder

**If the box still reaches a shell** (serial or SSH): reflash the stock `system.sqsh` you backed up, exactly like any other image, and reboot. Back to stock.

**If a modified rootfs fails to mount** (kernel panic, no shell): the boot partition is intact, so the SoC and kernel still run. Recovery options, roughly in order of effort:

- SD card / offline install of a stock image, once the no-serial install trigger is pinned down (see [feasibility.md](feasibility.md)).
- InfoTM USB download mode. These SoCs have a ROM level USB recovery that can reflash the chip from a PC tool. This is the ultimate fallback and is why a truly dead board is unlikely, but it needs the vendor download tool and your full raw backup.

Keep your raw `/dev/mtd0` backup specifically for that last case.

## Thermals

If you run the hash engine, leave the fan controller running so it can manage temperature (it targets about 78 C). Do not freeze the fan controller or miner supervisor during a long run. The box is a real heater under load; run it somewhere that is fine with the heat and the noise, and keep an eye on temperature the first time.
