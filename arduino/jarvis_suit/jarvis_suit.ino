/*
  jarvis_suit.ino — lets JARVIS control your suit/props over USB.

  Upload with the Arduino IDE (Board: Arduino Uno or Nano). JARVIS sends one
  command per line at 9600 baud and the Arduino answers "OK <command>".

  WIRING (Arduino Uno / Nano)
    Pin 9  -> faceplate servo signal (orange/yellow wire)
    Pin 6  -> eye LEDs  (through a 220 ohm resistor each, LED - to GND)
    Pin 5  -> arc-reactor LED or LED ring data/anode (PWM, through 220 ohm)
    Pin 12 -> fan, ONLY through a transistor/MOSFET module (never straight from the pin)
             (moved from pin 3 — pin 3 is now the IR LED)
    GND    -> all grounds connected together

  POWER: a small SG90 servo can run from the Arduino's 5V. Bigger servos (MG996R)
  need their own 5V supply — connect its GND to the Arduino GND. Ask an adult to
  check your wiring before plugging in batteries.

  Commands: LIGHTS ON/OFF, FACE OPEN/CLOSE, REACTOR ON/OFF/PULSE, FAN ON/OFF,
            SUIT UP, POWER DOWN, STATUS,
            REACTOR GLOW (breathes while JARVIS speaks) / REACTOR IDLE (steady dim glow),
            SENSORS, DOOR, BUTTON, IR LEARN, IR SEND p a c (USE_IR), STRIP r g b (USE_STRIP)
*/
// ── OPTIONAL PARTS: remove the // in front of a line to switch that part on ──
// #define USE_DHT     // DHT11/DHT22 temperature + humidity on pin 2  (library: "DHT sensor library" by Adafruit)
// #define USE_IR      // IR receiver on pin 11 + IR LED on pin 3      (library: "IRremote" by Armin Joachimsmeyer)
// #define USE_STRIP   // WS2812 LED strip data on pin 10              (library: "FastLED")
// Always available (no library): light sensor (LDR) on A0, soil sensor on A1,
// door reed switch on pin 4 (to GND), gauntlet push button on pin 7 (to GND).

#include <Servo.h>
#ifdef USE_DHT
  #include <DHT.h>
  DHT dht(2, DHT11);          // change DHT11 to DHT22 if you have a DHT22
#endif
#ifdef USE_IR
  #include <IRremote.hpp>
#endif
#ifdef USE_STRIP
  #include <FastLED.h>
  #define NUM_LEDS 30
  CRGB leds[NUM_LEDS];
#endif

const int PIN_SERVO   = 9;
const int PIN_EYES    = 6;
const int PIN_REACTOR = 5;
const int PIN_FAN     = 12;
const int PIN_DOOR    = 4;
const int PIN_BUTTON  = 7;
bool buttonFlag = false, lastButton = HIGH;

const int FACE_OPEN_ANGLE   = 100;   // adjust these two to fit your helmet
const int FACE_CLOSED_ANGLE = 10;

Servo face;
bool eyesOn = false, reactorOn = false, fanOn = false, faceOpen = false;
bool glowing = false;            // REACTOR GLOW: breathe until REACTOR IDLE
unsigned long glowStart = 0;
String line = "";

void moveFace(int target) {
  int from = face.read();
  int step = (target > from) ? 1 : -1;
  for (int a = from; a != target; a += step) { face.write(a); delay(8); }   // smooth movement
  face.write(target);
}

void setReactor(bool on) { reactorOn = on; analogWrite(PIN_REACTOR, on ? 255 : 0); }

void pulseReactor() {
  for (int r = 0; r < 2; r++) {
    for (int v = 0; v <= 255; v += 5) { analogWrite(PIN_REACTOR, v); delay(6); }
    for (int v = 255; v >= 0; v -= 5) { analogWrite(PIN_REACTOR, v); delay(6); }
  }
  setReactor(true);
}

