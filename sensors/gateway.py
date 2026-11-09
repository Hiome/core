# coding=utf-8

from abstract_sensor import AbstractSensor

class Gateway(AbstractSensor):
  def __init__(self, sensor_id, name, room_id, data, battery, version, last_seen, manager, sensor_type='gateway'):
    super(Gateway, self).__init__(sensor_id, name, room_id, data, battery, version, last_seen, manager, sensor_type)

  def update_data(self, data):
    return False

  def update_battery(self, battery):
    return False

  def update_last_seen(self, should_update=True):
    return None

  def initialize_data(self, data):
    return None
