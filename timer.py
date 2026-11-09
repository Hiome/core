import datetime
import schedule
import sentry_sdk
from process_stream import ProcessStream

sentry_sdk.init()

TIMERS = {}

# 1. external service asks us to start a timer
def on_message(ps, msg):
  # pass event to timer thread
  ps.timer_q.put(msg)

# 2. create scheduler job
def schedule_timer(ps, msg):
  object_id = msg.namespace + '/' + msg.object_id

  if msg.val is None:
    # a timer event is being deleted
    TIMERS.setdefault(msg.to_attribute, {}).pop(object_id, None)
    return

  unit = msg.data.get('unit', 'minutes')
  if unit not in ['seconds', 'minutes', 'hours', 'days', 'weeks']:
    if unit in ['second', 'minute', 'hour', 'day', 'week']:
      # make plural for datetime.timedelta
      unit += 's'
    else:
      raise ValueError("Unrecognized time " + unit)

  TIMERS.setdefault(msg.to_attribute, {})[object_id] = datetime.datetime.fromtimestamp(msg.ts/1000.0)
  getattr(schedule.every(msg.val), unit).do(run_timer, msg.to_attribute, object_id, msg.val, unit, ps.q)

# 3. the time has come!
def run_timer(event, object_id, timeout, unit, process_q):
  # only do something if the service did not overwrite or delete this timer
  if datetime.datetime.now() >= TIMERS.get(event, {}).get(object_id, datetime.datetime.now()) + datetime.timedelta(**{unit: timeout}):
    # pass event back to main thread for publishing
    process_q.put((event, (object_id, timeout)))
    # delete this key since we are done with it now
    del TIMERS[event][object_id]
  return schedule.CancelJob

# 4. tell external service that their timer has expired
def publish_expiration(ps, event, t):
  # publish from main thread to re-use our existing homestream thread
  object_id, timeout = t
  ns, oid = object_id.split('/')
  ps.homestream.write_to(ns, oid, event + '_expired', timeout)

ProcessStream('timer', on_message=on_message, on_timer=schedule_timer, on_timer_event=publish_expiration).start()
