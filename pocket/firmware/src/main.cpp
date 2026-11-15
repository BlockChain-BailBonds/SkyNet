#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <mbedtls/md.h>
#include <mbedtls/sha256.h>
#include <esp_system.h>
#include <time.h>
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
constexpr uint32_t kUplinkMs=60000;
constexpr uint32_t kMinUnixTime=1704067200;
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
uint32_t lastUplink=0;
uint32_t restartAt=0;
String wifiName,wifiPass,s3Host,ruviewPath,cameraPath,apPassword;
uint16_t s3Port=80;
String uplinkHost,uplinkId,uplinkSecret,uplinkCa,uplinkState="NOT CONFIGURED";
uint16_t uplinkPort=443;
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
  line(172,"Uplink: "+uplinkState,uplinkState=="ACK RECEIVED"?TFT_GREEN:TFT_YELLOW);
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
    line(150, uplinkHost.isEmpty()?"Uplink not configured":"Uplink gateway configured",TFT_LIGHTGREY);
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
  const char* trackedHeaders[]={"Content-Type"};
  http.collectHeaders(trackedHeaders,1);
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

bool validGatewayHost(const String& host) {
  if(host.length()<4 || host.length()>120 || host.indexOf('.')<=0 ||
     host[0]=='.' || host.endsWith(".") || host.indexOf("..")>=0) return false;
  for(size_t i=0;i<host.length();++i) {
    char c=host[i];
    if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||
         (c>='0'&&c<='9')||c=='-'||c=='.')) return false;
  }
  return true;
}
bool validDeviceId(const String& id) {
  if(id.length()<8 || id.length()>64) return false;
  for(size_t i=0;i<id.length();++i) {
    char c=id[i];
    if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||
         (c>='0'&&c<='9')||c=='_'||c=='-')) return false;
  }
  return true;
}
bool validSecret(const String& secret) {
  if(secret.length()!=64) return false;
  for(size_t i=0;i<secret.length();++i) {
    char c=secret[i];
    if(!((c>='0'&&c<='9')||(c>='a'&&c<='f'))) return false;
  }
  return true;
}
String hexBytes(const uint8_t* bytes, size_t count) {
  static const char* digits="0123456789abcdef";
  String result;
  result.reserve(count*2);
  for(size_t i=0;i<count;i++) {
    result+=digits[bytes[i]>>4];
    result+=digits[bytes[i]&15];
  }
  return result;
}
bool uplinkConfigured() {
  return validGatewayHost(uplinkHost) && validDeviceId(uplinkId) &&
         validSecret(uplinkSecret) && uplinkCa.indexOf("-----BEGIN CERTIFICATE-----")>=0 &&
         uplinkCa.indexOf("-----END CERTIFICATE-----")>=0;
}
void sendUplink() {
  if(!uplinkConfigured()) {
    uplinkState="NOT CONFIGURED";
    return;
  }
  if(WiFi.status()!=WL_CONNECTED) {
    uplinkState="WIFI OFFLINE";
    return;
  }
  const time_t seconds=time(nullptr);
  if(seconds<static_cast<time_t>(kMinUnixTime)) {
    uplinkState="CLOCK BLOCKED";
    return;
  }
  if(ESP.getMaxAllocHeap()<25000) {
    uplinkState="LOW HEAP";
    return;
  }
  StaticJsonDocument<384> message;
  message["schema"]="skynet-pocket-heartbeat/v1";
  message["kind"]="heartbeat";
  message["device_id"]=uplinkId;
  message["firmware_id"]="cyd-n4-pocket-uplink-v1";
  message["uptime_ms"]=static_cast<uint32_t>(millis());
  message["wifi_rssi_dbm"]=constrain(WiFi.RSSI(),-127,0);
  message["s3_http_ok"]=s3State=="HTTP 200 JSON";
  message["ruview_api_ok"]=ruviewState=="API RESPONDS";
  String body;
  serializeJson(message,body);
  if(body.length()==0 || body.length()>1024) {
    uplinkState="PAYLOAD BLOCKED";
    return;
  }
  uint8_t bodyHash[32];
  if(mbedtls_sha256_ret(reinterpret_cast<const unsigned char*>(body.c_str()),
                        body.length(),bodyHash,0)!=0) {
    uplinkState="SHA FAILED"; return;
  }
  uint8_t nonceData[16];
  esp_fill_random(nonceData,sizeof(nonceData));
  String nonce=hexBytes(nonceData,sizeof(nonceData));
  String stamp=String(static_cast<unsigned long>(seconds));
  String canonical=String("POST")+char(10)+"/api/pocket/heartbeat"+char(10)+
                   uplinkId+char(10)+stamp+char(10)+nonce+char(10)+
                   hexBytes(bodyHash,sizeof(bodyHash));
  uint8_t key[32];
  for(size_t i=0;i<32;++i) {
    String part=uplinkSecret.substring(i*2,i*2+2);
    key[i]=static_cast<uint8_t>(strtoul(part.c_str(),nullptr,16));
  }
  uint8_t signature[32];
  const mbedtls_md_info_t* sha=mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  bool signedOk=sha && mbedtls_md_hmac(
      sha,key,sizeof(key),
      reinterpret_cast<const unsigned char*>(canonical.c_str()),
      canonical.length(),signature)==0;
  memset(key,0,sizeof(key));
  if(!signedOk) {uplinkState="HMAC FAILED";return;}
  WiFiClientSecure tls;
  tls.setCACert(uplinkCa.c_str());
  tls.setTimeout(7);
  HTTPClient http;
  http.setTimeout(7000);
  http.setReuse(false);
  String url=String("https://")+uplinkHost+":"+String(uplinkPort)+"/api/pocket/heartbeat";
  if(!http.begin(tls,url)) {uplinkState="TLS BLOCKED";return;}
  http.addHeader("Content-Type","application/json");
  http.addHeader("X-SkyNet-Device",uplinkId);
  http.addHeader("X-SkyNet-Timestamp",stamp);
  http.addHeader("X-SkyNet-Nonce",nonce);
  http.addHeader("X-SkyNet-Signature",hexBytes(signature,sizeof(signature)));
  int code=http.POST(reinterpret_cast<uint8_t*>(const_cast<char*>(body.c_str())),body.length());
  String response;
  if(code==201 && http.getSize()>=0 && http.getSize()<512) response=http.getString();
  http.end();
  StaticJsonDocument<256> ack;
  if(code==201 && deserializeJson(ack,response)==DeserializationError::Ok &&
     ack["schema"]=="skynet-pocket-ack/v1" && ack["accepted"]==true &&
     ack["receipt"].as<String>().length()==64) {
    uplinkState="ACK RECEIVED";
    Serial.println("[uplink] accepted; signed heartbeat acknowledged");
  } else {
    uplinkState=(code>0)?"HTTP "+String(code):"TLS/NETWORK ERROR";
    Serial.println("[uplink] blocked; no accepted gateway receipt");
  }
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
<hr><h3>Optional SkyNet Main HTTPS uplink</h3>
<p>Leave blank to retain the existing uplink settings. Requires operator-approved enrollment and trusted TLS root. No GitHub token.</p>
<label>Gateway DNS host (no https://)<input name="uphost" maxlength="120" placeholder="gateway.example.org"></label><p></p>
<label>Gateway TLS port<input name="upport" type="number" min="1" max="65535" value="443"></label><p></p>
<label>Device ID<input name="upid" maxlength="64" placeholder="pocket-n4-0001"></label><p></p>
<label>Device HMAC secret (64 hex)<input name="upsecret" type="password" maxlength="64" autocomplete="off"></label><p></p>
<label>Trusted gateway CA certificate (PEM)<textarea name="upca" rows="5" maxlength="3000"></textarea></label><p></p>
<button type="submit">Save to device & reboot</button></form>
<p>Local read-only HTTP only. No video or RuView sensing is assumed.</p></body></html>)HTML";
    sendNoStore();
    web.send(200,"text/html",html);
  });
  web.on("/save",HTTP_POST,[](){
    String ssid=web.arg("ssid"), pass=web.arg("pass");
    String host=web.arg("host"), port=web.arg("port");
    String ru=web.arg("ru"), cam=web.arg("cam");
    String hostNew=web.arg("uphost"), idNew=web.arg("upid"), secretNew=web.arg("upsecret");
    String caNew=web.arg("upca");
    String portNew=web.arg("upport");
    secretNew.toLowerCase();
    long pUp=portNew.toInt();
    long p=port.toInt();
    if(ssid.length()<1 || ssid.length()>32 || pass.length()>63 ||
       !privateIp(host) || p<1 || p>65535 || !validPath(ru) || !validPath(cam)) {
      sendNoStore();web.send(400,"text/plain","Invalid SSID, S3 private IPv4, port or path.");
      return;
    }
    if(!hostNew.isEmpty() &&
       (!validGatewayHost(hostNew) || !validDeviceId(idNew) ||
        !validSecret(secretNew) || caNew.length()>3000 ||
        caNew.indexOf("-----BEGIN CERTIFICATE-----")<0 ||
        caNew.indexOf("-----END CERTIFICATE-----")<0 ||
        pUp<1 || pUp>65535)) {
      sendNoStore();
      web.send(400,"text/plain","Invalid gateway DNS, device ID, secret, TLS port or CA certificate.");
      return;
    }
    if(!hostNew.isEmpty()) {
      prefs.putString("uphost",hostNew);
      prefs.putString("upid",idNew);
      prefs.putString("upsecret",secretNew);
      prefs.putString("upca",caNew);
      prefs.putUShort("upport",static_cast<uint16_t>(pUp));
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
  uplinkHost=prefs.getString("uphost","");
  uplinkId=prefs.getString("upid","");
  uplinkSecret=prefs.getString("upsecret","");
  uplinkCa=prefs.getString("upca","");
  uplinkPort=prefs.getUShort("upport",443);
  uplinkState=uplinkConfigured()?"WAITING":"NOT CONFIGURED";
  if(!validPath(ruviewPath)) ruviewPath="/api/ruview";
  if(!validPath(cameraPath)) cameraPath="";
  showStatus();
  if(wifiName.isEmpty() || !privateIp(s3Host)) {startPortal();return;}
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(wifiName.c_str(),wifiPass.c_str());
  configTime(0,0,"pool.ntp.org","time.google.com");
  const uint32_t started=millis();
  while(WiFi.status()!=WL_CONNECTED && millis()-started<12000) {
    delay(200);
  }
  if(WiFi.status()!=WL_CONNECTED) startPortal();
  else {poll();showStatus();lastPoll=millis();lastUplink=millis()-kUplinkMs;}
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
  if(!portal && millis()-lastUplink>=kUplinkMs) {
    lastUplink=millis();
    sendUplink();
    if(page==Page::Status) showStatus();
  }
  delay(25);
}
