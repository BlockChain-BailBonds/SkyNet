#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <TFT_eSPI.h>
#include <ArduinoJson.h>
#include "mbedtls/pk.h"
// ESP32-2432S028R (ESP32E N4 CYD) candidate pins are explicit in platformio.ini.
// Confirm the physical board revision before flashing. No GitHub write token is used.
TFT_eSPI tft; Preferences prefs; const char *snapshot="https://blockchain-bailbonds.github.io/SkyNet/data/public/latest-alerts.json";
void show(const char* title,const char* line,uint16_t color){tft.fillScreen(TFT_BLACK);tft.setTextColor(color,TFT_BLACK);tft.drawString(title,8,12,4);tft.setTextColor(TFT_WHITE);tft.drawString(line,8,55,2);}
bool validAlert(JsonObject a,time_t now){if(!a["id"].is<const char*>()||!a["expires"].is<const char*>())return false;struct tm tm{};if(!strptime(a["expires"],"%Y-%m-%dT%H:%M:%SZ",&tm))return false;return timegm(&tm)>now;}
void setup(){Serial.begin(115200);tft.init();tft.setRotation(1);show("SKYNET POCKET","Provision Wi-Fi via authorized build configuration",TFT_YELLOW);WiFi.mode(WIFI_STA);configTime(0,0,"pool.ntp.org");/* Production provisioning uses a local captive portal and device-generated Ed25519 key stored in encrypted NVS. */}
void loop(){static unsigned long last=0;if(millis()-last<60000)return;last=millis();if(WiFi.status()!=WL_CONNECTED){show("OFFLINE","Buffered status; reconnecting",TFT_ORANGE);WiFi.reconnect();return;}HTTPClient http;http.setTimeout(8000);http.begin(snapshot);int code=http.GET();if(code!=200){show("FEED BLOCKED","Snapshot unavailable",TFT_RED);http.end();return;}DynamicJsonDocument doc(32768);auto err=deserializeJson(doc,http.getString());http.end();if(err){show("FEED FAILED","Malformed snapshot rejected",TFT_RED);return;}int active=0;for(JsonObject a:doc.as<JsonArray>())if(validAlert(a,time(nullptr)))active++;show(active?"PUBLIC ALERT":"NO ACTIVE ALERT",active?"See official source":"Best-effort snapshot",active?TFT_RED:TFT_GREEN);}
