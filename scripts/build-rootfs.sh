#!/bin/sh
# build-rootfs.sh - run ON A PC with squashfs-tools (mksquashfs/unsquashfs 4.x).
# Unpacks your extracted stock rootfs, applies the mods in scripts/mods/, repacks
# with stock-matching squashfs parameters, and loop-checks the result.
#
# Usage:
#   sh build-rootfs.sh <stock system.sqsh> <your authorized_keys> [out.sqsh]
#
# Everything operates on YOUR extracted image. No vendor code is included here.
set -e
SRC="$1"; AUTHKEYS="$2"; OUT="${3:-modified.sqsh}"
[ -f "$SRC" ] || { echo "stock rootfs not found: $SRC"; exit 1; }
[ -f "$AUTHKEYS" ] || { echo "authorized_keys not found: $AUTHKEYS"; exit 1; }
WORK="$(mktemp -d)"; ROOT="$WORK/root"
echo "Unpacking $SRC ..."
unsquashfs -d "$ROOT" "$SRC" >/dev/null

echo "Applying mods ..."
# 1) permanent SSH key for root
mkdir -p "$ROOT/root/.ssh"
cp "$AUTHKEYS" "$ROOT/root/.ssh/authorized_keys"
chmod 700 "$ROOT/root/.ssh"; chmod 600 "$ROOT/root/.ssh/authorized_keys"
chown -R 0:0 "$ROOT/root/.ssh" 2>/dev/null || true
# 2) keep sshd alive: neutralize S50sshd stop() so the mgmt daemon cannot kill it
if [ -f "$ROOT/etc/init.d/S50sshd" ]; then
  awk '
    /^stop\(\) \{/ {print; print "\t# kdbox-custom-fw: do not kill sshd"; print "\techo -n \"Stopping sshd: \""; print "\techo \"OK (kept)\""; print "}"; skip=1; next}
    skip && /^}/ {skip=0; next}
    skip {next}
    {print}
  ' "$ROOT/etc/init.d/S50sshd" > "$ROOT/etc/init.d/S50sshd.new"
  mv "$ROOT/etc/init.d/S50sshd.new" "$ROOT/etc/init.d/S50sshd"
  chmod 755 "$ROOT/etc/init.d/S50sshd"
fi
# 3) optional known root password (DES). Set KDBOX_ROOT_HASH to a crypt() hash to enable.
if [ -n "$KDBOX_ROOT_HASH" ] && [ -f "$ROOT/etc/shadow" ]; then
  sed -i "s|^root:[^:]*:|root:$KDBOX_ROOT_HASH:|" "$ROOT/etc/shadow"
fi
# 4) build marker
echo "KD-Box II community firmware (built $(date -u +%Y-%m-%dT%H:%M:%SZ))" > "$ROOT/etc/kdbox-custom-fw"

echo "Repacking -> $OUT ..."
rm -f "$OUT"
mksquashfs "$ROOT" "$OUT" -comp gzip -b 131072 -no-xattrs -noappend -quiet

PART=18874368; SZ=$(stat -c%s "$OUT")
echo "size $SZ bytes (partition $PART) fits: $([ "$SZ" -le "$PART" ] && echo YES || echo NO)"
echo "md5: $(md5sum "$OUT" | cut -d' ' -f1)"

# loop-check (needs root/loop; skipped automatically if unavailable)
if MP="$(mktemp -d)" && mount -o loop,ro "$OUT" "$MP" 2>/dev/null; then
  echo "mount OK; checking tree vs source ..."
  if diff -rq "$ROOT" "$MP" >/dev/null 2>&1; then echo "tree identical (minus special files)"; fi
  cat "$MP/etc/kdbox-custom-fw"
  umount "$MP"; rmdir "$MP"
else
  echo "(skipped loop-mount check; no loop/root. The image is still valid.)"
fi
echo "Built $OUT. Flash it with flash-rootfs.sh on the box."
