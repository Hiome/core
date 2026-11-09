# coding=utf-8

from logger import Logger
from room import Room
from sensors import BatterySensor, BedSensor, DoorSensor, MotionSensor, Gateway

class RoomManager:
  """ Tracks all rooms in environment. """

  def __init__(self, hs):
    self.homestream = hs
    self._restore()

  def find_room(self, room_id):
    try:
      return self.rooms[room_id]
    except KeyError:
      return None

  def create_room(self, room_id, name, count=0, hidden=False, publish_diff=False, persist=False):
    if room_id in self.rooms: return None
    r = Room(room_id, name, count, hidden, self)
    self.rooms[r.id] = r
    if persist:
      Logger.create_room(r.id, r.name, r.hidden, r.count)
    if publish_diff or persist:
      # find latest published values for this room
      published = self.homestream.read(namespace='com.hiome', object_id=r.id)
      attr_published = {p.attribute: p.val for p in published}
      # if name does not match published value, update it
      if attr_published.get('name') != r.name:
        r.write('name', r.name)
      # if hidden does not match published value, update it
      if attr_published.get('hidden') != r.hidden:
        r.write('hidden', r.hidden)
      # if occupancy does not match published value, update it
      occ_val = attr_published.get('occupancy')
      if not r.hidden and occ_val != r.count:
        # but only if the room is not hidden
        r.write('occupancy', r.count)
      elif r.hidden and occ_val is not None:
        # if room is hidden, delete occupancy state
          r.erase('occupancy')
    return r

  def delete_room(self, room_id):
    room = self.rooms.pop(room_id, None)
    if room:
      room.erase_all()
      # need to eliminate all references to this room object,
      # like suspicious rooms stack of other rooms, from memory for GC
      self._restore(publish_diff=False)

  def find_device(self, device_id):
    try:
      return self.devices[device_id]
    except KeyError:
      return None

  def create_device(self, sensor_id, sensor_type, name=None, room_id=None, data=None, battery=None, version=None, last_seen=None,
                      publish_diff=False, persist=False):
    device = self.sensor_class_from_type(sensor_type)(sensor_id, name, room_id, data, battery, version, last_seen, self)
    self.devices[device.id] = device
    if persist:
      Logger.create_sensor(device.id, device.name, device.type, device.room_id, device.version)
    if publish_diff or persist:
      # find latest published values for this object
      published = self.homestream.read(namespace='com.hiome', object_id=device.id)
      attr_published = {p.attribute: p.val for p in published}
      # check name
      if attr_published.get('name') != device.name:
        # mismatch between recorded value and what's published. Choose recorded value
        if device.name is None: # nothing to publish, erase what's there
          device.erase('name')
        else:
          device.write('name', device.name)
      # check device type (door, motion, bed, etc)
      if device.type != 'battery' and attr_published.get(device.type) != device.data:
        if device.data is None:
          device.erase(device.type)
        else:
          device.write(device.type, device.data)
      # check battery
      if attr_published.get('battery') != device.battery:
        if device.battery is None:
          device.erase('battery')
        else:
          device.publish_battery()
      # check version
      if attr_published.get('version') != device.version:
        if device.version is None:
          device.erase('version')
        else:
          device.write('version', device.version)
      # check room
      if attr_published.get('room') != device.room_id:
        if device.room_id is None:
          device.erase('room')
        else:
          device.write('room', device.room_id)
    return device

  def sensor_class_from_type(self, sensor_type):
    if sensor_type == 'door':
      return DoorSensor
    elif sensor_type == 'battery':
      return BatterySensor
    elif sensor_type == 'bed':
      return BedSensor
    elif sensor_type == 'motion':
      return MotionSensor
    elif sensor_type == 'gateway':
      return Gateway
    else:
      raise ValueError("Unknown sensor type")

  def delete_device(self, device_id):
    device = self.devices.pop(device_id, None)
    if device:
      device.erase_all()
      # re-create empty stub
      self.create_device(device.id, device.type, version=device.version)

  def _restore(self, publish_diff=True):
    """ Restores data from database into memory for faster recall """
    self.rooms = {}
    self.devices = {}

    # restore last known state of all rooms
    for room in Logger.rooms():
      self.create_room(room['id'], room['name'], room['occupancy_count'], room['hidden'], publish_diff=publish_diff)

    for sensor in Logger.sensors():
      self.create_device(
        sensor['id'],
        sensor['type'],
        sensor['name'],
        sensor['room_id'],
        sensor['data'],
        sensor['battery'],
        sensor['version'],
        sensor['last_seen'],
        publish_diff=publish_diff
      )
