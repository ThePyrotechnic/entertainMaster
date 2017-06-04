# :RRR,GGG,BBB                             <-- set new color
# nnXttCC,XttCC,XttCC,XttCC,XttCC,XttCC... <-- program new loop
#   nn is number of colors in sequence (max 99)
#   X is 'f' (fade) or 'i' (instant)
#   tt is time (for 'i': time to wait after switching, in hundreds of millis. For 'f': time between fade steps, in millis)
#   CC is a color code (given by position in states[])
#   Loops repeat until another sequence is read in
#   COLOR TABLE:
#       0   RED
#       1   BLU
#       2   GRN
#       3   WHT
#       4   PRP
#       5   PNK
#       6   ONG
#       7   OFF
#       8   LBL - Light Blue
#       9   DBL - Dim Blue
#       10 DWH - Dim White
# ex:
# (purple) :200,000,050
# (thunderstorm) 10f051,i501,i013,f021,i013,f021,i301,1023,f021,i601
from __future__ import print_function
from bs4 import BeautifulSoup
from collections import deque
import re
import sys
import serial
import time
import requests
import datetime
import threading
import random
import math


class Color:  # convenience class for difference of colors
    def __init__(self, r, g, b):
        self.r = r
        self.g = g
        self.b = b

    def __str__(self):
        return 'r: ' + str(self.r) + ' g: ' + str(self.g) + ' b: ' + str(self.b)

    def to_bytes(self):
        return bytes(':' + str(self.r).zfill(3) + ',' + str(self.g).zfill(3) + ',' + str(self.b).zfill(3), encoding='ASCII')

    @classmethod
    def from_tuple(cls, rgb: tuple):
        r = rgb[0]
        g = rgb[1]
        b = rgb[2]
        return cls(r, g, b)

    @classmethod
    def from_list(cls, rgb: list):
        r = rgb[0]
        g = rgb[1]
        b = rgb[2]
        return cls(r, g, b)

    def __add__(self, o):  # add and sub methods will over/underflow; meant to be used only when adding fractional color diffs (see the sun rise/set)
        return Color(self.r + o.r, self.g + o.g, self.b + o.b)

    def __sub__(self, o):
        return Color(self.r - o.r, self.g - o.g, self.b - o.b)

    def int_mul(self, o):
        return Color(self.r * o, self.g * o, self.b * o)

    def int_div(self, o):
        if self. r < 0:
            r = int(math.ceil(self.r / o))
        else:
            r = self.r // o
            
        if self. g < 0:
            g = int(math.ceil(self.g / o))
        else:
            g = self.g // o
            
        if self. b < 0:
            b = int(math.ceil(self.b / o))
        else:
            b = self.b // o
            
        return Color(r, g, b)


# globals TODO describe variable structure
arduino = None
bus_lock = threading.Lock()
colors = {}

esb_color = None

sun_data = None
sun_keyframes = None
is_init = True
sun_colors = {'rise': Color(255, 10, 0), 'mid': Color(255, 255, 255), 'set': None}

cur_weather = None
weather_refresh_t = datetime.datetime.today()

priorities = {"sun": 0, "weather": 1}  # 0 - 5. 4 is highest normal prio, 5 is special prio, 0 is default. (-1 is ignored)

EVENT_THREAD_INTERVAL = 5  # time, in seconds, for the master timer to wait before spawning a new event cycle
WEATHER_UPDATE_INTERVAL = 15  # minimum time, in seconds, between weather update requests


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def init():
    global esb_color, arduino, sun_data, cur_weather, sun_keyframes
    # hog the Arduino
    try:
        arduino = serial.Serial('COM4', 9600, timeout=0.2)
    except serial.SerialException as e:
        eprint("unable to connect to arduino. Information: ")
        eprint('\t' + str(e))
        exit(0)
    time.sleep(2)

    # populate the colors Dictionary
    with open('colors.txt', encoding='UTF-8') as s:
        for line in s:
            if line[0] == '*':
                continue
            line = line.split(',')
            colors[line[0].lower()] = (int(line[1]), int(line[2]), int(line[3].rstrip('\n')))

    # gather initial and once-per-day event data
    # order may matter!
    sun_colors['set'] = esb_color = fetch_esb_color()

    dat = fetch_weather_data()
    sun_data = (dat[0], dat[1])
    cur_weather = dat[2]
    sun_keyframes = generate_sun_keys()

    debug_print()
    # cur_weather = 'SNOWING'  # TODO Comment this when not testing weather
    # start decision engine
    master_timer()

    print("done")


