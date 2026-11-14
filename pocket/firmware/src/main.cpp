#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <Preferences.h>
#include <SPI.h>
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>
#include <ArduinoJson.h>
#include <TJpg_Decoder.h>

// SkyNet Pocket — original ESP32-2432S028R, 4 MB, no PSRAM.
// Separate buses: ILI9341 HSPI (TFT_eSPI flags), XPT2046 VSPI.
// All S3 endpoints are read-only. This firmware does not claim RuView CSI capture.
namespace {
constexpr uint8_t kBacklight=21;
constexpr uint8_t kTouchCs=33;
constexpr uint8_t kTouchIrq=36;
constexpr uint32_t kPollMs=8000;
constexpr uint32_t kTimeoutMs=3500;
constexpr size_t kMaxJson=4096;
constexpr size_t kMaxJpeg=65536;
constexpr int kFooterY=204;
TFT_eSPI display;
SPIClass touchBus(VSPI);
XPT2046_Touchscreen touch(kTouchCs,kTouchIrq);
Preferences prefs;
WebServer web(80);

enum class Page : uint8_t { Status, Camera, Setup };
Page page=Page::Status;
bool portal=false;
bool lastTouch=false;
bool cameraShown=false;
uint32_t lastPoll=0;
uint32_t restartAt=0;
String wifiName,wifiPass,s3Host,ruviewPath,cameraPath,apPassword;
uint16_t s3Port=80;
String s3State="UNVERIFIED",ruviewState="UNVERIFIED",cameraState="UNVERIFIED";

bool privateIp(const String& host) {
  IPAddress ip;
  if(!ip.fromString(host)) return false;
  uint8_t a=ip[0], b=ip[1];
  return a==10 || (a==172 && b>=16 && b<=31) || (a==192 && b==168);
}
bool validPath(const String& path) {
  if(path.length()==0) return true;
  if(path.length()>80 || path[0]!='/' || path.indexOf("..")>=0) return false;
  for(size_t i=0;i<path.length();++i) {
    const char c=path[i];
    if(!(isalnum(static_cast<unsigned char>(c)) || c=='/' || c=='-' || c=='_' || c=='.')) return false;
  }
  return true;
}
String endpoint(const String& path) {
  return String("http://")+s3Host+":"+String(s3Port)+path;
}
void line(int y,const String& label,uint16_t color=TFT_WHITE) {
  display.setTextColor(color,TFT_BLACK);
  display.drawString(label,8,y,2);
}
void header(const String& title) {
  display.fillScreen(TFT_BLACK);
  display.fillRect(0,0,320,27,TFT_DARKGREY);
  display.setTextColor(TFT_YELLOW,TFT_DARKGREY);
  display.drawString("918  SKYNET POCKET",7,5,2);
  display.setTextColor(TFT_WHITE,TFT_BLACK);
  display.drawString(title,8,32,2);
}
void footer() {
  const char* names[3]={"STATUS","CAMERA","SETUP"};
  for(int i=0;i<3;i++) {
    uint16_t c=static_cast<int>(page)==i?TFT_YELLOW:TFT_DARKGREY;
    display.fillRoundRect(3+i*106,kFooterY,101,33,5,c);
    display.setTextColor(static_cast<int>(page)==i?TFT_BLACK:TFT_WHITE,c);
    display.drawCentreString(names[i],53+i*106,kFooterY+9,2);
  }
}
void showStatus() {
  page=Page::Status;
  header("S3 + RuView evidence");
  line(56,String("Wi-Fi: ")+(WiFi.status()==WL_CONNECTED?"CONNECTED":"OFFLINE"),
       WiFi.status()==WL_CONNECTED?TFT_GREEN:TFT_RED);
  line(79,"S3: "+s3State,s3State=="HTTP 200 JSON"?TFT_GREEN:TFT_ORANGE);
  line(102,"RuView: "+ruviewState,ruviewState=="API RESPONDS"?TFT_GREEN:TFT_ORANGE);
  line(125,"Camera: "+cameraState,cameraState=="JPEG RECEIVED"?TFT_GREEN:TFT_ORANGE);
  line(149,"Heap: "+String(ESP.getFreeHeap())+" B",TFT_LIGHTGREY);
  line(172,"No CSI or camera claim from HTTP alone",TFT_YELLOW);
  footer();
}
void showCamera() {
  page=Page::Camera;
  header("Camera: tap picture area to fetch");
  if(cameraShown) line(56,"Last frame shown; not live video",TFT_YELLOW);
  else {
    line(64,cameraPath.length()?"Touch above menu for JPEG snapshot":"Configure snapshot path in SETUP",TFT_WHITE);
    line(97,"S3: "+s3Host,TFT_LIGHTGREY);
    line(124,"Camera: "+cameraState,TFT_ORANGE);
    line(151,"JPEG <=64 KiB; memory bounded",TFT_LIGHTGREY);
  }
  footer();
}
void showSetup() {
  page=Page::Setup;
  header("Wi-Fi / S3 configuration");
  if(portal) {
    line(65,"Connect to: SKYNET-CYD",TFT_YELLOW);
    line(90,"Wi-Fi key: "+apPassword,TFT_WHITE);
    line(116,"Open http://192.168.4.1",TFT_GREEN);
    line(147,"Device-only WPA2 setup portal",TFT_LIGHTGREY);
  } else {
    line(64,"Tap upper area to start setup AP",TFT_YELLOW);
    line(92,"Saved Wi-Fi: "+wifiName,TFT_WHITE);
    line(120,"S3 host: "+s3Host,TFT_WHITE);
    line(150,"Settings stored in ESP32 NVS",TFT_LIGHTGREY);
  }
  footer();
}
bool fetchJson(const String& path) {
  if(WiFi.status()!=WL_CONNECTED || !privateIp(s3Host) || !validPath(path)) return false;
  WiFiClient client;
  HTTPClient http;
  http.setTimeout(kTimeoutMs);
  http.setReuse(false);
  if(!http.begin(client,endpoint(path))) return false;
  const int code=http.GET();
  if(code!=200) { http.end(); return false; }
  int sz=http.getSize();
  if(sz<2 || sz>static_cast<int>(kMaxJson)) {http.end();return false;}
  String body=http.getString();
  http.end();
  if(body.length()<2 || body.length()>kMaxJson) return false;
  StaticJsonDocument<1024> doc;
  DeserializationError error=deserializeJson(doc,body,DeserializationOption::NestingLimit(6));
  return !error && (doc.is<JsonObject>() || doc.is<JsonArray>());
}
bool jpgOutput(int16_t x,int16_t y,uint16_t w,uint16_t h,uint16_t* data) {
  if(y>=kFooterY || x>=320) return false;
  if(x<0 || y<0 || x+w>320 || y+h>kFooterY) return false;
  display.pushImage(x,y,w,h,data);
  return true;
}
bool showJpeg() {
  cameraShown=false;
  if(cameraPath.isEmpty() || !validPath(cameraPath) ||
     WiFi.status()!=WL_CONNECTED || !privateIp(s3Host)) {
    cameraState="NOT CONFIGURED";
    return false;
  }
  WiFiClient client;
  HTTPClient http;
  http.setTimeout(6000);
  http.setReuse(false);
  if(!http.begin(client,endpoint(cameraPath))) {
    cameraState="CONNECT FAILED"; return false;
  }
  int code=http.GET();
  String type=http.header("Content-Type");
  int len=http.getSize();
  if(code!=200 || !type.startsWith("image/jpeg") || len<4 ||
     len>static_cast<int>(kMaxJpeg) || ESP.getMaxAllocHeap()<(size_t)len+10000) {
    cameraState="JPEG UNAVAILABLE";
    http.end(); return false;
  }
  uint8_t* data=static_cast<uint8_t*>(malloc(len));
  if(!data) {cameraState="LOW MEMORY";http.end();return false;}
  WiFiClient* stream=http.getStreamPtr();
  size_t got=0;
  const uint32_t started=millis();
  while(got<(size_t)len && millis()-started<6000) {
    size_t n=stream->readBytes(data+got,min(static_cast<size_t>(len)-got,(size_t)1024));
    if(n==0) break;
    got+=n;
    delay(0);
  }
  http.end();
  if(got!=(size_t)len || data[0]!=0xFF || data[1]!=0xD8) {
    cameraState="INVALID JPEG";free(data);return false;
  }
  uint16_t width=0,height=0;
  TJpgDec.getJpgSize(&width,&height,data,static_cast<uint32_t>(len));
  if(width==0 || height==0) {
    cameraState="DECODE FAILED";free(data);return false;
  }
  uint8_t scale=1;
  while(scale<8 && ((width+scale-1)/scale>320 || (height+scale-1)/scale>kFooterY-1)) scale*=2;
  if((width+scale-1)/scale>320 || (height+scale-1)/scale>kFooterY-1) {
    cameraState="FRAME TOO LARGE";free(data);return false;
  }
  display.fillRect(0,0,320,kFooterY,TFT_BLACK);
  TJpgDec.setJpgScale(scale);
  TJpgDec.setSwapBytes(true);
  TJpgDec.drawJpg(0,0,data,static_cast<uint32_t>(len));
  free(data);
  cameraState="JPEG RECEIVED";
  cameraShown=true;
  footer();
  return true;
}
void poll() {
  if(portal || WiFi.status()!=WL_CONNECTED) {
    s3State="OFFLINE";ruviewState="OFFLINE";return;
  }
  s3State=fetchJson("/api/status")?"HTTP 200 JSON":"NO JSON / OFFLINE";
  ruviewState=ruviewPath.isEmpty()?"NOT CONFIGURED":
              (fetchJson(ruviewPath)?"API RESPONDS":"NO JSON / OFFLINE");
}
void sendNoStore() {
  web.sendHeader("Cache-Control","no-store");
  web.sendHeader("Pragma","no-cache");
}
void startPortal() {
  if(portal) { showSetup();return; }
  portal=true;
  WiFi.disconnect(true);
  WiFi.mode(WIFI_AP);
  char secret[16];
  snprintf(secret,sizeof(secret),"Cyd%08lX",(unsigned long)esp_random());
  apPassword=secret;
  if(!WiFi.softAP("SKYNET-CYD",apPassword.c_str())) {
    portal=false;apPassword="AP FAILED";showSetup();return;
  }
  web.on("/",HTTP_GET,[](){
    const char html[]=R"HTML(<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-store"><title>SkyNet CYD setup</title></head>
<body style="font:18px system-ui;background:#111;color:#e8c35c;max-width:30em;margin:auto;padding:1em">
<h2>918 SkyNet Pocket</h2><p>Configure only authorized local devices. Credentials remain on the CYD.</p>
<form method="post" action="/save" autocomplete="off">
<label>Wi-Fi SSID<input required maxlength="32" name="ssid"></label><p></p>
<label>Wi-Fi password<input type="password" maxlength="63" name="pass" autocomplete="new-password"></label><p></p>
<label>S3 private IPv4 address<input required name="host" placeholder="192.168.1.25"></label><p></p>
<label>S3 HTTP port<input type="number" min="1" max="65535" value="80" name="port"></label><p></p>
<label>RuView JSON path<input name="ru" value="/api/ruview" maxlength="80"></label><p></p>
<label>Camera JPEG path (optional)<input name="cam" placeholder="/capture" maxlength="80"></label><p></p>
<button type="submit">Save to device & reboot</button></form>
<p>Local read-only HTTP only. No video or RuView sensing is assumed.</p></body></html>)HTML";
    sendNoStore();
    web.send(200,"text/html",html);
  });
  web.on("/save",HTTP_POST,[](){
    String ssid=web.arg("ssid"), pass=web.arg("pass");
    String host=web.arg("host"), port=web.arg("port");
    String ru=web.arg("ru"), cam=web.arg("cam");
    long p=port.toInt();
    if(ssid.length()<1 || ssid.length()>32 || pass.length()>63 ||
       !privateIp(host) || p<1 || p>65535 || !validPath(ru) || !validPath(cam)) {
      sendNoStore();web.send(400,"text/plain","Invalid SSID, S3 private IPv4, port or path.");
      return;
    }
    prefs.putString("ssid",ssid);
    prefs.putString("pass",pass);
    prefs.putString("host",host);
    prefs.putUShort("port",static_cast<uint16_t>(p));
    prefs.putString("ru",ru);
    prefs.putString("cam",cam);
    sendNoStore();
    web.send(200,"text/plain","Saved to device. CYD restarting.");
    restartAt=millis()+1200;
  });
  web.onNotFound([](){sendNoStore();web.send(404,"text/plain","Not found");});
  web.begin();
  showSetup();
}
void handleTouch() {
  bool pressed=touch.touched();
  if(pressed && !lastTouch) {
    TS_Point pt=touch.getPoint();
    // Reference-board defaults; calibrate on physical device if coordinates drift.
    int x=constrain(map(pt.x,200,3900,0,319),0,319);
    int y=constrain(map(pt.y,200,3900,0,239),0,239);
    if(y>=kFooterY) {
      if(x<106) showStatus();
      else if(x<212) showCamera();
      else showSetup();
    } else if(page==Page::Setup && !portal) {
      startPortal();
    } else if(page==Page::Camera) {
      if(!showJpeg()) showCamera();
    } else if(page==Page::Status) {
      poll();showStatus();
    }
  }
  lastTouch=pressed;
}
} // namespace

