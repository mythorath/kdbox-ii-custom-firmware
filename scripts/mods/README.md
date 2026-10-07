# Mods

The reference build applies the minimum needed to make SSH permanent, so the
modify/rebuild/flash pipeline can be proven with the least risk. `build-rootfs.sh`
performs these against your extracted rootfs:

1. **root SSH key** - adds `/root/.ssh/authorized_keys` (your key, which you pass in).
2. **keep sshd alive** - rewrites `stop()` in `/etc/init.d/S50sshd` to a no-op so the
   management daemon's `S50sshd stop` call can no longer `killall sshd`. sshd is already
   started at boot and the host keys already exist in `/etc`, so this is all that is needed.
3. **optional root password** - set `KDBOX_ROOT_HASH` to a `crypt()` hash to enable
   password login as a fallback (key auth is preferred).
4. **marker** - writes `/etc/kdbox-custom-fw` so a modified box is identifiable.

Everything else is left byte for byte identical to stock. Future builds (coin
conversion, etc.) layer on top of this same mechanism.

Generate a key (RSA, because the box runs OpenSSH 6.4):

    ssh-keygen -t rsa -b 2048 -f kdbox_rsa -N ""

Then pass `kdbox_rsa.pub` as the authorized_keys argument to build-rootfs.sh.
