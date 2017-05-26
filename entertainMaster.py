# :RRR,GGG,BBB                             <-- set new color
# nnXttC,XttC,XttC,XttC,XttC,XttC... <-- program new loop
#   nn is number of colors in sequence (max 99)
#   X is 'f' (fade) or 'i' (instant)
#   tt is time (for 'i': time to wait after switching, in hundreds of millis. For 'f': time between fade steps, in millis)
#   C is a color code (given by position in states[])
#       0 RED
#       1 BLU
#       2 GRN
#       3 WHT
#       4 PRP
#       5 PNK
#       6 ONG
#       7 OFF
# ex:
# (purple) :200,000,050
# (thunderstorm) 10f051,i501,i013,f021,i013,f021,i301,1023,f021,i601

import serial
import time
import requests
from bs4 import BeautifulSoup

arduino = None
colors = {}


def init():
    # hog the Arduino
    arduino = serial.Serial('COM4', 9600, timeout=0.2)
    time.sleep(2)

    # populate the colors Dictionary
    with open('colors.txt', encoding='UTF-8') as s:
        for line in s:
            if line[0] == '*':
                continue
            line = line.split(',')
            colors[line[0]] = (line[1], line[2], line[3].rstrip('\n'))

    # gather initial event data
    # TODO sunrise/set
    # TODO weather
    esb_color = fetch_esb_color()
    # start decision engine

    print("done")


def fetch_esb_color():
    res = requests.get("http://www.esbnyc.com/explore/tower-lights/calendar")
    if res.status_code != 200:
        return None
    c = res.content
    data = BeautifulSoup(c)
    flavor_str = str(data.find("p", "lighting-desc").string).lstrip("\n ")
    flavor_str = flavor_str.split(" ")
    for s in flavor_str:
        if s in colors:
            return colors[s]
    return None

init()