void setup() {
  Serial.begin(115200);
  pinMode(kBacklight,OUTPUT);
  digitalWrite(kBacklight,HIGH);
  display.init();
  display.setRotation(1);
  display.setTextWrap(false);
  touchBus.begin(25,39,32,kTouchCs);
  touch.begin(touchBus);
  touch.setRotation(1);
  TJpgDec.setCallback(jpgOutput);
  prefs.begin("skynet-cyd",false);
  wifiName=prefs.getString("ssid","");
  wifiPass=prefs.getString("pass","");
  s3Host=prefs.getString("host","");
  s3Port=prefs.getUShort("port",80);
  ruviewPath=prefs.getString("ru","/api/ruview");
  cameraPath=prefs.getString("cam","");
  if(!validPath(ruviewPath)) ruviewPath="/api/ruview";
  if(!validPath(cameraPath)) cameraPath="";
  showStatus();
  if(wifiName.isEmpty() || !privateIp(s3Host)) {startPortal();return;}
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(wifiName.c_str(),wifiPass.c_str());
  const uint32_t started=millis();
  while(WiFi.status()!=WL_CONNECTED && millis()-started<12000) {
    delay(200);
  }
  if(WiFi.status()!=WL_CONNECTED) startPortal();
  else {poll();showStatus();lastPoll=millis();}
}
void loop() {
  if(portal) web.handleClient();
  handleTouch();
  if(restartAt && millis()>=restartAt) ESP.restart();
  if(!portal && millis()-lastPoll>=kPollMs) {
    lastPoll=millis();
    poll();
    if(page==Page::Status) showStatus();
  }
  delay(25);
}
