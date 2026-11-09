# coding=utf-8
"""Optional telemetry. No external destination is enabled by default."""

import json
import os
import statsd
from socket import gaierror
import urllib2

DEVICEID = os.getenv('DEVICEID', 'example-device')

def slack(text, ts=None):
  webhook = os.getenv('SLACK_WEBHOOK_URL')
  if not webhook:
    return
  attachment = {
    "mrkdwn_in": ["text"],
    "color": "#6F3CD1",
    "title": DEVICEID,
    "text": text,
    "ts": ts
  }
  dashboard = os.getenv('DEVICE_DASHBOARD_URL')
  if dashboard:
    attachment['title_link'] = dashboard
  urllib2.urlopen(webhook, json.dumps({"attachments": [attachment]}))

def stats(*args):
  host = os.getenv('STATSD_HOST')
  if not host:
    return
  try:
    port = int(os.getenv('STATSD_PORT', '8125'))
    statsd.StatsClient(host, port, prefix=DEVICEID).incr(*args)
  except gaierror:
    pass
