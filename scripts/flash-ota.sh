#!/usr/bin/env bash
# flash-ota.sh — upload a signed .cpb to a KD-Box II through its own web updater.
#
#   scripts/flash-ota.sh <miner-ip> <package.cpb> [firmware-<mcbversion>.tgz]
#
# The box verifies the package's signature, then runs its update thread. Expect ~3.5
# minutes of downtime starting a few seconds after the POST.
#
# Environment:
#   KD_USER      web user       (default: admin)
#   KD_PASS      web password   (default: 123456789 — the factory default)
#   KD_DRY_RUN=1 status + login only; do not upload
#
# Read docs/ota-signed-flash.md first. Flashing rewrites the config partition: mining
# pools are wiped and the web password returns to the factory default.

set -euo pipefail

IP="${1:-}"
PKG="${2:-}"
NAME="${3:-}"

[ -n "$IP" ] && [ -n "$PKG" ] || { echo "usage: $0 <miner-ip> <package.cpb> [filename]" >&2; exit 1; }
[ -f "$PKG" ] || { echo "error: no such package: $PKG" >&2; exit 1; }

KD_USER="${KD_USER:-admin}"
KD_PASS="${KD_PASS:-123456789}"

# The updater only accepts a file named firmware-<mcbversion>.tgz. The daemon renames
# whatever you send, but the scan matches on this pattern, so default to the header value.
if [ -z "$NAME" ]; then
    NAME=$(head -c 512 "$PKG" | python3 -c 'import sys;print(sys.stdin.buffer.read().split(b"\x00")[0].decode("ascii","replace"))')
fi
case "$NAME" in
    firmware-*.tgz) ;;
    *) echo "error: expected firmware-<mcbversion>.tgz from the package header, got '$NAME'" >&2; exit 1 ;;
esac

echo "target   $IP"
echo "package  $PKG ($(stat -c%s "$PKG") bytes)"
echo "filename $NAME"
echo "sha256   $(sha256sum "$PKG" | cut -d' ' -f1)"
echo

STATUS=$(curl -s -m 6 "http://$IP/mcb/status" || true)
case "$STATUS" in
    *'"mcbversion"'*) echo "status   $STATUS" ;;
    "") echo "error: $IP is not answering on the web UI" >&2; exit 1 ;;
    *) echo "error: $IP answered, but not with a KD-Box status document:" >&2
       echo "       ${STATUS:0:160}" >&2; exit 1 ;;
esac

MCB=$(printf '%s' "$STATUS" | sed -n 's/.*"mcbversion"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
if [ -n "$MCB" ] && [ "$NAME" != "firmware-$MCB.tgz" ]; then
    echo
    echo "WARNING: this unit reports mcbversion '$MCB' but the package is '$NAME'."
    echo "         A package built for another version can leave the box needing serial"
    echo "         recovery. Rebuild from this unit's own stock package."
    printf "         continue anyway? [y/N] "
    read -r ans 2>/dev/null </dev/tty || read -r ans || ans=""
    case "$ans" in y|Y) ;; *) echo "aborted"; exit 1 ;; esac
fi

# Login: the UI encrypts the password with AES-128-CBC, static key, zero IV, zero padding.
C=$(python3 - "$KD_PASS" <<'PY' | openssl enc -aes-128-cbc -K 21212121212121212121212121212121 \
        -iv 00000000000000000000000000000000 -nopad 2>/dev/null | xxd -p -c 256
import sys
p = sys.argv[1].encode()
sys.stdout.buffer.write(p + b'\x00' * ((-len(p)) % 16))
PY
)
[ -n "$C" ] || { echo "error: password encryption failed (need openssl + xxd + python3)" >&2; exit 1; }

LOGIN=$(curl -s -m 10 "http://$IP/user/login?username=$KD_USER&password=$C&cipher=true" || true)
JWT=$(printf '%s' "$LOGIN" | python3 -c '
import json, sys
try: print(json.load(sys.stdin)["JWT Token"])
except Exception: sys.exit(1)' 2>/dev/null) || true

if [ -z "$JWT" ]; then
    echo "error: login failed (a wrong password returns HTTP 500, not 401)." >&2
    echo "       response: ${LOGIN:0:160}" >&2
    echo "       set KD_USER / KD_PASS if the admin password was changed." >&2
    exit 1
fi
echo "login    ok (${#JWT} char token)"

if [ "${KD_DRY_RUN:-0}" = "1" ]; then
    echo
    echo "dry run — not uploading. The real request is:"
    echo "  curl -X POST -H 'Authorization: Bearer <jwt>' -F 'file=@$PKG;filename=$NAME' \\"
    echo "       http://$IP/mcb/uploadimage"
    exit 0
fi

echo
echo "uploading — the box will drop off the network almost immediately"
code=$(curl -s -m 300 -X POST -H "Authorization: Bearer $JWT" \
        -F "file=@$PKG;filename=$NAME" -o /dev/null -w '%{http_code}' \
        "http://$IP/mcb/uploadimage" || true)
echo "POST     ${code:-<connection closed>}"
echo
echo "watching for the box to come back (up to ~6 min)..."

for _ in $(seq 1 36); do
    sleep 10
    w=$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://$IP/mcb/status" || true)
    printf '  %s  http=%s\n' "$(date +%H:%M:%S)" "${w:-000}"
    if [ "$w" = "200" ]; then
        echo
        echo "back up:"
        curl -s -m 6 "http://$IP/mcb/status"; echo
        echo
        echo "verify root (legacy flags are required — OpenSSH 6.4, RSA only):"
        echo "  ssh -i ~/.ssh/id_ed25519 -o PubkeyAcceptedKeyTypes=+ssh-rsa \\"
        echo "      -o HostKeyAlgorithms=+ssh-rsa root@$IP 'id; cat /etc/kdbox-custom-fw'"
        exit 0
    fi
done

echo
echo "warning: the box has not come back after 6 minutes." >&2
echo "         If it is still on the old image it will answer eventually. If the rootfs" >&2
echo "         failed to mount, recovery needs the J2 console (docs/serial-and-root.md)." >&2
exit 1
