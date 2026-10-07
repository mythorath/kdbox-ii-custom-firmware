#!/bin/sh
# run-on-box.sh - run ON THE BOX. Points the blake2s miner at your local stratum
# RNG server (see kdbox-rng.json; set SERVER-IP to the PC running the server) and
# lets it stream hardware nonces for RUNSECS seconds, then restores the stock stack.
RUNSECS="${RUNSECS:-30}"
echo RNG_RUN_START
killall -STOP minerd xminerd 2>/dev/null         # stop the stock stack grabbing the chip
killall xvgminer kdaminer bfgminer 2>/dev/null
sleep 1
cd /tmp
xvgminer -c /tmp/kdbox-rng.json > /tmp/rng.log 2>&1 &
BPID=$!
C=0; while [ $C -lt "$RUNSECS" ]; do sleep 1; C=$((C+1)); done
kill $BPID 2>/dev/null; killall xvgminer 2>/dev/null; sleep 1
echo "== connect =="; grep -iE 'stratum|difficulty|authori|chains|Init suces' /tmp/rng.log | head
echo "== accepted shares (each is a hardware nonce) =="; grep -c 'Accepted' /tmp/rng.log
echo RNG_RUN_DONE
killall -CONT minerd xminerd 2>/dev/null        # restore stock behavior
