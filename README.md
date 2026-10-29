# IoT FM transmission silence detector

Prototype for Windows PC + ESP32 DevKit V1 + ADS1115 + RDA5807M.
Read `Breadboard_Wiring.pdf` before applying power. Receiver physical pin order is unconfirmed: use the actual module documentation. A bare RDA5807M IC needs its reference circuit and is not a drop-in breadboard module.

## Windows dashboard — no Python packages needed

1. Install Python 3.10 or newer from python.org. Extract this entire ZIP.
2. Open PowerShell in the extracted folder.
3. Run `py -3 server.py --demo`.
4. In your own PC browser, open `http://localhost:8000`.
5. The simulation alternates about 15 seconds of audio and 10 seconds of quiet. Expect AUDIO, QUIET, then SILENCE. The source label says SIMULATION. This proves software behavior only.
6. Press Ctrl+C to stop the simulation before connecting real hardware.

## Hardware mode

1. Build and meter-check the PDF circuit. Use Arduino IDE 2, install Espressif's **esp32** board package, select **DOIT ESP32 DEVKIT V1**, and select its COM port. Some boards need their manufacturer's CP210x or CH340 USB driver. A data USB cable is required.
2. Through Library Manager install **Adafruit ADS1X15** (and its offered dependencies) and **PU2CLR RDA5807**. The sketch targets these libraries; it has not been compiled or tested on physical hardware here.
3. Open `firmware/fm_monitor.ino`. Set Wi-Fi SSID/password, station frequency, and `SERVER_URL`. Keep credentials local. Use a 2.4 GHz Wi-Fi network.
4. Find the PC's active Wi-Fi IPv4 address with `ipconfig`, e.g. 192.168.1.100. Set the sketch URL to that PC address on port 8000. ESP32 localhost refers to the ESP32 itself, so it cannot reach the PC that way.
5. Run `py -3 server.py --host 0.0.0.0` on Windows. Allow Python through Windows Firewall on **Private networks only**, on a trusted home/lab LAN. Do not expose/forward port 8000 to the Internet. This prototype has no login or TLS. Both devices must share a LAN without client isolation. Your PC browser can still use localhost:8000.
6. Upload the sketch. Serial Monitor at 115200 should show ADC readings and HTTP 200. Missing ADS1115 stops telemetry. Disconnected or hung telemetry becomes OFFLINE after 3 seconds.
7. With no receiver yet, set `USE_RADIO` to 0. Test a suitable analog signal as described in the PDF; silence baseline alone does not prove detection of sound. The radio library is unnecessary in this mode.

## Calibration and acceptance

- Set the receiver volume and leave it fixed. With known genuinely quiet audio (or temporarily ground the detector's input side of the coupling capacitor), wait 2 seconds, then click **Use latest reading as quiet baseline**. Grounding this input disconnects the receiver audio first; never short a powered receiver output.
- Restore the receiver. Note the rise above baseline for quiet and normal speech/music. Select a threshold above quiet noise and below normal programme audio. Default 45 mV and 5 seconds are starting points, not validated field settings.
- Confirm that normal audio produces AUDIO, a known silent input produces QUIET then SILENCE, restored audio clears it, and switching off ESP32 produces OFFLINE.
- The BAT43 drop makes low-level audio difficult to detect. If normal audio does not clearly exceed noise, do not assume the system works: increase the receiver volume within the PDF voltage limits or redesign for an amplified/precision envelope detector in a separate revision.
- RF noise can sound like audio during loss of station. This version detects low audio, not verified RF carrier failure. It uses one channel and may miss audio present only on the other channel. Stereo monitoring, RSSI/station-valid telemetry, alarm delivery, and persistent logs are future work.
- The chart holds the last 300 readings. Settings/history reset when Python restarts. The server accepts one hardware stream; do not run simulation with hardware.

## Files

- `Breadboard_Wiring.pdf`: net connections, schematic and safe bring-up.
- `server.py`, `index.html`: local server and dashboard, Python standard library only.
- `firmware/fm_monitor.ino`: ESP32 firmware draft.
- `test_server.py`: software checks; run `py -3 -m unittest -v test_server.py`.

No physical hardware, RF behavior, Arduino compilation, or Windows execution was available for validation in the authoring environment. The Python API and silence/offline behavior were tested on Linux. Confirm your receiver model/pinout before wiring it.
