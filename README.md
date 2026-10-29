# IoT FM transmission monitor

Windows PC dashboard with phone/password login, glass UI and authenticated ESP32 telemetry. Python 3.10+ standard library only; no pip packages required for running the dashboard.

## First run on Windows

1. Download and extract the latest GitHub ZIP. Open PowerShell in the folder containing `server.py`.
2. Create your local account, replacing the example with **your phone number in international format**:

   ```powershell
   py -3 server.py --create-user "+263771234567"
   ```

   Enter your own password (at least 12 characters) twice. Typing is hidden in the terminal; that is expected. There is no default password. The phone identifies a local account; there is no SMS verification or SMS alert service.
3. Start simulation:

   ```powershell
   py -3 server.py --demo
   ```

4. Open `http://localhost:8000` and sign in with your phone number and chosen password.
5. Simulation cycles through normal, low audio, carrier on/no audio (after the delay), and transmitter off in 12-second phases. Simulation is prominently labelled and uses generated data only. Stop with Ctrl+C before hardware mode.

## Hardware mode

Read `Breadboard_Wiring.pdf` before wiring power and `HARDWARE_API.md` for telemetry fields and state rules. Verify the actual receiver pinout; a bare IC requires its reference circuit and PCB.

1. Install Arduino IDE 2, Espressif's esp32 board package, **Adafruit ADS1X15** and **PU2CLR RDA5807** libraries. Select DOIT ESP32 DEVKIT V1 and its COM port. Use a USB data cable and the manufacturer's USB driver if needed.
2. Generate a device credential on your PC:

   ```powershell
   py -3 server.py --create-device-token
   ```

   Copy the displayed token to `DEVICE_TOKEN` in your **local** firmware. The server stores only its hash. Running this command again replaces the previous credential. Do not share the token or commit edited credentials to GitHub.
3. Set Wi-Fi SSID/password, station frequency and PC URL in `firmware/fm_monitor.ino`. Find the active Wi-Fi IPv4 address with `ipconfig`; use e.g. `http://192.168.1.100:8000/api/readings`. ESP32 localhost refers to itself, not the PC.
4. Start the server:

   ```powershell
   py -3 server.py --host 0.0.0.0
   ```

   Both devices need the same trusted private LAN without client isolation; ESP32 uses 2.4 GHz Wi-Fi. Allow Python through Windows Firewall on Private networks only. Continue using `http://localhost:8000` in your PC browser.
5. Upload the sketch. Serial Monitor 115200 should show ADC readings and HTTP 200. Missing ADC halts sampling; missing telemetry shows Device offline.
6. The sketch leaves carrier unknown until `CARRIER_RSSI_MIN` is calibrated; `-1` means unconfigured. RSSI is receiver raw units, not dBm. The receiver-only hardware cannot prove transmitter power state; `transmitter_on` remains null until an independent sensor is integrated. See the API document before enabling carrier inference.
7. Without the receiver, set `USE_RADIO` to 0 for analog bench tests; carrier/transmitter states correctly remain unknown.

## Detection and calibration

- Four main operating conditions: **Normal operation**, **Low audio**, **Carrier on · no audio**, **Transmitter off**. Extra states distinguish no carrier, unknown carrier, quiet awaiting delay, device offline and server unavailable.
- Normal/no-audio/low-audio classification requires hardware carrier data. Audio alone cannot establish RF state. Explicit transmitter-off data takes priority. Receiver signal loss is labelled No carrier detected, not assumed power-off.
- Fix radio volume. Apply a known quiet input, wait 2 s, then calibrate the quiet baseline. Never short a powered audio output; follow PDF input-disconnection instructions.
- Set silence threshold above noise; set normal threshold above that and below normal programme audio. Defaults (45 / 100 mV and 5 s) require real measurements. Low audio is between those thresholds. No audio requires sustained readings below the silence threshold.
- Verify all four conditions using known hardware inputs, plus sensor disconnection/offline behavior. A silent baseline alone does not prove sound detection.
- The BAT43 diode has a low-level dead zone. If quiet and normal levels overlap, adjust receiver volume within circuit limits or redesign the detector; do not claim valid detection.
- Settings and latest 300 readings are held in memory and reset on restart; accounts and the hashed device credential persist in `.fm-monitor/` on this PC. Keep the folder when updating project files. If extracting into a new folder, recreate the account/token or move your private `.fm-monitor` folder locally. Never upload it.

## Login, password reset and access limits

Passwords use PBKDF2-HMAC-SHA256 (600,000 iterations, random salts). Browser sessions use HttpOnly, SameSite=Strict cookies, expire after 8 hours and are invalidated on logout or server restart. APIs require a session for monitoring/settings; hardware writes use a separate device token. Browser login is rate-limited to five attempts per minute per client IP. All local accounts can view and change the single monitor.

To reset a password, stop the server, rerun `--create-user` with the same phone and choose a new password, then restart. No phone verification, self-registration, cloud account or remote password recovery is included.

This is a local prototype: HTTP does not encrypt passwords or device tokens on the LAN. Use the browser on localhost, keep the LAN trusted, and do not expose/forward port 8000 to the Internet. An Internet deployment needs HTTPS, a production server and further security work.

## Development validation

Run `py -3 -m unittest -v test_server.py` for state, authentication and HTTP checks. `make_pdf.py` regenerates the original wiring guide if ReportLab is installed (`py -3 -m pip install reportlab`); PDF generation is optional and unnecessary for running the dashboard. The guide concerns the analog circuit; use this README and HARDWARE_API.md for current login and monitoring instructions, which supersede its older software steps.

Physical circuit, Arduino compilation and Windows execution have not been verified here. Confirm your receiver model/pinout and bench-test sensor calibration before relying on alarms.
