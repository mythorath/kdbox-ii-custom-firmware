#!/bin/sh
# backup-flash.sh - run ON THE BOX (root shell over serial or temporary SSH).
# Dumps your flash so you can always get back to stock. Copy the results OFF the box.
#
# Usage: point OUT at a mounted SD card or other writable, roomy location.
#   OUT=/mnt/sd sh backup-flash.sh
OUT="${OUT:-/tmp}"
echo "Writing backups to $OUT"
# Whole raw chip (the ultimate restore image; cannot be sliced due to sector remapping).
dd if=/dev/mtd0      of="$OUT/kdbox_flash_full.bin" bs=65536
# Logical partitions (de-mapped by the driver), useful for targeted restore/analysis.
dd if=/dev/spiblock0 of="$OUT/boot.img"    bs=65536
dd if=/dev/spiblock1 of="$OUT/system.sqsh" bs=65536
dd if=/dev/spiblock2 of="$OUT/config.img"  bs=65536
dd if=/dev/spiblock3 of="$OUT/reserve.img" bs=65536
sync
echo "== checksums (keep these) =="
md5sum "$OUT"/kdbox_flash_full.bin "$OUT"/boot.img "$OUT"/system.sqsh "$OUT"/config.img "$OUT"/reserve.img
echo "Done. Copy $OUT off the box and store it safely."