def master_timer():
    global EVENT_THREAD_INTERVAL
    while True:
        t = threading.Thread(target=event_master)
        t.start()

        time.sleep(EVENT_THREAD_INTERVAL)  # TODO change to 30 min


def event_master():
    global priorities

    print('Choosing next event...')
    update_event_data()
    update_priorities()
    next_event = max(priorities, key=priorities.get)
    globals()[next_event + "_event"]()


def update_priorities():
    global priorities
    # TODO remember to add any new event priorities here

    priorities["weather"] = get_weather_priority()


def update_event_data():
    global weather_refresh_t, cur_weather, WEATHER_UPDATE_INTERVAL
    # TODO remember to add any new events here
    weather_refresh = datetime.timedelta(seconds=WEATHER_UPDATE_INTERVAL)  # TODO change to minutes

    t_since_last_weather = datetime.datetime.today() - weather_refresh_t
    if t_since_last_weather > weather_refresh:
        print('Refreshing weather...')
        cur_weather = fetch_weather_data()  # TODO Uncomment this when not testing weather
        weather_refresh_t = datetime.datetime.today()


def sun_event():
    global sun_keyframes, arduino

    print('\tFiring sun_event')
    if sun_keyframes:
        color = None
        # this check allows the sun color to change at a different frequency than the global event update frequency
        # and the loop allows the sun event to skip events to find the current sun keyframe
        while True:
            data = sun_keyframes[0]
            time_req = data[0]
            print("Current time:" + str(datetime.datetime.today()) + ". This color's time requirement: " + str(time_req) + ". (" + str(data[1]) + ")")
            if datetime.datetime.today() >= time_req:
                sun_keyframes.popleft()
                color = data[1]
            else:
                break

        if color is not None:
            print("Passed " + str(color))
            send_color_str(color.to_bytes())
    # else the queue is empty, do nothing


def weather_event():
    global cur_weather

    print('\tFiring weather_event')
    if "thunder" in cur_weather.lower():
        # chunks:
        # flash - i0103,f0201
        # long wait - f0201,i5001
        # short wait - f0201,i2501
        chunks = (b'f0201,i2501', b'i0103,f0201')
        str_to_send = b'32f0201,i5001'  # remember that the string must start with the expected number of colors
        for _ in range(15):
            str_to_send += b',' + random.choice(chunks)
        send_color_str(str_to_send)

    if "rain" in cur_weather.lower():
        # chunks:
        # long light blue - f0508,i5008
        # long blue - f0501,i5001
        # long dim blue - f0509,i5009
        # short light blue - f0508,i2508
        # short blue - f0501,i2501
        # short dim blue - f0509,i2509
        chunks = (b'f0508,i5008', b'f0501,i5001', b'f0508,i2508', b'f0501,i2501', b'f0501,i2501', b'f0509,i2509')
        str_to_send = b'32f0208,i5008'
        for _ in range(15):
            str_to_send += b',' + random.choice(chunks)
        send_color_str(str_to_send)

    if "snow" in cur_weather.lower():
        # chunks:
        # flash - i0110,f0303
        # long wait - f0203,i5003
        # short wait - f0203,i2503
        chunks = (b'f0203,i2503', b'i0110,f0303')
        str_to_send = b'32f0203,i5003'
        for _ in range(15):
            str_to_send += b',' + random.choice(chunks)
        send_color_str(str_to_send)

    else:
        eprint("Unknown weather event: " + cur_weather)


