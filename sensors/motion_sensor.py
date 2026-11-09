# coding=utf-8

from abstract_sensor import AbstractSensor

class MotionSensor(AbstractSensor):
  def __init__(self, sensor_id, name, room_id, data, battery, version, last_seen, manager, sensor_type='motion'):
    super(MotionSensor, self).__init__(sensor_id, name, room_id, data, battery, version, last_seen, manager, sensor_type)
