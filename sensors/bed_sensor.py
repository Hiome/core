# coding=utf-8

from abstract_sensor import AbstractSensor

class BedSensor(AbstractSensor):
  def __init__(self, sensor_id, name, room_id, data, battery, version, last_seen, manager, sensor_type='bed'):
    super(BedSensor, self).__init__(sensor_id, name, room_id, data, battery, version, last_seen, manager, sensor_type)
