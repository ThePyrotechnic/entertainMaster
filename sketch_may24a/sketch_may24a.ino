// pins
#define R 5
#define G 3
#define B 6

#define INPUT_LEN 496 // :RRR,GGG,BBB                               <-- set new color
//////////////////////// nnXttC,XttC,XttC,XttC,XttC,XttC... <-- program new loop
//nn is number of colors in sequence (max 99)
//X is 'f' (fade) or 'i' (instant)
//tt is time (for 'i': time to wait after switching, in hundreds of millis. For 'f': time between fade steps, in millis)
//C is a color code (given by position in states[])

//color macros
const char* RED = ":255,000,000";
const char* BLU = ":000,000,255";
const char* GRN = ":000,255,000";
const char* WHT = ":255,255,255";
const char* PRP = ":200,000,050";
const char* PNK = ":255,000,255";
const char* ONG = ":255,030,000";
const char* OFF = ":000,000,000";

const char* const states[] = {RED, BLU, GRN, WHT, PRP, PNK, ONG, OFF}; // must add new macros to array

//global current light values
byte red = 0;
byte grn = 0;
byte blu = 0;

char in[INPUT_LEN + 1]; //input buffer
bool msg = 0; // whether a message has been received
bool isPgm = 0; // whether the current message is a program
byte numCols = 0; // number of colors in the user's sent program

void setup() {
  Serial.begin(9600);

  pinMode(R, OUTPUT);
  pinMode(G, OUTPUT);
  pinMode(B, OUTPUT);

  analogWrite(R, red);
  analogWrite(G, grn);
  analogWrite(B, blu);
}

void loop() {
  if (msg) {
    msg = 0;

    if (in[0] == ':') { // requesting a direct color
      stringSet(in, 0);
    }
    else if (in[2] == 'f' || in[2] == 'i') { // requesting a custom program
      // 'f' = fade, 'i' = instant
      char colsStr[2];
      memcpy(colsStr, &in, 2);
      numCols = (byte)atoi(colsStr);

      char lightData[5];

      byte next = 2; // location of next light setting in 'in' string

      while (Serial.available() == 0) {
        for (int a = 0; a < numCols; a++) {
          memcpy(lightData, &in[next], 4);
          lightData[4] = '\0';
          next += 5;

          parseSplit(lightData);
        }
        next = 2;
      }
    }
  }
}

void serialEvent() {
  for (int a = 0; a < INPUT_LEN + 1; a++)
    in[a] = '\0';

  Serial.readBytes(in, INPUT_LEN);
  msg = 1;
  isPgm = 0;
}

void parseSplit(char* split) {
  char interval[3];
  memcpy(interval, &split[1], 2);
  interval[2] = '\0';

  char col = split[3];
  if (split[0] == 'f') fade(states[col - '0'], atoi(interval));
  else stringSet(states[col - '0'], atoi(interval) * 100); //split[0] should be i // Range of interval * 100 is 100 - 9900 millis
}

void fade(char* col, int dur) {
  char split[4];
  split[3] = '\0';
  memcpy(split, &col[1], 3);
  byte newR = atoi(split);

  memcpy(split, &col[5], 3);
  byte newG = atoi(split);

  memcpy(split, &col[9], 3);
  byte newB = atoi(split);
  bool rDone = 0, gDone = 0, bDone = 0;
  bool rNeg = 0, gNeg = 0, bNeg = 0;

  int rDiff = newR - red;
  int gDiff = newG - grn;
  int bDiff = newB - blu;

  int rAdd = 1, gAdd = 1, bAdd = 1;

  if (rDiff < 0) {
    rNeg = 1;
    rDiff = -rDiff;
    rAdd = -1;
  }
  if (gDiff < 0) {
    gNeg = 1;
    gDiff = -gDiff;
    gAdd = -1;
  }
  if (bDiff < 0) {
    bNeg = 1;
    bDiff = -bDiff;
    bAdd = -1;
  }
/*
  Serial.print("New: "); Serial.print(newR); Serial.print('|'); Serial.print(newG); Serial.print('|'); Serial.println(newB);
  Serial.print("Cur: "); Serial.print(red); Serial.print('|'); Serial.print(grn); Serial.print('|'); Serial.println(blu);
  Serial.print("Diff: "); Serial.print(rDiff); Serial.print('|'); Serial.print(gDiff); Serial.print('|'); Serial.println(bDiff);
  Serial.print("Neg: "); Serial.print(rNeg); Serial.print('|'); Serial.print(gNeg); Serial.print('|'); Serial.println(bNeg);
  Serial.print("Add: "); Serial.print(rAdd); Serial.print('|'); Serial.print(gAdd); Serial.print('|'); Serial.println(bAdd);
*/
  while (!(rDone && gDone && bDone)) {
    if (red == newR) rDone = 1;
    if (grn == newG) gDone = 1;
    if (blu == newB) bDone = 1;
    if (!rDone) analogWrite(R, red = red + rAdd);
    if (!gDone) analogWrite(G, grn = grn + gAdd);
    if (!bDone) analogWrite(B, blu = blu + bAdd);
    delay(dur);
  }
}

void stringSet(char* str, int dur) {
  char split[4];
  split[3] = '\0';
  memcpy(split, &str[1], 3);
  byte r = (byte)atoi(split);

  memcpy(split, &str[5], 3);
  byte g = (byte)atoi(split);

  memcpy(split, &str[9], 3);
  byte b = (byte)atoi(split);
  set(r, g, b, dur);
}

void set(byte r, byte g, byte b, int dur) {
  red = r;
  grn = g;
  blu = b;

  analogWrite(R, r);
  analogWrite(G, g);
  analogWrite(B, b);
  if (dur > 0) delay(dur);
}

