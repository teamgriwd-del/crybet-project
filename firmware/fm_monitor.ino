/* ESP32 DevKit V1. See breadboard PDF before connecting power.
   Arduino libraries: Adafruit ADS1X15, PU2CLR RDA5807.
   Set USE_RADIO to 0 for analog bench tests without the receiver.
*/
#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#define USE_RADIO 1
#if USE_RADIO
#include <RDA5807.h>
RDA5807 radio;
#endif
Adafruit_ADS1115 ads;
const char* WIFI_SSID = "YOUR_2_4_GHZ_WIFI";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
// Use the Windows PC's LAN IPv4 address, never localhost here.
const char* SERVER_URL = "http://192.168.1.100:8000/api/readings";
// Generate on PC: py -3 server.py --create-device-token
const char* DEVICE_TOKEN = "YOUR_DEVICE_TOKEN";
// Leave -1 until calibrated against your station and no-carrier receiver noise.
// Raw RSSI is 0..127, not dBm. Thresholding is a receiver-side estimate only.
const int CARRIER_RSSI_MIN = -1;
const uint16_t FM_FREQUENCY = 10000; // 100.00 MHz; PU2CLR uses 10 kHz units
unsigned long lastWifiAttempt = 0;
void setup() {
  Serial.begin(115200);
  Wire.begin(21,22);
  if (!ads.begin(0x48)) { Serial.println("ADS1115 missing: check 3.3V, GND, SDA, SCL, ADDR"); while(true) delay(1000); }
  ads.setGain(GAIN_ONE); // +/-4.096V scale does NOT permit inputs above supply
  ads.setDataRate(RATE_ADS1115_128SPS);
#if USE_RADIO
  radio.setup();
  radio.setFrequency(FM_FREQUENCY);
  radio.setVolume(8); // Keep fixed after calibrating the detector
#endif
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
}
// RDA5807 sequential read address 0x10 starts with status registers 0x0A/0x0B.
// Register 0x0B bits 15:9 hold the raw 7-bit RSSI. Check actual module datasheet.
int readReceiverRssi() {
#if USE_RADIO
  if (Wire.requestFrom((uint8_t)0x10, (uint8_t)4) != 4) {
    while (Wire.available()) Wire.read();
    return -1;
  }
  Wire.read(); Wire.read();
  uint8_t high = Wire.read(); Wire.read();
  return high >> 1;
#else
  return -1;
#endif
}
void loop() {
  // Average envelope, not raw audio. Eight conversions take about 64 ms.
  float sum=0;
  for (int i=0;i<8;i++) sum += ads.computeVolts(ads.readADC_SingleEnded(0))*1000.0f;
  float mv=sum/8;
  Serial.printf("Envelope %.1f mV; WiFi %s\n",mv,WiFi.status()==WL_CONNECTED?"connected":"offline");
  if (WiFi.status()==WL_CONNECTED) {
    HTTPClient http;
    http.setConnectTimeout(1500); http.setTimeout(1500);
    http.begin(SERVER_URL); http.addHeader("Content-Type","application/json");
    http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
    int rssi = readReceiverRssi();
    String carrier = "null";
    if (rssi >= 0 && CARRIER_RSSI_MIN >= 0) carrier = rssi >= CARRIER_RSSI_MIN ? "true" : "false";
    String payload = "{\"envelope_mv\":" + String(mv,1)
      + ",\"carrier_present\":" + carrier
      + ",\"transmitter_on\":null,\"rssi\":" + (rssi < 0 ? String("null") : String(rssi)) + "}";
    // transmitter_on must come from a validated, independent transmitter status sensor.
    // A remote FM receiver cannot prove transmitter power status; never infer it from audio.
    int code=http.POST(payload);
    Serial.printf("HTTP result %d\n",code); http.end();
  } else if (millis()-lastWifiAttempt>10000) {
    lastWifiAttempt=millis(); WiFi.reconnect();
  }
  delay(250);
}
