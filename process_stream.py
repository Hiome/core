# coding=utf-8

from multiprocessing import Process, Queue, active_children
import schedule
import sentry_sdk
import signal
import sys
import time
from home_stream_wrapper import HomeStreamWrapper as HomeStream

class ProcessStream:
  def __init__(self, name, on_connect=None, on_message=None, on_timer=None, on_timer_event=None, publish_status=True, clean_session=False):
    self.name = name
    self.on_connect = on_connect
    self.on_message = on_message
    connect_method = self.on_connect_pipe if self.on_connect is not None else None
    message_method = self.on_message_pipe if self.on_message is not None else None
    self.homestream = HomeStream('com.hiome', self.name, on_connect=connect_method, on_message=message_method,
        write_status=publish_status, clean_session=clean_session)
    self.q = Queue()

    self.on_timer = on_timer
    self.on_timer_event = on_timer_event
    if self.on_timer is not None:
      self.timer_q = Queue()
      self.timer_process = self.spawn_process(self.timer_loop)

    signal.signal(signal.SIGINT, self.on_shutdown)
    signal.signal(signal.SIGTERM, self.on_shutdown)

  def on_connect_pipe(self, client, rc):
    self.q.put(('on_connect', rc))

  def on_message_pipe(self, client, msg):
    self.q.put(('on_message', msg))

  def start(self):
    self.homestream.listen_async()
    if self.on_timer is not None:
      self.timer_process.start()
    self.run_forever(self.core_loop)

  def timer_loop(self):
    while True:
      if not self.timer_q.empty():
        msg = self.timer_q.get_nowait()
        self.on_timer(self, msg)
      schedule.run_pending()
      time.sleep(1)

  def core_loop(self):
    while True:
      event, msg = self.q.get()
      if event == 'on_message':
        self.on_message(self, msg)
      elif event == 'on_connect':
        self.on_connect(self, msg)
      elif self.on_timer_event is not None:
        self.on_timer_event(self, event, msg)

  def on_shutdown(self, _signal=None, _frame=None):
    sys.stdout.flush()
    sys.stderr.flush()
    self.homestream.stop_listening_async()
    while len(active_children()) > 0:
      try:
        active_children()[0].terminate()
      except Exception:
        pass
    print "Good bye, cruel world!"
    sys.exit()

  def safe_exec(self, method, *args, **kwargs):
    try:
      method(*args, **kwargs)
    except Exception:
      sentry_sdk.capture_exception()

  def run_forever(self, method, *args, **kwargs):
    while True:
      self.safe_exec(method, *args, **kwargs)

  def spawn_process(self, *args):
    process = Process(target=self.run_forever, args=args)
    process.daemon = True
    return process