void handle(String cmd) {
  cmd.trim(); cmd.toUpperCase();
  if      (cmd == "LIGHTS ON")    { eyesOn = true;  digitalWrite(PIN_EYES, HIGH); }
  else if (cmd == "LIGHTS OFF")   { eyesOn = false; digitalWrite(PIN_EYES, LOW); }
  else if (cmd == "FACE OPEN")    { moveFace(FACE_OPEN_ANGLE);   faceOpen = true; }
  else if (cmd == "FACE CLOSE")   { moveFace(FACE_CLOSED_ANGLE); faceOpen = false; }
  else if (cmd == "REACTOR ON")   { setReactor(true); }
  else if (cmd == "REACTOR OFF")  { setReactor(false); }
  else if (cmd == "REACTOR PULSE"){ pulseReactor(); }
  else if (cmd == "REACTOR GLOW") { glowing = true; glowStart = millis(); reactorOn = true; }
  else if (cmd == "REACTOR IDLE") { glowing = false; reactorOn = true; analogWrite(PIN_REACTOR, 60); }
  else if (cmd == "FAN ON")       { fanOn = true;  digitalWrite(PIN_FAN, HIGH); }
  else if (cmd == "FAN OFF")      { fanOn = false; digitalWrite(PIN_FAN, LOW); }
  else if (cmd == "SUIT UP")      { pulseReactor(); moveFace(FACE_CLOSED_ANGLE); faceOpen = false;
                                    delay(200); eyesOn = true; digitalWrite(PIN_EYES, HIGH); }
  else if (cmd == "POWER DOWN")   { digitalWrite(PIN_EYES, LOW); eyesOn = false; setReactor(false);
                                    digitalWrite(PIN_FAN, LOW); fanOn = false; moveFace(FACE_OPEN_ANGLE); faceOpen = true; }
  else if (cmd == "STATUS")       { Serial.print("OK STATUS eyes="); Serial.print(eyesOn);
                                    Serial.print(" reactor="); Serial.print(reactorOn);
                                    Serial.print(" fan="); Serial.print(fanOn);
                                    Serial.print(" face="); Serial.println(faceOpen ? "open" : "closed"); return; }
  else if (cmd == "SENSORS")      { Serial.print("OK SENSORS");
#ifdef USE_DHT
                                    Serial.print(" t="); Serial.print(dht.readTemperature());
                                    Serial.print(" h="); Serial.print(dht.readHumidity());
#endif
                                    Serial.print(" light="); Serial.print(analogRead(A0));
                                    Serial.print(" soil="); Serial.print(analogRead(A1));
                                    Serial.print(" door="); Serial.println(digitalRead(PIN_DOOR) == HIGH ? 1 : 0); return; }
  else if (cmd == "DOOR")         { Serial.print("OK DOOR "); Serial.println(digitalRead(PIN_DOOR) == HIGH ? 1 : 0); return; }
  else if (cmd == "BUTTON")       { Serial.print("OK BUTTON "); Serial.println(buttonFlag ? 1 : 0); buttonFlag = false; return; }
#ifdef USE_IR
  else if (cmd == "IR LEARN")     { unsigned long t0 = millis();
                                    while (millis() - t0 < 8000) {
                                      if (IrReceiver.decode()) {
                                        IRData d = IrReceiver.decodedIRData; IrReceiver.resume();
                                        if (d.protocol != UNKNOWN) {
                                          Serial.print("OK IR "); Serial.print((int)d.protocol); Serial.print(" ");
                                          Serial.print(d.address); Serial.print(" "); Serial.println(d.command); return; }
                                      } }
                                    Serial.println("ERR IR TIMEOUT"); return; }
  else if (cmd.startsWith("IR SEND ")) { int a = 0, b = 0, c = 0;
                                    sscanf(cmd.c_str() + 8, "%d %d %d", &a, &b, &c);
                                    IRData d; d.protocol = (decode_type_t)a; d.address = b; d.command = c; d.flags = 0;
                                    IrSender.write(&d, 1); }
#endif
#ifdef USE_STRIP
  else if (cmd.startsWith("STRIP ")) { int r = 0, g = 0, b = 0;
                                    sscanf(cmd.c_str() + 6, "%d %d %d", &r, &g, &b);
                                    fill_solid(leds, NUM_LEDS, CRGB(r, g, b)); FastLED.show(); }
#endif
  else if (cmd.length() == 0)     { return; }
  else                            { Serial.print("ERR "); Serial.println(cmd); return; }
  Serial.print("OK "); Serial.println(cmd);
}

void setup() {
  Serial.begin(9600);
  pinMode(PIN_EYES, OUTPUT); pinMode(PIN_REACTOR, OUTPUT); pinMode(PIN_FAN, OUTPUT);
  pinMode(PIN_DOOR, INPUT_PULLUP); pinMode(PIN_BUTTON, INPUT_PULLUP);
#ifdef USE_DHT
  dht.begin();
#endif
#ifdef USE_IR
  IrReceiver.begin(11, DISABLE_LED_FEEDBACK);
  IrSender.begin(3);
#endif
#ifdef USE_STRIP
  FastLED.addLeds<WS2812B, 10, GRB>(leds, NUM_LEDS); FastLED.setBrightness(120);
#endif
  face.attach(PIN_SERVO);
  face.write(FACE_OPEN_ANGLE); faceOpen = true;
  digitalWrite(PIN_EYES, HIGH); delay(150); digitalWrite(PIN_EYES, LOW);   // hello blink
}

void loop() {
  bool b = digitalRead(PIN_BUTTON);            // remember a gauntlet-button press until JARVIS asks
  if (b == LOW && lastButton == HIGH) buttonFlag = true;
  lastButton = b;
  if (glowing) {                       // smooth breathing, about 1.2 s per breath
    float t = (millis() - glowStart) / 1200.0 * 6.2832;
    analogWrite(PIN_REACTOR, (int)(150 + 105 * sin(t)));
  }
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { handle(line); line = ""; }
    else if (c != '\r' && line.length() < 40) { line += c; }
  }
}
