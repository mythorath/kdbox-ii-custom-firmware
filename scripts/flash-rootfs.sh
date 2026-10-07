#!/bin/sh
# flash-rootfs.sh - run ON THE BOX. Writes a rootfs image to /dev/spiblock1 and
# verifies the write by reading it back, BEFORE you reboot.
#
# Usage:  sh flash-rootfs.sh /path/to/modified.sqsh
# Get the image onto the box first (SD card, or wget from a PC on your LAN).
set -e
IMG="$1"
[ -f "$IMG" ] || { echo "image not found: $IMG"; exit 1; }
SZ=$(( $(wc -c < "$IMG") ))
PART=18874368
[ "$SZ" -le "$PART" ] || { echo "image larger than partition; refusing"; exit 1; }
WANT=$(md5sum "$IMG" | cut -d' ' -f1)
echo "image md5: $WANT  size: $SZ"

# stop daemons that could interfere or kill our session mid-write
killall -STOP minerd xminerd cepd eventhub 2>/dev/null || true
sync

echo "writing to /dev/spiblock1 ..."
dd if="$IMG" of=/dev/spiblock1 bs=65536
echo "syncing (this is the slow part, NOR program happens here) ..."
sync; sleep 1

# read back exactly the written region and compare
BLKS=$(( SZ / 512 )); REM=$(( SZ % 512 ))
if [ "$REM" -ne 0 ]; then
  # size not a multiple of 512: read full blocks + remainder
  GOT=$( (dd if=/dev/spiblock1 bs=512 count="$BLKS" 2>/dev/null; dd if=/dev/spiblock1 bs=1 skip=$(( BLKS*512 )) count="$REM" 2>/dev/null) | md5sum | cut -d' ' -f1)
else
  GOT=$(dd if=/dev/spiblock1 bs=512 count="$BLKS" 2>/dev/null | md5sum | cut -d' ' -f1)
fi
echo "readback md5: $GOT"
if [ "$GOT" = "$WANT" ]; then
  echo "VERIFY PASS - safe to reboot (use: reboot -f)"
else
  echo "VERIFY FAIL - do NOT reboot. Reflash your stock image and investigate."
  exit 2
fi
