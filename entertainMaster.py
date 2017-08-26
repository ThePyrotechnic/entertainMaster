"""
The program is expected to be (re)started each day before sunrise

ARDUINO MESSAGE FORMAT:
:RRR,GGG,BBB                             <-- set new color
nnXttCC,XttCC,XttCC,XttCC,XttCC,XttCC... <-- program new loop
  nn is number of colors in sequence (max 99)
  X is 'f' (fade) or 'i' (instant) or 's' (fade, no loop) or 'c' (instant, no loop)
  tt is time (for 'i': time to wait after switching, in hundreds of millis. For 'f': time between fade steps, in millis)
  CC is a color code (given by position in states[])
  Loops repeat until another sequence is read in
  COLOR TABLE:
      0  RED
      1  BLU
      2  GRN
      3  WHT
      4  PRP
      5  PNK
      6  ONG
      7  OFF
      8  LBL - Light Blue
      9  DBL - Dim Blue
      10 DWH - Dim White
      11 MOV - Movie Orange
      12 DPR - Dim Purple
      13 DGR - Dim Green
      14 BRN - Brown
      15 YLW - Yellow
      16 DRE - Dim Red
      17 BLD - Blue, Diabetes
      18 DPN - Dim Pink
ex:
(purple) :200,000,050
(thunderstorm) 10f0501,i5001,i0103,f0201,i0103,f0201,i3001,10203,f0201,i6001
"""
from __future__ import print_function

from collections import deque
import datetime
import math
from os import path
import random
import re
import socket
import ssl
from string import punctuation
import sys
import threading
import time

import errno
from bs4 import BeautifulSoup
import requests
import serial
import tweepy
from tweepy import OAuthHandler