def generate_sun_keys():
    global sun_data, sun_colors, esb_color

    keyframes = deque()
    sun_diff = sun_data[1] - sun_data[0]

    # One key per hour from rise until set
    hours_diff = sun_diff.seconds // 3600
    if sun_diff.seconds % 3600 // 60 > 30:  # round up to nearest hour
        hours_diff += 1

    rise_key_count = hours_diff // 2
    set_key_count = hours_diff // 2
    if rise_key_count * 2 != hours_diff:  # correct int division
        rise_key_count += 1

    c_diff = sun_colors['mid'] - sun_colors['rise']
    c_diff = c_diff.int_div(rise_key_count - 1)

    for a in range(rise_key_count - 1):
        hour_req = sun_data[0] + datetime.timedelta(hours=a)  # one keyframe per hour, starting at sunrise
        keyframes.append((hour_req, sun_colors['rise'] + c_diff.int_mul(a)))
    hour_req = sun_data[0] + datetime.timedelta(hours=rise_key_count - 1)
    keyframes.append((hour_req, sun_colors['mid']))  # manually set last keyframe in order to actually hit the desired end color

    if sun_colors['set'] is None:
        sun_colors['set'] = random_color(dim=True)

    c_diff = sun_colors['set'] - sun_colors['mid']
    c_diff = c_diff.int_div(set_key_count - 1)

    for a in range(set_key_count - 1):
        hour_req = sun_data[0] + datetime.timedelta(hours=rise_key_count + a)
        keyframes.append((hour_req, sun_colors['mid'] + c_diff.int_mul(a)))
    hour_req = sun_data[0] + datetime.timedelta(hours=rise_key_count + set_key_count - 1)
    keyframes.append((hour_req, sun_colors['set']))

    return keyframes


def random_color(from_table: bool = False, bright: bool = False, dim: bool = False):

    if from_table:  # TODO add more colors to the table
        color_table = (
            Color(255, 0, 0),
            Color(0, 255, 0),
            Color(0, 0, 255)
        )
        return random.choice(color_table)

    r_color = [random.randint(1, 255), random.randint(1, 255), random.randint(1, 255)]
    if bright:
        if all(a < 200 for a in r_color):  # if all colors are not bright (< 200), make one color bright
            r_color[random.randint(0, 2)] = 200
        return Color.from_list(r_color)

    r_color = [random.randint(1, 255), random.randint(1, 255), random.randint(1, 255)]
    if dim:
        for a, val in enumerate(r_color):  # make sure no colors are too bright, and turn off one color
            if val > 150:
                r_color[a] = random.randint(1, 63)
        r_color[random.randint(0, 2)] = 0
    return Color.from_list(r_color)


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
    try:
        res = requests.get("http://www.esbnyc.com/explore/tower-lights/calendar")
    except requests.exceptions.RequestException as e:  # This is the correct syntax
        eprint("unable to connect to www.esbnyc.com. Information: ")
        eprint('\t' + str(e))

    c = res.content
    data = BeautifulSoup(c, "html.parser")
    flavor_str = str(data.find("p", "lighting-desc").string).lstrip("\n ")
    flavor_str = flavor_str.split(" ")
    for s in flavor_str:
        if s.lower() in colors:
            return Color.from_tuple(colors[s.lower()])
    return None


def fetch_weather_data():
    global is_init

    try:
        res = requests.get("https://www.wunderground.com/cgi-bin/findweather/getForecast?query=Whittier+Oaks%2C+NJ")
    except requests.exceptions.RequestException as e:  # This is the correct syntax
        eprint("unable to connect to www.wunderground.com. Information: ")
        eprint('\t' + str(e))
        return None

    c = res.content
    data = BeautifulSoup(c, "html.parser")
    phrase_now = str(data.find("div", id="curCond").contents[0].contents[0])

    if is_init:  # On first run also gather sun data for the day
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

        is_init = False
        return rise_t, set_t, phrase_now
    return phrase_now


def send_color_str(col_string: bytes):
    global bus_lock, arduino
    print('sending ' + str(col_string))
    with bus_lock:
        arduino.write(col_string)


def debug_print():
    global esb_color, sun_data, sun_keyframes, is_init, sun_colors, cur_weather, weather_refresh_t, priorities
    print('------DEBUG OUT------')
    print('esb_color: ' + str(esb_color))
    print('sun_data[0] (sunrise): ' + str(sun_data[0]))
    print('sun_data[1] (sunset): ' + str(sun_data[1]))
    print('sun_keyframes: ' + str(sun_keyframes))
    print('sun_colors[\'set\']: ' + str(sun_colors['set']))
    print('cur_weather: ' + cur_weather + '(is_init: ' + str(is_init) + ')')
    print('weather_refresh_t: ' + str(weather_refresh_t))
    print('priorities: ' + str(priorities))
    print('---------------------------')


init()
