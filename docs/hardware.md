# Hardware

## Board overview

The KD-Box II is a small single hashboard miner with a controller SoC and one blake2s ASIC subsystem, in a metal case with two fans.

| Part | Detail |
|------|--------|
| SoC | InfoTM iMAPx910, quad core ARM Cortex-A9, ARMv7 |
| RAM | ~256 MB usable (seen as 247 MB total in Linux) |
| Flash | Winbond W25Q256JW, 32 MB SPI NOR |
| Hash engine | InfoTM "intchains_qomo" blake2s ASIC |
| Network | 100 Mbit Ethernet, plus a wifi helper process |
| Console | 3.3 V level serial on the J2 header, 115200 8N1 |

## Serial console header (J2)

Three lines matter: GND, the board's TX (console output), and the board's RX (console input). The square pad on the header is GND.

Important: the console lines sit behind a passive MOSFET level shifter with roughly 1.5 k pull ups to 3.3 V, while the SoC side runs at 1.8 V. At idle TX sits near 3.3 V. On power up TX dips toward 1.5 V then settles.

Consequence: a normal USB-serial adapter can **read** the console fine, but its output stage usually cannot pull the shifted RX line low enough to register, so typed characters never reach the SoC. You can see the boot log but you cannot type. The fix is to drive RX with a push-pull GPIO that pulls hard to near 0 V. An ESP32 GPIO does this; a cheap CP2102/CH340 dongle generally does not. See [hardware/kdbox_uart_bridge](../hardware/kdbox_uart_bridge).

## Flash layout

The raw 32 MB chip is **not** laid out linearly. InfoTM uses a sector remapping layer ("spi_sect_map") that scatters the partitions across physical flash, with map tables at logical offsets. Because of that, a raw dump of the whole chip is a valid restore image but cannot be carved up directly.

For analysis and for flashing, use the logical partition block devices that the driver presents already de-mapped:

| Device | Contents | Size |
|--------|----------|------|
| /dev/mtd0 | whole raw chip (32 MB) | backup only |
| /dev/spiblock0 | boot (SPL, kernel) | 8320 KB |
| /dev/spiblock1 | rootfs (squashfs) | 18432 KB |
| /dev/spiblock2 | config (vfat, writable, mounted at /mnt/config) | 3072 KB |
| /dev/spiblock3 | reserve | 2245 KB |

The partition that matters for custom firmware is **/dev/spiblock1**, the rootfs.

## Boot and kernel notes

- Kernel is Linux 3.10.0-infotm, built from a Buildroot 2014 tree.
- The kernel command line mounts the rootfs read-write from the squashfs partition, with no dm-verity or signature check on the root filesystem. That is what makes a modified rootfs bootable.
- There is a watchdog init script, but on the units tested the watchdog kernel module failed to load at boot, so nothing force reboots the box while you work. Do not rely on that being true on every unit.

## Fans and thermals

Two fans, managed by a userspace fan controller that targets roughly 78 C. At idle with no hashing the fans sit low (around 20 percent) and the board stays near room temperature. If you run the hash engine, let the fan controller keep running so it can manage temperature.
