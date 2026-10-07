/*
  kdbox_uart_bridge.ino  (v3, fixed 115200, no button)
  ----------------------------------------------------
  ESP32 <-> KD-Box II serial console bridge, locked at 115200 8N1.

  v2 had a BOOT-button feature that cycled the baud. GPIO0 (BOOT) is also
  pulsed by the USB auto-program circuit (DTR) whenever a terminal opens or
  the board resets, so it kept knocking the bridge off 115200. Removed. This
  version does one thing: pass bytes both ways at 115200, forever.

  WHY THE ESP32 AND NOT A PLAIN USB-SERIAL ADAPTER:
  The KD console lines sit behind a passive MOSFET level shifter with ~1.5k
  pull-ups to 3.3 V. A USB-serial adapter's output has series resistance and
  can only drag the line to ~1.5 V, which the shifter ignores, so typed bytes
  never reach the SoC. An ESP32 GPIO drives push-pull with no series resistor
  and pulls the line to ~0.1 V, under the shifter threshold. That is the job.

  WIRING  (38-pin ELEGOO ESP-WROOM-32)      KD-Box J2
    GND ------------------------------------> GND   (connect first)
    RX2 / GPIO16 (input)  <------------------ TX    (board transmit)
    TX2 / GPIO17 (output) ------------------> RX    (board receive)
    Leave TX0/RX0 (GPIO1/GPIO3) empty.

  PC side: terminal at 115200 8N1 on the ESP's COM port.
  PuTTY: Flow control = None. If lines stack, enable "Implicit CR in every LF".
*/

#include <Arduino.h>

#define BRIDGE_RX 16      // RX2 pin  <- KD TX
#define BRIDGE_TX 17      // TX2 pin  -> KD RX
#define USB_BAUD  115200
#define KD_BAUD   115200

void setup() {
  Serial.begin(USB_BAUD);
  delay(300);
  Serial.print("\r\n[bridge] KD-Box II bridge v3, locked 115200 8N1.\r\n");
  Serial.print("[bridge] KD text streams below. Press Enter, look for '/ #'.\r\n");
  Serial1.setRxBufferSize(4096);
  Serial1.begin(KD_BAUD, SERIAL_8N1, BRIDGE_RX, BRIDGE_TX);
}

void loop() {
  // KD -> PC
  while (Serial1.available()) {
    int c = Serial1.read();
    if (c < 0) break;
    Serial.write((uint8_t)c);
  }
  // PC -> KD
  while (Serial.available()) {
    int c = Serial.read();
    if (c < 0) break;
    Serial1.write((uint8_t)c);
  }
}
