#!/usr/bin/python
# coding=utf-8

## Occupancy Metrics Service
# 
# Track metrics around how our occupancy service is doing

from home_stream_wrapper import HomeStreamWrapper as HomeStream
import psycopg2
import sentry_sdk

sentry_sdk.init()

TWO_WEEKS_IN_MS = 2 * 7 * 24 * 60 * 60 * 1000

def on_connect(client, rc):
  client.subscribe(namespace="com.hiome", attribute="entry")

def on_deleted(client, msg):
  with psycopg2.connect("") as conn:
    with conn.cursor() as db:
      # eventually this will also "DROP_MATERIALIZED_VIEW entries_agg_"+device_id
      db.execute("DELETE FROM entries WHERE sensor_id = %s", (msg.object_id,))

def on_message(client, msg):
  if msg.val == 'reverted' or msg.val == 'validated': return

  # save to local db, ignoring duplicates
  with psycopg2.connect("") as conn:
    with conn.cursor() as db:
      db.execute("""
        INSERT INTO entries(
          sensor_id,
          ts,
          is_valid,
          valid_score,
          invalid_score,
          confidence,
          direction,
          sensor_conf,
          bgm,
          fgm,
          start_position,
          end_position,
          history,
          blob_size,
          noise_size,
          neighbors,
          height,
          width,
          hw_ratio,
          tempc,
          payload
        ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
      """, (msg.object_id, msg.ts, msg.data['is_valid'], msg.data['valid_score'], msg.data['invalid_score'], msg.data['confidence'],
        msg.val, msg.data['sensor_conf'], msg.data['bgm'], msg.data['fgm'], msg.data['start_position'], msg.data['end_position'],
        msg.data['history'], msg.data['blob_size'], msg.data['noise_size'], msg.data['neighbors'], msg.data['height'], msg.data['width'],
        msg.data['hw_ratio'], msg.data['tempc'], msg.payload))
      # delete entries from this sensor that are more than 2 weeks old
      db.execute("DELETE FROM entries WHERE sensor_id = %s and ts < %s and corrected is false", (msg.object_id, msg.ts - TWO_WEEKS_IN_MS))

HomeStream('com.hiome', 'entry_metrics', on_connect=on_connect, on_message=on_message, on_deleted=on_deleted).listen_forever()
