# Serial console and root access

## Wiring the bridge

You need something that can both read the console and drive the board's RX line hard to near 0 V. An ESP32 dev board works well. The sketch in [hardware/kdbox_uart_bridge](../hardware/kdbox_uart_bridge) turns an ESP32 into a transparent 115200 8N1 bridge between USB and the J2 header.

Wiring (ELEGOO ESP-WROOM-32 shown):

```
ESP32 GND            ->  KD-Box J2 GND   (square pad, connect first)
ESP32 GPIO16 (RX2)   <-  KD-Box TX
ESP32 GPIO17 (TX2)   ->  KD-Box RX
```

Leave the ESP32's own USB serial pins (GPIO1/GPIO3) alone. On the PC, open the ESP32's COM port at 115200 8N1 with no flow control.

If you only see output and cannot type, you are hitting the level shifter problem described in [hardware.md](hardware.md). Confirm with `hardware/tx_stream_test.py`, which streams zero bytes so you can watch the line sag on a meter. The ESP32 bridge is the fix.

## Getting a shell

The stock firmware runs a root shell directly on the serial console (a getty running /bin/sh, no login prompt). Press Enter and you should land at a `/ #` prompt as root. There is no password to get the serial shell.

## Taming console noise

Several daemons spam the console, which makes typed commands drop characters. Freeze the noisy ones while you work (they are respawned by init, so stop them, do not kill them):

```sh
for p in $(pidof minerd xminerd cepd eventhub); do kill -STOP $p; done
kill -STOP $(ps | awk '/[n]tpd/{print $1}')
```

Note that ntpd runs as a busybox applet, which is why it is matched by pattern rather than by `killall`. Resume everything with `kill -CONT` on the same processes, or just reboot.

If you intend to run the hash engine for more than a moment, do **not** freeze the fan controller or the miner supervisor, since they manage fan speed. Freeze only minerd, ntpd, cepd, and eventhub for a quiet shell.

## Optional: SSH over the network (temporary)

The stock image ships an OpenSSH server but the management daemon stops it a couple of seconds after boot. You can bring it back up for the current session from the serial shell. Because the root filesystem is a read only squashfs, you cannot run `passwd`; instead you set a known password in RAM with a bind mount and start sshd by hand. See `scripts/ssh-setup-ram.sh`.

Two gotchas worth knowing:

- The box runs OpenSSH 6.4, which predates ed25519. Use an RSA key, and connect with the legacy algorithm flags: `-o PubkeyAcceptedKeyTypes=+ssh-rsa -o HostKeyAlgorithms=+ssh-rsa`.
- Anything set up this way lives in RAM and is gone after a reboot. To make SSH permanent, bake it into the rootfs, which is exactly what the build in [build-and-flash.md](build-and-flash.md) does.

## Backing up your flash

Before you change anything, dump your flash. See `scripts/backup-flash.sh`. At minimum capture the whole raw chip (`/dev/mtd0`) and the rootfs partition (`/dev/spiblock1`). Copy them off the box and keep them safe.
