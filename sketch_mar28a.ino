#include <WiFi.h>
#include <WiFiUdp.h>

// --- Network Settings ---
const char* ssid = "yashmitbum";
const char* password = "yashmitisabum";
const char* udpAddress = "192.168.137.1";
const int udpPort = 5005;

// --- Hardware Settings ---
const int BUTTON_PIN = 1; // Standard C3 Boot Button
WiFiUDP udp;

void setup() {
  // Essential for ESP32-C3 USB Serial
  Serial.begin(115200);
  
  
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  Serial.println("\n--- ESP32-C3 HIGH-SPEED START ---");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\n✅ Connected to Hotspot!");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    // 1 if pressed, 0 if not
    int state = (digitalRead(BUTTON_PIN) == LOW) ? 1 : 0;
    
    // --- CONSTANT SERIAL OUT ---
    if (state == 1) {
      Serial.println("STATE: PRESSED [1]");
    } else {
      Serial.println("STATE: NOT PRESSED [0]");
    }

    // --- HIGH SPEED NETWORK SEND ---
    udp.beginPacket(udpAddress, udpPort);
    udp.print(state);
    udp.endPacket();
  }

  // Adjust this for speed: 10ms = 100Hz, 1ms = 1000Hz
  delay(10); 
}