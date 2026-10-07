# Experiments: control surface, ASIC, and novel uses

Notes from poking the box with full root, answering three questions: how much of the
controller can we drive, how much of the ASICs can we drive, and what else can this
hardware do besides mine its original coin.

## Controller control surface

With root on the SoC, the board's peripherals are exposed through normal Linux
kernel interfaces, so they are fully scriptable:

- **Fans**: `/sys/class/fans/fan0..3`. Write `lvl` to set speed, read `rpm`. This is
  direct manual fan control with no reverse engineering. (Only two fans are physical;
  fan2/fan3 read zero.)
- **LEDs**: `/sys/class/leds/green` and `/sys/class/leds/red`, with `brightness`
  (0-255) and `trigger`. The status lights are ours to drive.
- **GPIO**: `/sys/class/gpio`, several pins already exported.
- **I2C**: four buses (`/dev/i2c-0..3`); the temperature sensor lives here.
- **SPI**: `spidev` nodes; the hashboard is on SPI.
- Plus RTC, power supply, a `switch` class, and the InfoTM config/env store
  (`/dev/items`, `/dev/env`).

Everything is built into the kernel (empty `lsmod`), and there is no working watchdog
device on the units tested, so nothing force reboots the box while you work.

## ASICs: topology and control

Reported live by the driver when work starts:

```
Goldshell-KDBox2 Miner detected, 1 chains totally!
C0: kdbox2 Init sucessed. 36 chips, 3240 Total goodcores.
C0: kdbox2 scan time is 16.00s@500.00MHz
```

- **1 chain, 36 blake2s chips, 3240 good cores** (90 cores per chip).
- The driver (`intchains_qomo`) exposes per-chip **frequency** (MHz) and **voltage**
  (mV) control via the miner's `--set-device` string, for example
  `intchains_qomo:vfff=65.000000:550:40:64`. You can watch it calibrate each chip's
  PLL across a frequency table at startup.
- Throughput is about **0.27 GH/s at 500 MHz** (the full 2^32 nonce space is scanned
  in ~16 seconds).

How direct is "control"? You drive the chips through the existing kernel driver and
the BFGMiner-derived userspace miner, by feeding work and reading back nonces. There
is no clean public API for hand-writing individual chip commands; that would mean
reverse engineering the proprietary SPI protocol behind the `xd248` driver, which is a
lot of effort for little gain when the work/nonce interface already gives you what you
need.

## What the chips actually compute

One operation only: **blake2s** over an ~80-byte mining header, sweeping the 32-bit
nonce, returning nonces whose digest is below a target. That is the entire instruction
set. It is not a CPU or GPU, it cannot hash arbitrary-length data, and it cannot run
any non-blake2s algorithm, because the function is fixed in silicon.

So any "novel use" has to be expressible as: *find a nonce N such that
blake2s(header-with-N) is below some target.*

## Feeding the chips work we control

Generic BFGMiner `--benchmark` mode does **not** work here: it hands the driver
malformed work, so every returned nonce fails validation (100% HW errors, 0 h/s). The
chips are hashing, but against work the host cannot verify.

The clean approach is a tiny **local stratum server**. The miner speaks stratum v1, so
a ~200-line server can hand the box any blake2s header and difficulty we like and
collect the nonces it finds, with no internet, no pool, and no coin. See
[rng/](rng/). This is the general control harness; the RNG below is one application of
it, and a vanity / proof-of-work finder is another (same server, higher difficulty).

## Novel use built so far: hardware RNG

Running the local stratum server at a low difficulty turns the box into a blake2s-backed
entropy faucet. Each nonce the hardware returns is an unpredictable draw (which core
hits first, and when, depends on the physical silicon and its timing). The server folds
every nonce into a SHA-256 pool and squeezes out random bytes and numbers.

Measured in a 28-second run:

- 7,963 hardware nonces, about 77 per second (scales with difficulty).
- ~249 KB of SHA-256-whitened random bytes.

Statistics on the whitened output (see [rng/sample-stats.txt](rng/sample-stats.txt)):

| Metric | Measured | Ideal |
|--------|----------|-------|
| Shannon entropy | 7.9993 bits/byte | 8.0 |
| Chi-square (255 df) | 257.6 | ~255 |
| Bit balance | 0.50014 | 0.5 |
| Lag-1 serial correlation | -0.0006 | 0 |
| Distinct byte values | 256/256 | 256 |

Honest caveat: those numbers are on the SHA-256-whitened output, so uniformity is
partly guaranteed by the hashing and does not by itself prove the raw source has high
min-entropy. The genuine hardware unpredictability is real but unquantified here. Treat
this as a fun, legitimate entropy source, not a certified TRNG.

## Honest limits

- Only blake2s. No other algorithm, ever, regardless of firmware.
- No arbitrary-length hashing; the input is the fixed ~80-byte header shape.
- Not general compute. It cannot be repointed at unrelated workloads.
- The useful envelope is exactly: blake2s nonce search. RNG, vanity/PoW finding, and a
  LAN "find me a nonce" service all fit; anything else does not.
