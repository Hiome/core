#!/usr/bin/python

## Health Service
# 
# Log all mqtt messages and track errors in database

from home_stream_wrapper import HomeStreamWrapper as HomeStream
import serial
import sentry_sdk

sentry_sdk.init()

# adapted from https://github.com/pyserial/pyserial/issues/216
class ReadLine:
  def __init__(self, s):
    self.buf = bytearray()
    self.s = s

  def readline(self):
    i = self.buf.find(b"\n")
    if i >= 0:
      r = self.buf[:i]
      self.buf = self.buf[i+1:]
      return (r, i)
    while True:
      i = max(1, min(1024, self.s.in_waiting))
      data = self.s.read(i)
      i = data.find(b"\n")
      if i >= 0:
        l = len(self.buf) + i
        r = self.buf + data[:i]
        self.buf[0:] = data[i+1:]
        return (r, l)
      else:
        self.buf.extend(data)

ser = serial.Serial('/dev/ttyAMA0', baudrate=19200, timeout=None, xonxoff=True, rtscts=False, dsrdtr=False)
serWrapped = ReadLine(ser)

# gateway is always node id 1
hs = HomeStream('com.hiome', '1', write_status=True).listen_async()

try:
  while True:
    data, l = serWrapped.readline()
    if l > 5: # min valid message size is 6: 2;1;01
      hs.write('message', data.decode('ascii', 'ignore'), retain=False)
finally:
  ser.close()