class Color:
    """
    Convenience class for the representation of colors.
    """
    __slots__ = ('r', 'g', 'b')

    def __init__(self, r: int, g: int, b: int):
        for x in (r, g, b):
            assert 0 <= x <= 0xFF, 'All fields must be between 0 and 255'
        self.r = r
        self.g = g
        self.b = b

    def __str__(self):
        return 'r: %d g: %d b: %d' % (self.r, self.g, self.b)

    def __bytes__(self):
        return b':%03d,%03d,%03d' % (self.r, self.g, self.b)

    def __eq__(self, other):
        if self is other:
            return True
        elif isinstance(other, Color):
            return self.r == other.r and self.g == other.g and self.b == other.b
        elif isinstance(other, int):
            return int(self) == other
        return NotImplemented

    def __int__(self):
        return 0x010000 * self.r + 0x0100 * self.g + self.b

    # meant to be used only when adding fractional color diffs 
    # See also: sun rise/set
    def __add__(self, other):
        return Color(min(self.r + other.r, 0xFF),
                     min(self.g + other.g, 0xFF),
                     min(self.b + other.b, 0xFF))

    def __sub__(self, other):
        return Color(max(self.r - other.r, 0),
                     max(self.g - other.g, 0),
                     max(self.b - other.b, 0))

    def __mul__(self, other: int):
        if other < 0:
            raise ValueError('Cannot multiply a Color by a negative number.')
        return Color(min(self.r * other, 255),
                     min(self.g * other, 255),
                     min(self.b * other, 255))

    def __truediv__(self, other: int):
        if other < 0:
            raise ValueError('Cannot divide a Color by a negative number.')
        return Color(self.r // other, self.g // other, self.b // other)


arduino = None
bus_lock = None
interrupt_lock = None
interrupt_active = False
colors = {}
cur_event = None
esb_color = None
sun_data = None
sun_keyframes = None
sun_key_count = 0
is_init = True
sun_colors = None
last_sun_color = None
cur_weather = None
weather_refresh_t = None
cal_event_color_str = None
team_won = {'rangers': False, 'steelers': False}
DJI_difference = None
fetched_stocks = False
stocks_color_str = None
priorities = None

# constants
WHITE = Color(0xFF, 0xFF, 0xFF)
EVENT_THREAD_INTERVAL = 5  # time, in minutes, for the master timer to wait before spawning a new event cycle
TEAM_COLORS = {
    'rangers': b'04f1000,i5000,f1001,i5001',
    'steelers': b'04f1015,i5015,f0207,i5007',
}
WEATHER_UPDATE_INTERVAL = 15  # minimum time, in minutes, between weather update requests


def eprint(*args, **kwargs):
    """
    Print to stderr
    """
    print(*args, file=sys.stderr, **kwargs)


def init():
    global esb_color, arduino, sun_data, cur_weather, sun_keyframes, fetched_stocks, bus_lock, interrupt_lock, \
        interrupt_active, colors, cur_event, esb_color, sun_data, sun_keyframes, sun_key_count, is_init, sun_colors, \
        last_sun_color, cur_weather, weather_refresh_t, cal_event_color_str, DJI_difference, \
        fetched_stocks, stocks_color_str, priorities

    # intiialize globals
    # TODO describe variable structure
    arduino = None
    bus_lock = threading.Lock()
    interrupt_lock = threading.Lock()
    interrupt_active = False
    colors = {}
    cur_event = None

    esb_color = None

    # Default sunrise/set times, just in case
    sun_data = (datetime.datetime.combine(datetime.date.today(), datetime.time(hour=6)),
                datetime.datetime.combine(datetime.date.today(), datetime.time(hour=20, minute=30)))
    sun_keyframes = None
    sun_key_count = 0
    is_init = True
    sun_colors = {'rise': Color(255, 10, 0),
                  'mid': Color(255, 255, 255),
                  'set': None}
    last_sun_color = (Color(255, 10, 0), 0)

    cur_weather = None
    weather_refresh_t = datetime.datetime.today()

    cal_event_color_str = None

    DJI_difference = None
    fetched_stocks = False
    stocks_color_str = None

    # 0 - 6. 5 is highest normal prio, 6 is special prio, 0 is default. (-1 is ignored)
    priorities = {'sun': 0,
                  'weather': -1,
                  'calendar': -1,
                  'sports': -1,
                  'stocks': -1,
                  'sleep': -1}

    # hog the Arduino
    try:
        arduino = serial.Serial('COM4', 9600, timeout=0.2)
        # eprint('Running without an arduino connection. Nothing will happen!')
    except serial.SerialException as e:
        eprint('unable to connect to arduino. Information: ')
        eprint('\t', e, sep='')
        exit(1)
    time.sleep(2)

    # gather initial and once-per-day event data
    # order may matter!
    sun_colors['set'] = esb_color = fetch_esb_color()

    dat = fetch_weather_data()
    if dat is not None:
        sun_data = (dat[0], dat[1])
        cur_weather = dat[2]
    print('Generating sun keyframes...')
    sun_keyframes = generate_sun_keys()

    # read holidays.txt for an event
    parse_calendar_event()
    print('Parsing calendar events...')

    # read tweets for sports information
    crawl_twitter_accounts()
    print('Crawling Twitter...')

    # get stock data if necessary
    if datetime.datetime.today().hour >= 16:
        print('Fetching stock data...')
        fetch_stock_data()
        fetched_stocks = True  # only fetch once

    # resume interrupts if necessary
    resume_interrupt()

    # cur_weather = 'SNOWING'  # TODO Comment this when not testing weather

    debug_print()

    # start decision engine
    master_timer()

    print('done')


def master_timer():
    global EVENT_THREAD_INTERVAL, interrupt_lock, interrupt_active, arduino
    while True:
        with interrupt_lock:
            if not interrupt_active:
                # Place a breakpoint here to manually allow threads through while debugging
                t = threading.Thread(target=event_master, daemon=True)
                t.start()
        if datetime.datetime.now().hour == 4:
            return
        else:
            time.sleep(EVENT_THREAD_INTERVAL * 60)  # change to seconds when debugging


def event_master():
    global priorities

    print('Choosing next event...')
    update_event_data()
    update_priorities()
    next_event = max(priorities, key=priorities.get)
    print('event_master chose', next_event)
    globals()[next_event + '_event']()


def update_priorities():
    global priorities, fetched_stocks
    # TODO remember to add any changing event priorities here

    priorities['sleep'] = get_sleep_priority()
    priorities['weather'] = get_weather_priority()
    if fetched_stocks:
        priorities['stocks'] = get_stocks_priority()


def update_event_data():
    global weather_refresh_t, cur_weather, fetched_stocks, WEATHER_UPDATE_INTERVAL
    # TODO remember to add any new events here
    weather_refresh = datetime.timedelta(seconds=WEATHER_UPDATE_INTERVAL * 60)  # change to seconds when debugging

    today = datetime.datetime.today()

    time_since_last_weather = today - weather_refresh_t
    if time_since_last_weather > weather_refresh:
        print('Refreshing weather...')
        cur_weather = fetch_weather_data()
        weather_refresh_t = datetime.datetime.today()

    nasdaq_close = four_pm = 16
    if not fetched_stocks and today.hour >= nasdaq_close:
        fetch_stock_data()
        fetched_stocks = True  # only fetch once


# Could possibly be multithreaded, but with a 15 minute main loop refresh time, it isn't really competing for resources.
def pc_listener():
    use_ssl = False
    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)  # 30 seconds. Must be done this way to avoid default OS timeout
        if use_ssl:
            context = ssl.create_default_context()
            context.check_hostname = True
            messenger_socket = context.wrap_socket(sock, server_hostname='www.michaelmanis.com')
        else:
            messenger_socket = sock
        print('Starting server connection')
        with messenger_socket:
            connected = False
            while not connected:
                try:
                    messenger_socket.connect(('www.michaelmanis.com', 8493))
                except OSError:
                    pass
                else:
                    connected = True
                    print('Connected to remote server')

            try:
                msg = messenger_socket.recv(1024)
            except socket.timeout:
                print("No message was received before timeout")
            except OSError as e:
                if e.errno == 10054:
                    print('The connection was closed by the server')
            else:
                accept_info(msg, messenger_socket)
                try:
                    messenger_socket.shutdown(socket.SHUT_RDWR)
                    print('Closed the socket')
                except socket.error as e:
                    if e.errno != errno.ENOTCONN:
                        raise e
                    else:
                        print('The connection was closed by the server')
            #     ct = threading.Thread(target=accept_info, args=[client_socket])  # Not a daemon since it writes to a file
            #     ct.run()


