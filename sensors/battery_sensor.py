# coding=utf-8

import datetime

from abstract_sensor import AbstractSensor

class BatterySensor(AbstractSensor):
  def __init__(self, sensor_id, name, room_id, data, battery, version, last_seen, manager, sensor_type='battery'):
    super(BatterySensor, self).__init__(sensor_id, name, room_id, data, battery, version, last_seen, manager, sensor_type)
    if self.name is None: self.update_name("Hiome PowerPack")

  def update_last_seen(self, should_update=True):
    if should_update:
      self.write_to('com.hiome', 'timer', 'device_online', 70, {'unit': 'minutes'})
      self.connected = True
      self.write('connected', True)
      self.last_seen = datetime.datetime.now()
      return self.last_seen
    return None

  def mark_offline(self):
    self.connected = False
    self.write('connected', False)
    self.update_battery(0)
    self.save()

  def publish_battery(self, old_val=None):
    # same as super method, except we insert a done_charging template
    # when battery first makes it into full category
    label = self.voltage_to_battery_label(self.battery)
    payload = {'was_val': old_val, 'label': label}
    if label == 'full':
      old_label = self.voltage_to_battery_label(old_val)
      if label != old_label: payload['tmpl'] = 'done_charging'
    self.write('battery', self.battery, payload=payload)
