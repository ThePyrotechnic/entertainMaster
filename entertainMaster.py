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
from __future__ import print_function
from bs4 import BeautifulSoup
import re
import sys
import serial
import time
import requests
import datetime

# globals
arduino = None
esb_color = None
sun_data = None
cur_weather = None
colors = {}
refresh_t = datetime.datetime.today()
priorities = {"sun": 0, "weather": 1}  # 0 - 5. 4 is highest normal prio, 5 is special prio, 0 is default. (-1 is therefore ignored)


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def init():
    global esb_color, arduino, sun_data, cur_weather
    # hog the Arduino
    arduino = serial.Serial('COM4', 9600, timeout=0.2)
    time.sleep(2)

    # arduino.write(b'10f051,i501,i013,f021,i013,f021,i301,1023,f021,i601')

    # populate the colors Dictionary
    with open('colors.txt', encoding='UTF-8') as s:
        for line in s:
            if line[0] == '*':
                continue
            line = line.split(',')
            colors[line[0].lower()] = (line[1], line[2], line[3].rstrip('\n'))

    # gather initial event data
    dat = fetch_weather_data()
    sun_data = (dat[0], dat[1])
    cur_weather = dat[2]

    esb_color = fetch_esb_color()

    # start decision engine
    event_master()

    print("done")


def event_master():
    global priorities

    while True:
        time.sleep(5)  # TODO change to 1 hour
        update_event_data()
        update_priorities()
        next_event = max(priorities, key=priorities.get)
        globals()[next_event + "_event"]()


def sun_event():
    global sun_data
    # RESUME HERE


def weather_event():
    # TODO
    print("Weather not implemented")


def update_priorities():
    global priorities
    # TODO remember to add any new event priorities here

    priorities["weather"] = get_weather_priority()


def update_event_data():
    global refresh_t, esb_color, sun_data, cur_weather
    # TODO remember to add any new events here

    t_since_last = datetime.datetime.today() - refresh_t
    print(str(t_since_last))
    if t_since_last > datetime.timedelta(seconds=25):  # TODO change to 1 day
        esb_color = fetch_esb_color()
        refresh_t = datetime.datetime.today()

    dat = fetch_weather_data()
    sun_data = (dat[0], dat[1])
    cur_weather = dat[2]


def get_weather_priority():
    global cur_weather

    if "thunder" in cur_weather.lower():
        return 4
    if "rain" in cur_weather.lower():
        return 2
    if "snow" in cur_weather.lower():
        return 3
    else:
        return -1


def fetch_esb_color():
    res = requests.get("http://www.esbnyc.com/explore/tower-lights/calendar")
    if res.status_code != 200:
        eprint("unable to connect to www.esbnyc.com: " + res.status_code)
        return "white"

    c = res.content
    data = BeautifulSoup(c, "html.parser")
    flavor_str = str(data.find("p", "lighting-desc").string).lstrip("\n ")
    flavor_str = flavor_str.split(" ")
    for s in flavor_str:
        if s in colors:
            return colors[s]
    return "white"


def fetch_weather_data():
    res = requests.get("https://www.wunderground.com/cgi-bin/findweather/getForecast?query=Whittier+Oaks%2C+NJ")
    if res.status_code != 200:
        eprint("unable to connect to www.wunderground.com: " + res.status_code)
        return None

    c = res.content
    data = BeautifulSoup(c, "html.parser")
    phrase_now = str(data.find("div", id="curCond").contents[0].contents[0])

    # TODO make ampm more robust
    rise_t_str = data.find("span", id="cc-sun-rise")
    ampm = rise_t_str.parent.contents[2]
    rise_t_str = str(rise_t_str.contents[0]) + ' ' + str(ampm.contents[0])

    set_t_str = data.find("span", id="cc-sun-set")
    ampm = set_t_str.parent.contents[2]
    set_t_str = str(set_t_str.contents[0]) + ' ' + str(ampm.contents[0])

    rise_t = re.split(r'[: ]+', rise_t_str)
    set_t = re.split(r'[: ]+', set_t_str)

    for t in (rise_t, set_t):
        if t[2].lower() == 'pm':
            t[0] = int(t[0]) + 12

    rise_t = datetime.datetime.combine(datetime.date.today(), datetime.time(int(rise_t[0]), int(rise_t[1])))
    set_t = datetime.datetime.combine(datetime.date.today(), datetime.time(int(set_t[0]), int(set_t[1])))

    return rise_t, set_t, phrase_now


init()