def accept_info(msg, messenger_socket):
    global cur_event
    print('Received server message: ')
    print('\t', msg, sep='')

    status_update = b'1'
    custom_color = b'c'
    custom_string = b'v'
    
    if msg.startswith(status_update):
        print('cur_event:', cur_event)
        messenger_socket.sendall(cur_event.encode('UTF-8'))

    elif msg.startswith(custom_color):
        if len(msg) == 13:
            print('received custom color:', msg)
            fire_interrupt(msg)
            messenger_socket.sendall(cur_event.encode('UTF-8'))
        else:
            print('Invalid custom color:', msg)

    elif msg.startswith(custom_string):
        if len(msg) >= 8:  # vnnXttCC is the minimum length. max length is 595 (99 chunks minus 1 comma plus 'nn')
            print('received custom string:', msg)
            fire_interrupt(msg)
            messenger_socket.sendall(cur_event.encode('UTF-8'))
        else:
            print('Invalid custom string:', msg)

    else:  # must be a miscellaneous interrupt
        response = fire_interrupt(msg)
        messenger_socket.sendall(response.encode('UTF-8'))
        print('sent event:', response)


def fire_interrupt(signal, resume=False):
    """
    BYTE CODES:
    - m = movie mode
    - z = sleep mode
    - x = cancel interrupt
    - o = off
    - s = music mode (unimplemented)
    - r = relax mode (unimplemented)
    - c = custom color
    - v = custom string
    """
    global interrupt_lock, interrupt_active, cur_event

    with interrupt_lock:
        interrupt_active = signal != b'x'
    
    if signal == b'x':
        if interrupt_active:
            open('interrupt.temp', 'w').close()
            cur_event = None
            event_master()

        return cur_event

    else:
        if signal == b'm':
            if resume:
                send_color_str(b':008,002,000')  # this is different because if it gets resumed then the program should not re-animate the 'fade-in'
            else:
                send_color_str(b'03s0203,f0206,f0811')
            cur_event = 'movie'

        elif signal == b'z':
            if resume:
                send_color_str(b':002,000,000')
            else:
                send_color_str(b'01s0416')
            cur_event = 'sleep'
        # TODO Add unimplemented events
        elif signal == b'r':  # relax mode
            print(NotImplemented)
            cur_event = 'relax'

        elif signal == b's':  # song mode
            print(NotImplemented)
            # send_color_str(signal)  # implement on arduino
            cur_event = 'music'

        elif signal.startswith(b'c'):  # (c) custom color
            send_color_str(signal[1:])
            cur_event = signal.decode()

        elif signal.startswith(b'v'):  # (v) custom string
            send_color_str(signal[1:])
            cur_event = 'string'

        elif signal == b'o':
            send_color_str(b':000,000,000')
            cur_event = 'off'

    # saves interrupt state to be resumed if program restarts
    # (i.e if restarts at midnight during a movie)
    with open('interrupt.temp', 'wb') as interrupt_state:
        interrupt_state.write(signal)
    return cur_event


