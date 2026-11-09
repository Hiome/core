#!/usr/bin/python
# coding=utf-8

## Babel Fish Service
# 
# Translates HomeStream messages to old hiome mqtt message format

from home_stream_wrapper import HomeStreamWrapper as HomeStream
import json
import sentry_sdk

sentry_sdk.init()

sensor_names = {}

def on_connect(client, rc):
  client.subscribe(attribute='name')
  client.subscribe(attribute='door')
  client.subscribe(attribute='battery')
  client.subscribe(attribute='occupancy')

def on_message(hs, msg):
  if msg.attribute == 'name':
    sensor_names[msg.object_id] = msg.val
    return

  try:
    name = sensor_names[msg.object_id]
  except KeyError:
    return

  msg.data['meta'] = {
    "type": msg.attribute,
    "source": "gateway",
    "name": name,
    "client_id": "babelfish"
  }
  if msg.attribute == 'occupancy':
    msg.data['meta']['room'] = msg.object_id
  hs.client.publish("hiome/1/sensor/" + msg.object_id + ":" + msg.attribute, payload=json.dumps(msg.data), qos=1, retain=True)

HomeStream('com.hiome', 'babelfish', on_connect=on_connect, on_message=on_message, write_status=False).listen_forever()
