"""
tx_stream_test.py  -  stream 0x00 bytes out a COM port so a multimeter can see it.

A 0x00 byte is nine low bits out of ten on the wire, so any line the data is
actually reaching sags from ~3.3 V idle down to a few tenths of a volt for the
whole run. A line the data is NOT reaching stays at 3.3 V.

Usage:
    pip install pyserial
    python tx_stream_test.py COM4            (default 115200, 20 seconds)
    python tx_stream_test.py COM4 115200 30

Close PuTTY / Arduino serial monitor first; only one program can own the port.
"""
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed: pip install pyserial")

port = sys.argv[1] if len(sys.argv) > 1 else "COM4"
baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0

chunk = b"\x00" * 4096
with serial.Serial(port, baud, timeout=0) as s:
    # Leave DTR/RTS alone; on an ESP devkit they touch EN/IO0 through the
    # auto-reset transistors. EN is jumpered to GND anyway if you're using
    # the pass-through trick, so this is belt and braces.
    print(f"streaming zeros on {port} @ {baud} for {secs:.0f} s ... meter time")
    t0 = time.time()
    sent = 0
    while time.time() - t0 < secs:
        s.write(chunk)
        s.flush()
        sent += len(chunk)
    print(f"done, {sent} bytes sent ({sent / secs / 1000:.1f} kB/s)")