def resume_interrupt():
    if path.isfile('interrupt.temp'):
        with open('interrupt.temp', 'rb') as interrupt_state:
            signal = interrupt_state.read()
            if signal:
                fire_interrupt(signal, resume=True)


def try_sleep_event():
    global cur_event

    sleep_time = 0
    wake_time = 6

    if sleep_time <= datetime.datetime.now().hour <= wake_time:
        fire_interrupt(b'zz')


def sun_event():
    global sun_keyframes, last_sun_color, cur_event, sun_key_count

    print('\tFiring sun_event')
    color = None
    # this check allows the sun color to change at a different frequency than the global event update frequency
    # and the loop allows the sun event to skip events to find the current sun keyframe
    data = None
    now = datetime.datetime.now()
    while sun_keyframes:
        data = sun_keyframes[0]
        time_req = data[0]
        if now >= time_req:
            sun_keyframes.popleft()
            color = data[1]
        else:
            break

    if color is not None:
        keyframe_index = data[2]
        last_sun_color = (color, keyframe_index)

        if keyframe_index <= sun_key_count/4:  # if keyframe is within the first quarter of keyframes
            cur_event = 'sunrise'
        elif keyframe_index < sun_key_count * 0.75:  # if keyframe is above first quarter but below last quarter
            cur_event = 'midday'
        else:  # if keyframe is within last quarter
            if keyframe_index == sun_key_count - 1:
                cur_event = 'sundown'
            else:
                cur_event = 'sunset'
        send_color_str(bytes(color))
    else:
        col = last_sun_color[0]
        ind = last_sun_color[1]

        if ind <= sun_key_count/4:
            cur_event = 'sunrise'
        elif ind <= sun_key_count * 0.75:
            cur_event = 'midday'
        else:
            if ind == sun_key_count - 1:
                cur_event = 'sundown'
            else:
                cur_event = 'sunset'
        send_color_str(bytes(col))


def weather_event():
    global cur_weather, cur_event
    handled = False  # Helps find new weather events

    print('\tFiring weather_event')
    if cur_weather is not None:
        if 'thunder' in cur_weather.lower():
            # chunks:
            # flash - i0103,f0201
            # long wait - f0201,i5001
            # short wait - f0201,i2501
            chunks = (b'f0201,i2501', b'i0103,f0201')
            str_to_send = b'32f0201,i5001'  # remember that the string must start with the expected number of colors
            for _ in range(15):
                str_to_send += b',' + random.choice(chunks)
            send_color_str(str_to_send)
            cur_event = 'thunder'
            handled = True

        if 'rain' in cur_weather.lower():
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
            cur_event = 'rain'
            handled = True

        if 'snow' in cur_weather.lower():
            # chunks:
            # flash - i0110,f0303
            # long wait - f0203,i5003
            # short wait - f0203,i2503
            chunks = (b'f0203,i2503', b'i0110,f0303')
            str_to_send = b'32f0203,i5003'
            for _ in range(15):
                str_to_send += b',' + random.choice(chunks)
            send_color_str(str_to_send)
            cur_event = 'snow'
            handled = True

    if not handled:
        eprint('Unknown weather event: ' + cur_weather)


def calendar_event():
    global cal_event_color_str, cur_event
    print('\tFiring calendar_event')

    if cur_event != 'calendar':  # don't resend the string needlessly
        send_color_str(cal_event_color_str)
        cur_event = 'calendar'


def sports_event():
    global cur_event
    print('\tFiring sports_event')

    # ordered by preference. This list is read left to right so that if multiple teams win, the preferred team is chosen
    # TODO make this a global so it can be modified in UI if desired
    for team, won in team_won.items():
        if won:
            team = team.lower()
            send_color_str(TEAM_COLORS[team])
            cur_event = team
            break
    else:
        eprint('Sports event chosen, but no team won a game last night')
        return


def stocks_event():
    global stocks_color_str, cur_event
    print('\tFiring stocks_event')

    if stocks_color_str is not None:
        send_color_str(stocks_color_str)
    else:
        eprint('Stocks event chosen, but there is no stock color set')
    cur_event = 'stocks'


def sleep_event():
    global cur_event
    print('\tFiring sleep_event')

    send_color_str(b'01s0416')
    cur_event = 'sleep'


