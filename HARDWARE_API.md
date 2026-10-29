# Hardware telemetry contract (version 2)

Hardware **pushes** current measurements to the PC; the signed-in dashboard fetches them from the PC every 500 ms. This does not require the PC to connect inbound to the ESP32.

POST `http://PC_LAN_IP:8000/api/readings` with `Content-Type: application/json` and `Authorization: Bearer YOUR_DEVICE_TOKEN`.

```json
{
  "envelope_mv": 820.0,
  "carrier_present": true,
  "transmitter_on": null,
  "rssi": 55
}
```

- `envelope_mv`: required finite number, 0–3300 mV; ADS1115 envelope voltage.
- `carrier_present`: boolean or null/omitted. True/false must come from a validated RF detector or calibrated receiver measurement. Never derive this from audio. Unknown is null, not false.
- `transmitter_on`: boolean or null/omitted. Only report true/false when an independent hardware status input actually confirms transmitter operation. A remote receiver missing a station does not prove transmitter power is off. The supplied receiver-only sketch leaves this null.
- `rssi`: optional raw RDA5807 value 0–127; not dBm. Null on unavailable measurement. Informational only: the server does not classify from uncalibrated RSSI.
- Send at least once per second. Device is OFFLINE after 3 seconds without an accepted reading. The PC's receipt time is authoritative. Bad token = 401, invalid fields/conflicting off+carrier data = 400, hardware uploads during simulation = 409. Only one device stream is supported.

## Operating states

The server checks in this order, always using the latest accepted hardware packet:

| State | Meaning |
|---|---|
| OFFLINE | No reading, or latest is older than 3 seconds. Never implies transmitter off. |
| TRANSMITTER_OFF | Hardware explicitly reports `transmitter_on: false`. |
| NO_CARRIER | Carrier false, transmitter state true or unknown. Could be RF loss, tuning or antenna trouble. |
| UNKNOWN | Carrier measurement missing or null; do not claim normal operation from audio alone. |
| QUIET_PENDING | Carrier true and audio rise below silence threshold; waiting for configured delay. |
| CARRIER_NO_AUDIO | Carrier true and audio rise stays below silence threshold for the delay. |
| LOW_AUDIO | Carrier true and audio rise is at least the silence threshold but below normal threshold. |
| NORMAL | Carrier true and audio rise is at least the normal threshold. |

`audio rise = max(0, envelope_mv − quiet baseline)`. Defaults: silence threshold 45 mV, normal threshold 100 mV, silence delay 5 seconds. Equality with silence threshold is LOW_AUDIO; equality with normal threshold is NORMAL. Low audio and confirmed transmitter off are shown immediately; the delay applies only to sustained silence. Gaps, carrier changes, normal/low audio and threshold edits reset silence confirmation.

Examples with baseline 650 mV: 820 mV + carrier true = normal; 720 mV + carrier true = low audio; repeated 655 mV + carrier true = no audio after 5 s. `transmitter_on: false, carrier_present: false` = transmitter off. Stopping all telemetry = device offline.

## Supplied ESP32 sketch

The sketch authenticates with a separate device token. It reads envelope voltage and attempts an I²C status read for RSSI from the RDA5807M. `CARRIER_RSSI_MIN = -1` disables carrier inference until bench-calibrated. Set a validated raw threshold only after measuring your station and background/no-carrier conditions on the selected frequency. RSSI can be high from interference; reception is not proof of transmitter power. Without carrier configuration the dashboard intentionally shows carrier status unknown.

Confirmed transmitter-off detection requires an additional validated transmitter-status signal. Do not wire transmitter/RF/high-voltage circuitry directly to the ESP32. This change adds no physical transmitter-status wiring to the PDF. The firmware has not been compiled or hardware-tested here.
