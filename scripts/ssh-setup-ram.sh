#!/bin/sh
# ssh-setup-ram.sh - run ON THE BOX from the serial shell. Brings sshd up for the
# CURRENT session only (gone after reboot). The rootfs is a read-only squashfs, so
# we set a known root password via a bind mount and start sshd by hand.
#
# Set KDBOX_ROOT_HASH to a crypt() DES hash for the password you want. Optionally
# put your public key at /tmp/.ssh/authorized_keys first for key auth.
#
# Remember OpenSSH 6.4: use an RSA key and connect with
#   -o PubkeyAcceptedKeyTypes=+ssh-rsa -o HostKeyAlgorithms=+ssh-rsa
HASH="${KDBOX_ROOT_HASH:-}"
if [ -n "$HASH" ]; then
  cp /etc/shadow /tmp/shadow
  sed -i "s|^root:[^:]*:|root:$HASH:|" /tmp/shadow
  mount -o bind /tmp/shadow /etc/shadow
fi
# host key in a writable spot if none is usable
[ -f /etc/ssh_host_rsa_key ] || ssh-keygen -t rsa -f /tmp/ssh_host_rsa_key -N "" -C "" >/dev/null 2>&1
AKF=""
[ -f /tmp/.ssh/authorized_keys ] && AKF="-o AuthorizedKeysFile=/tmp/.ssh/authorized_keys"
/usr/sbin/sshd -o PermitRootLogin=yes -o PasswordAuthentication=yes -o PubkeyAuthentication=yes \
               -o UseDNS=no -o StrictModes=no $AKF
echo "sshd started (RAM only). It will be killed by the mgmt daemon on a stock image;"
echo "re-run this if it drops, or flash a build with permanent SSH to make it stick."