def generate_sun_keys():
    global sun_data, sun_colors, sun_key_count

    keyframes = deque()
    sun_diff = sun_data[1] - sun_data[0]

    # One key per hour from rise until set
    sun_key_count = hours_diff = sun_diff.seconds // 3600
    if sun_diff.seconds % 3600 // 60 > 30:  # round up to nearest hour
        hours_diff += 1

    rise_key_count = math.ceil(hours_diff / 2)
    set_key_count = hours_diff // 2

    c_diff = (sun_colors['mid'] - sun_colors['rise']) / (rise_key_count - 1)

    for a in range(rise_key_count - 1):
        hour_req = sun_data[0] + datetime.timedelta(hours=a)  # one keyframe per hour, starting at sunrise
        keyframes.append((hour_req, sun_colors['rise'] + c_diff * a, a))  # append the count so that we can see where we are for image updating
    hour_req = sun_data[0] + datetime.timedelta(hours=rise_key_count - 1)
    keyframes.append((hour_req, sun_colors['mid'], rise_key_count - 1))  # manually set last keyframe in order to actually hit the desired end color

    if sun_colors['set'] is None:
        sun_colors['set'] = random_color(dim=True)

    c_diff = (sun_colors['mid'] - sun_colors['set']) / (set_key_count - 1)

    for a in range(set_key_count - 1):
        hour_req = sun_data[0] + datetime.timedelta(hours=rise_key_count + a)
        keyframes.append((hour_req, sun_colors['mid'] - c_diff * a, a + rise_key_count))
    hour_req = sun_data[0] + datetime.timedelta(hours=rise_key_count + set_key_count - 1)
    keyframes.append((hour_req, sun_colors['set'], sun_key_count - 1))

    return keyframes


def random_color(from_table: bool = False, bright: bool = False, dim: bool = False):
    if from_table:  # TODO add more colors to the table
        color_table = (
            Color(255, 0, 0),
            Color(0, 255, 0),
            Color(0, 0, 255)
        )
        return random.choice(color_table)

    r_color = [random.randint(1, 255),
               random.randint(1, 255),
               random.randint(1, 255)]
    if bright:
        # if all colors are not bright (< 200), make one color bright
        if all(a < 200 for a in r_color):
            r_color[random.randint(0, 2)] = 200
    elif dim:
        # make sure no colors are too bright, and turn off one color
        quarter_brightness = 63
        r_color = [random.randint(1, quarter_brightness) if val > 150 else val
                   for val in r_color]
        r_color[random.randint(0, 2)] = 0
    return Color(*r_color)


def get_weather_priority():
    global cur_weather

    if 'thunder' in cur_weather.lower():
        return 5
    if 'rain' in cur_weather.lower():
        return 2
    if 'snow' in cur_weather.lower():
        return 5
    else:
        return -1


def get_stocks_priority():
    global priorities

    today = datetime.datetime.today()
    nasdaq_close = four_pm = 16

    # only show stock event for a few hours
    if today.hour >= nasdaq_close + 3:
        return -1
    else:
        return priorities['stocks']


def get_sleep_priority():
    current_hour = datetime.datetime.today().hour

    bed_time = 0
    wake_time = 6

    if bed_time <= current_hour <= wake_time:
        return 6
    else:
        return -1


def fetch_esb_color():
    """
    Populate the global `colors` dictionary and find the
    color of the Empire State Building on the current night.
    """
    # populate the colors Dictionary
    with open('colors.txt', encoding='UTF-8') as colors_file:
        for color in colors_file:
            if color.startswith('*'):
                continue
            color_name, r, g, b = color.split(',')
            colors[color_name.lower()] = Color(int(r), int(g), int(b))

    # get the color
    data = crawl_data('http://www.esbnyc.com/explore/tower-lights/calendar')
    if not data:
        return None

    lighting_description = str(data.find('p', 'lighting-desc').string).lstrip('\n ')

    for word in lighting_description.split(' '):
        color = colors.get(word.lower().rstrip(punctuation))
        if color and color != WHITE:
            return color
    return None


