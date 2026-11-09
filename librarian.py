#!/usr/bin/python
# coding=utf-8

## Librarian Service
# 
# Keeper of the ledger. This service logs all HomeStream events to a database

import json
import psycopg2
import sentry_sdk
import paho.mqtt.client as mqtt
import time
from hiome_helper import slack, stats

sentry_sdk.init()

TWO_WEEKS_IN_MS = 2 * 7 * 24 * 60 * 60 * 1000

def onConnect(client, userdata, flags, rc):
  try:
    client.publish('hs/1/com.hiome/librarian/connected', payload=json.dumps({'val':True,'ts':int(round(time.time()*1000.0))}), qos=1, retain=True)
    client.subscribe('hs/1/#', qos=1)
  except Exception:
    sentry_sdk.capture_exception()

def onMessage(client, userdata, payload):
  try:
    payload.topic = payload.topic.lower()
    topic = payload.topic.split('/', 4)

    if not payload.payload:
      # we deleted a topic, delete all logs of it
      with psycopg2.connect("") as conn:
        with conn.cursor() as db:
          db.execute("DELETE FROM events WHERE topic = %s", (payload.topic,))
      return

    try:
      msg = json.loads(payload.payload)
    except ValueError:
      # payload must be a valid json message
      return
    # required attributes for HomeStream
    if 'ts' not in msg or 'val' not in msg: return

    if topic[4].startswith('to/'):
      cmd = topic[4].split('/', 3)
      attr = 'to'
      to_namespace = cmd[1]
      to_object_id = cmd[2]
      to_attr = cmd[3]
    else:
      attr = topic[4]
      to_namespace = to_object_id = to_attr = None

    if attr == 'occupancy' and msg.get('tmpl') is not None:
      if msg['tmpl'] in ('negative', 'reset', 'revert', 'cleared', 'decayed'):
        # publish to slack
        slack("Occupancy changed from " + str(msg['was_val']) + " to " + str(msg['val']) + " because *" + msg['tmpl'] + "*", int(msg['ts']/1000.0))

      # publish to statsd
      if msg['tmpl'] == 'negative':
        stats('negative_occupancy', 1)
      else:
        count = abs(msg['was_val'] - msg['val'])
        if count > 0:
          stats(msg['tmpl'], count)

    # don't bother logging all the connected status updates. It creates too
    # much noise, and wills from when service disconnects have out-of-order ts
    if topic[4] == 'connected' and msg.get('tmpl') is None: return

    # save to local db, ignoring duplicates
    with psycopg2.connect("") as conn:
      with conn.cursor() as db:
        db.execute("""
          INSERT INTO events(
            ts,
            topic,
            namespace,
            object_id,
            attribute,
            to_namespace,
            to_object_id,
            to_attribute,
            payload,
            context_ts,
            context_topic,
            tmpl
          ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
        """, (msg['ts'], payload.topic, topic[2], topic[3], attr, to_namespace, to_object_id, to_attr,
          payload.payload, msg.get('context_ts'), msg.get('context_topic'), msg.get('tmpl')))
        # delete messages from this topic that are more than 2 weeks old
        db.execute("DELETE FROM events WHERE ts < %s and topic = %s", (msg['ts'] - TWO_WEEKS_IN_MS, payload.topic))
  except Exception:
    sentry_sdk.capture_exception()

client = mqtt.Client(client_id='com.hiome:librarian', clean_session=False)
client.on_connect = onConnect
client.on_message = onMessage
client.will_set('hs/1/com.hiome/librarian/connected', payload=json.dumps({'val':False,'ts':int(round(time.time()*1000.0))}), qos=1, retain=True)
client.connect('hiome', 1883, 60)
client.loop_forever()
