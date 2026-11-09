#!/usr/bin/python
# coding=utf-8

## Bouncer Service
# 
# Checks external resources and lets them in if appropriate
# TODO this will eventually use an SQS queue per device to load remote commands that can be queued even if device is offline

from home_stream_wrapper import HomeStreamWrapper as HomeStream
import json
import os
import psycopg2
import psycopg2.extras
import sentry_sdk
import time
import urllib2

sentry_sdk.init()

hs = HomeStream('com.hiome', 'manifester').listen_async()

DEVICEID = os.getenv('DEVICEID')
MANIFEST_BASE_URL = os.getenv('MANIFEST_BASE_URL', '').rstrip('/')
stream = hs.read('com.hiome', 'settings', 'timezone')
tz = stream[0].val if len(stream) == 1 else None

def parse_manifest():
  global tz

  # Remote provisioning is optional in this archival source release.
  if not MANIFEST_BASE_URL or not DEVICEID:
    return

  for attempt in range(5): # try up to 5 times to establish network connection
    try:
      manifest = json.load(urllib2.urlopen(MANIFEST_BASE_URL + '/' + DEVICEID + '.json'))
    except urllib2.URLError: # network failure
      if attempt == 4: # we're out of lives
        return
      else:
        # wait 2+ seconds before trying again
        time.sleep(2 + attempt)
    else: # successfully grabbed manifest
      break

  # check what's in database
  known_sensors = {}
  with psycopg2.connect("") as conn:
    with conn.cursor() as db:
      db.execute("SELECT id, type FROM sensors")
      pg_sensors = db.fetchall()
      for s in pg_sensors:
        known_sensors[s[0]] = s[1]

  for k,v in manifest.iteritems():
    if k == "tz":
      if v != tz:
        hs.write('timezone', v, author='settings')
        tz = v
    elif k not in known_sensors:
      hw_type, hw_revision = v.split('/')
      hs.write_to('com.hiome', 'gateway', 'create_sensor', k, payload={'type': hw_type})

while True:
  parse_manifest()
  time.sleep(90000) # check again in over a day
