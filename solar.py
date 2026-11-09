#!/usr/bin/python

## Solar Service
# 
# Checks times for dawn, sunrise, sunset, and dusk events
# every day and schedules jobs to publish events when they
# happen.

from home_stream_wrapper import HomeStreamWrapper as HomeStream
from astral import Astral, Location
from datetime import datetime, timedelta
import ipinfo
import pytz
import sentry_sdk
import time

sentry_sdk.init()

handler = ipinfo.getHandler()
ip_info = handler.getDetails()

a = Astral()
city = Location()
city.name = ip_info.city
city.region = ip_info.region
city.timezone = 'UTC'
city.latitude = float(ip_info.latitude)
city.longitude = float(ip_info.longitude)

hs = HomeStream('com.hiome', 'sun', write_status=True).listen_async()
# Publish name if necessary
stream = hs.read('com.hiome', 'sun', 'name')
if len(stream) == 0 or stream[0].val != 'Sun':
  hs.write('name', 'Sun')

def current_time():
  return datetime.now(pytz.utc)

def sun_for(d):
  return a.sun_utc(d, city.latitude, city.longitude)

def datetime_to_epoch(ts):
  return int(ts.strftime('%s'))*1000

next_time = datetime(1970,1,1,tzinfo=pytz.utc)

def current_position(t):
  sun = sun_for(t.date())
  # skip dawn, noon, and dusk events
  if sun['sunrise'] <= t and sun['sunset'] > t:
    # if we're between sunrise and sunset, sun is up
    position = 'sunrise'
  else:
    position = 'sunset'
  return (sun, position)

def update_next_time(sun, position, at_time):
  global next_time

  next_event = 'sunset' if position == 'sunrise' else 'sunrise'
  if sun[next_event] < at_time:
    # we must be at the end of the day, calculate sunrise for tomorrow instead
    sun = sun_for(at_time.date() + timedelta(days=1))

  # delay event time by 2 minutes to ensure
  # position math works when this time rolls around
  next_time = sun[next_event] + timedelta(minutes=2)

def calculate_starting_position():
  # lookup the last position we published in a previous life
  stream = hs.read('com.hiome', 'sun', 'position')
  # if nothing found, end this method and let publish_position do its magic
  if len(stream) != 1: return

  now = current_time()
  sun, position = current_position(now)

  # previously published position is not the current position, so we've been
  # blacked out for a while. End this method and let publish_position handle it
  if position != stream[0].val: return

  # calculate time for next publish
  update_next_time(sun, position, now)

def publish_position(with_template=True):
  now = current_time()
  if now > next_time:
    # find current position
    sun, position = current_position(now)
    # publish it
    pl = {'occurred_at': datetime_to_epoch(sun[position])}
    if with_template: pl['tmpl'] = position
    hs.write('position', position, payload=pl)
    # calculate time for next publish
    update_next_time(sun, position, now)

# publish current position on startup
calculate_starting_position()
publish_position(with_template=False)

# wait for next publish
while True:
  # calculate number of seconds until next publish
  secs_until = int((next_time - current_time()).total_seconds())
  if secs_until > 300:
    # we're more than 5 minutes away, sleep until we're 4 minutes away
    time.sleep(secs_until - 240)
  else:
    # probably 4 minutes away, wait 5 min to be safe
    # this extra wait is to account for clock drift.
    time.sleep(300)

  publish_position()