def fetch_weather_data():
    global is_init

    data = crawl_data('https://www.wunderground.com/weather/us/nj/hoboken')
    if not data:
        return

    try:
        phrase_now = str(data.find('div', id='curCond').contents[0].contents[0])
    except AttributeError as e:
        eprint('unable read data from www.wunderground.com. Information: ')
        eprint('\t', e, sep='')
        return None

    if is_init:  # On first run also gather sun data for the day
        # TODO make ampm more robust
        rise_t_str = data.find('span', id='cc-sun-rise')
        ampm = rise_t_str.parent.contents[2]
        rise_t_str = str(rise_t_str.contents[0]) + ' ' + str(ampm.contents[0])

        set_t_str = data.find('span', id='cc-sun-set')
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


def parse_calendar_event():
    global priorities, cal_event_color_str
    
    today = str(datetime.date.today())
    
    with open('holidays.txt', 'r', encoding='UTF-8') as holidays:
        for holiday in holidays:
            date, _, color, priority = holiday.split('|')
            if date == today:
                cal_event_color_str = color.encode()
                priorities['calendar'] = int(priority)
                break


def crawl_twitter_accounts():
    global priorities

    consumer_key = '8jQgMroN3l5lOgZ4gg8PY6PsD'
    consumer_secret = 'ZmpFmplX3qXdIQyFdMXeS61o4kHMGPFXw3lEwkGIODwYW34mZf'
    access_token = '1352886691-FeCAGFBWbt3ns4vkz1792IpBt0htAZqAV31VX0C'
    access_secret = 'h3Vx59GPYVEgKm4jla9pHEGpSoWJLNHsCpqLMsbC4angu'

    auth = OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_secret)

    api = tweepy.API(auth, timeout=5)
    
    team_won.update({team: did_team_win(api, team) for team in team_won})
    
    if any(team_won.values())
        priorities['sports'] = 3


def did_team_win(api: tweepy.API, team_name: str) -> bool:
    """
    Query Twitter for whether or not a team won using an API access.
    """
    yesterday = datetime.date.today() - datetime.timedelta(days=1)

    try:
        tweet = api.user_timeline('Did%sWin' % team_name.capitalize(), count=1)[0]
        date = tweet.created_at.date()
        text = tweet.text[:3].rstrip(',')
    except tweepy.error.TweepError as e:
        eprint("Failed to connect to %s's Twitter. error:\n\t%s" % (team_name, e))
        return False
    else:
        return text.lower() == 'yes' and date == yesterday


def fetch_stock_data():
    global priorities, DJI_difference, stocks_color_str

    data = crawl_data('https://www.google.com/finance?q=INDEXDJX:.DJI')
    if not data:
      return
    
    DJI_difference = float(data.find('span', id='ref_983582_c').string)
    
    if 200.0 <= DJI_difference < 300:
        stocks_color_str = b'03f1002,i9902,f0507'  # single pulse
        priorities['stocks'] = 2
    elif DJI_difference >= 300:
        stocks_color_str = b'05f1002,i9902,f0507,f0502,f0507'  # double pulse
        priorities['stocks'] = 3
    elif -300.0 < DJI_difference < -150:
        stocks_color_str = b'03f1000,i9900,f0507'
        priorities['stocks'] = 2
    elif DJI_difference <= -300:
        stocks_color_str = b'05f1000,i9900,f0507,f0500,f0507'
        priorities['stocks'] = 3


def send_color_str(col_string: bytes):
    global bus_lock, arduino
    print('sending', col_string)
    with bus_lock:
        arduino.write(col_string)
        # eprint('No connection to arduino!')


def crawl_data(url):
    try:
        res = requests.get(url)
    except requests.RequestException as e:
        eprint('unable to connect to', url.split('/')[2], 'Information: ')
        eprint('\t', e, sep='')
        return None
    else:
        return BeautifulSoup(res.content, 'html.parser')
        

def debug_print():
    """
    Print key global variables.
    """
    print('''
    ----------DEBUG OUT----------
    esb_color: {esb_color}
    sun_data[0] (sunrise): {sun_data[0]}
    sun_data[1] (sunset): {sun_data[1]}
    sun_keyframes: {sun_keyframes}
    sun_colors['set'] = {sun_set_color}
    cal_event_color_str: {cal_event_color_str}
    cur_weather: {cur_weather} (is_init: {is_init})
    weather_refresh_t: {weather_refresh_t}
    DJI_difference: {DJI_difference}
    stocks_color_str: {stocks_color_str}
    team_won: {team_won}
    priorities: {priorities}
    -----------------------------
    '''.format(**globals(), sun_set_color=sun_colors['set']))

if __name__ == '__main__':
    tr = threading.Thread(target=pc_listener, daemon=True)
    tr.start()
    while True:
        init()
