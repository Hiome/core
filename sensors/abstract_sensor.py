# coding=utf-8

import sys
sys.path.insert(0, '..')
from logger import Logger
import datetime

class AbstractSensor(object):
  def __init__(self, sensor_id, name, room_id, data, battery, version, last_seen, manager, sensor_type='generic'):
    self.id = sensor_id
    self.name = unicode(name, 'utf-8') if isinstance(name, str) else name
    self.room_id = room_id
    self.data = self.initialize_data(data)
    self.battery = int(battery) if battery is not None else None
    self.version = version
    self.type = sensor_type
    self.manager = manager
    self.last_seen = last_seen
    self.connected = None

  def update(self, data, battery=None, should_update_last_seen=True):
    updated = False
    if self.parse_data(data): updated = True
    if self.update_battery(battery): updated = True

    if updated:
      last_seen = self.update_last_seen(should_update_last_seen)
      self.save(last_seen)

  def parse_data(self, data):
    if data is not None:
      if str(data)[0] == 'V': return self.update_version(data)
      if str(data) == 'h': return True
      return self.update_data(data)
    return False

  def update_data(self, data):
    if self.data != data:
      old_val = self.data
      self.data = data
      self.write(self.type, self.data, payload={'was_val': old_val})
      return True
    return False

  def initialize_data(self, data):
    return data

  def update_version(self, version):
    if self.version != version:
      old_val = self.version
      self.version = version
      pl = {'was_val': old_val}
      if old_val is not None and self.version is not None:
        pl['tmpl'] = 'updated'
      self.write('version', self.version, payload=pl)
      return True
    return False

  def update_battery(self, battery):
    if battery is not None and self.battery != int(battery):
      old_val = self.battery
      self.battery = int(battery)
      if self.battery > 0:
        self.publish_battery(old_val)
      else:
        self.erase('battery')
      return True
    return False

  def voltage_to_battery_label(self, voltage):
    if voltage > 410: return "full"
    elif voltage > 380: return "high"
    elif voltage > 350: return "normal"
    elif voltage > 340: return "low"
    elif voltage > 250: return "critical"
    else: return "none"

  def publish_battery(self, old_val=None):
    self.write('battery', self.battery, payload={'was_val': old_val, 'label': self.voltage_to_battery_label(self.battery)})

  def update_last_seen(self, should_update=True):
    if should_update:
      self.write_to('com.hiome', 'timer', 'device_online', 4, {'unit': 'hours'})
      self.connected = True
      if self.last_seen is None:
        payload = {'tmpl': 'new_device'}
      elif self.connected is False:
        payload = {'tmpl': 'reconnected'}
      else:
        payload = {}
      self.write('connected', True, payload=payload)
      self.last_seen = datetime.datetime.now()
      return self.last_seen
    return None

  def update_room_id(self, room_id):
    if room_id is not None: room_id = str(room_id)
    if room_id != self.room_id:
      self.room_id = room_id
      Logger.put_sensor_in_room(self.id, room_id)
      if room_id is None:
        self.erase('room')
      else:
        self.write('room', room_id)
      return True
    return False

  def update_name(self, name):
    name = unicode(name, 'utf-8') if isinstance(name, str) else name
    if name != self.name:
      self.name = name
      Logger.name_sensor(self.id, name)
      if name is None:
        self.erase('name')
      else:
        self.write('name', name)

  def mark_offline(self):
    self.connected = False
    self.write('connected', False, payload={'tmpl':'disconnected'})

  def save(self, last_seen=None):
    Logger.save_sensor(self.id, self.data, self.battery, self.version, last_seen)

  def write(self, attr, val, payload={}, retain=True):
    return self.manager.homestream.write(attr, val, payload=payload, retain=retain, author=self.id)

  def write_to(self, namespace, object_id, attr, val, payload={}):
    return self.manager.homestream.write_to(namespace, object_id, attr, val, payload=payload, author=self.id)

  def erase(self, attr):
    self.manager.homestream.erase(attr, author=self.id)

  def erase_all(self):
    Logger.delete_sensor(self.id)
    self.erase(self.type)
    self.erase('battery')
    self.erase('name')
    self.erase('room')
    self.erase('connected')
