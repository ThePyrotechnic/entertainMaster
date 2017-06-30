// pins
#define R 5
#define G 3
#define B 6

// :RRR,GGG,BBB                               <-- set new color
// nnXttCC,XttCC,XttCC,XttCC,XttCC,XttCC... <-- program new loop
#define INPUT_LEN 595 
//nn is number of colors in sequence (max 99)
//X is 'f' (fade) or 'i' (instant)
//tt is time (for 'i': time to wait after switching, in hundreds of millis. For 'f': time between fade steps, in millis)
//CC is a color code (given by position in states[])

//color macros
//       0   RED
//       1   BLU
//       2   GRN
//       3   WHT
//       4   PRP
//       5   PNK
//       6   ONG
//       7   OFF
//       8   LBL - Light Blue
//       9   DBL - Dim Blue
//       10 DWH - Dim White
//       11 MOV - Movie Orange
//       12 DPR - Dim Purple
//       13 DGR - Dim Green
//       14 BRN - Brown
//       15 YLW - Yellow
//       16 DRE - Dim Red
//       17 BLD - Blue, Diabetes
const char* RED = ":255,000,000";
const char* BLU = ":000,000,255";
const char* GRN = ":000,255,000";
const char* WHT = ":255,255,255";
const char* PRP = ":200,000,050";
const char* PNK = ":255,000,255";
const char* ONG = ":255,030,000";
const char* OFF = ":000,000,000";
const char* LBL = ":000,100,255";
const char* DBL = ":000,000,040";
const char* DWH = ":040,040,040";
const char* MOV = ":008,002,000";
const char* DPR = ":025,000,005";
const char* DGR = ":000,025,000";
const char* BRN = ":255,030,004";
const char* YLW = ":255,160,000";
const char* DRE = ":002,000,000";
const char* BLD = ":060,000,255";
// must also add new macros to array
const char* const states[] = {RED, BLU, GRN, WHT, PRP, PNK, ONG, OFF, LBL, DBL, DWH, MOV, DPR, DGR, BRN, YLW, DRE, BLD}; 

//global current light values
byte red = 0;
byte grn = 0;
byte blu = 0;

char in[INPUT_LEN + 1]; //input buffer
bool msg = 0; // whether a message has been received
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
    else if (in[2] == 'f' || in[2] == 'i' || in[2] == 's' || in[2] == 'c') { // requesting a custom program
      // 'f' = fade, 'i' = instant, 's' = single (fade, no loop), 'c' = single (instant, no loop)
      char colsStr[2];
      memcpy(colsStr, &in, 2);
      numCols = (byte)atoi(colsStr);

      char lightData[6]; // size of one light setting (a single 'chunk')

      byte next = 2; // location of next chunk in the 'in' string
      byte single = 0;
      
      while (Serial.available() == 0 && !single) {
        for (int a = 0; a < numCols; a++) {
          memcpy(lightData, &in[next], 5);
          lightData[5] = '\0';
          next += 6;

          parseSplit(lightData);
        }
        next = 2;
        if (in[2] == 's' || in[2] == 'c')
          single = 1;
      }
    }
  }
}

void serialEvent() {
  for (int a = 0; a < INPUT_LEN + 1; a++)
    in[a] = '\0';

  Serial.readBytes(in, INPUT_LEN);
  msg = 1;
}

void parseSplit(char* split) {
  char interval[3];
  memcpy(interval, &split[1], 2);
  interval[2] = '\0';

  char col[3];
  memcpy(col, &split[3],2);
  col[2] = '\0';
  
  if (split[0] == 'f' || split[0] == 's') fade(states[atoi(col)], atoi(interval));
  else stringSet(states[atoi(col)], atoi(interval) * 100); //split[0] should be i // Range of interval * 100 is 100 - 9900 millis
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

