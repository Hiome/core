# coding=utf-8

import datetime
from logger import Logger
from parse_bool import parse_bool

class Room:
  def __init__(self, id, name, count, hidden, manager):
    self.id = id
    self.name = unicode(name, 'utf-8') if isinstance(name, str) else name
    self.count = count or 0
    self.hidden = parse_bool(hidden, False)
    self.manager = manager
    self.suspicious_rooms = []
    self.empty_since = None
    self.occupied_since = None
    self.last_activity_context_ts = None
    if self.count > 0:
      self._reset_inactivity_timer()

  def update_count(self, new_count, reason=None, context_ts=None, context_topic=None, door_id=None, other_room_id=None):
    if self.count == new_count: return
    old_count = self.count
    self.count = new_count
    self.publish(reason, context_ts, context_topic, door_id, other_room_id, old_count)
    Logger.update_occupancy_count(self.id, self.count)
    if old_count == 0:
      # room just became occupied
      self._reset_decay_timer()
      self.occupied_since = datetime.datetime.now()
    elif self.count == 0:
      # room just became empty
      self.empty_since = datetime.datetime.now()
    if self.count > 0:
      # somebody entered room
      self._reset_inactivity_timer()

  def publish(self, reason=None, context_ts=None, context_topic=None, door_id=None, other_room_id=None, from_count=None):
    """ Publish current room count, called when room is first created """
    if self.hidden: return
    payload = {
      'was_val': from_count,
      'tmpl': reason,
      'context_ts': context_ts,
      'context_topic': context_topic,
      'door_id': door_id,
      'other_room_id': other_room_id
    }
    if self.count != from_count and from_count is not None: # don't include durations if publishing for negative occupancy alert
      if self.count == 0 and self.occupied_since is not None:
        # room just became empty and we were around when it became occupied
        payload['was_occupied_duration'] = int((datetime.datetime.now() - self.occupied_since).total_seconds())
      elif from_count == 0 and self.empty_since is not None:
        # room just became occupied and we were around when it became empty
        payload['was_empty_duration'] = int((datetime.datetime.now() - self.empty_since).total_seconds())
    self.write('occupancy', self.count, payload=payload)
    self.last_activity_context_ts = context_ts

  def _reset_inactivity_timer(self):
    if self.hidden: return
    # whenever there is a chance in occupancy, this counter should be reset
    # if it hits 0, the count is reset to 0 because there was no activity
    self.write_to('com.hiome', 'timer', 'activity', 23, {'unit': 'hours'})

  def _reset_decay_timer(self):
    if self.hidden: return
    # as long as room is occupied, this counter should keep counting down
    # when it hits 0, it will decay 1 from occupancy count
    self.write_to('com.hiome', 'timer', 'occupancy', 24, {'unit': 'hours'})

  def update_name(self, name):
    name = unicode(name, 'utf-8') if isinstance(name, str) else name
    if name != self.name:
      self.name = name
      Logger.name_room(self.id, self.name)
      self.write('name', self.name)

  def hide_room(self, hidden):
    hidden = parse_bool(hidden)
    if hidden is None: return
    if hidden != self.hidden:
      self.hidden = hidden
      Logger.hide_room(self.id, self.hidden)
      self.write('hidden', self.hidden)
      if self.hidden:
        self.erase('occupancy')
      else:
        self.publish()
        if self.count > 0:
          self._reset_inactivity_timer()
          self._reset_decay_timer()

  def erase_all(self):
    Logger.delete_room(self.id)
    self.erase('name')
    self.erase('hidden')
    self.erase('occupancy')

  def clear_occupancy(self):
    self.override_count(0, reason='cleared')

  def decay_occupancy(self):
    if self.count > 0:
      self.override_count(self.count - 1, reason='decayed')

  def override_count(self, new_count, reason='reset', context_ts=None, context_topic=None):
    self.update_count(new_count, reason=reason, context_ts=context_ts, context_topic=context_topic)
    if self.count > 0: self._reset_decay_timer()
    self.suspicious_rooms = []

  def entered(self, door_id=None, other_room_id=None, reason='entry', context_ts=None, context_topic=None):
    self.update_count(self.count + 1, reason=reason, context_ts=context_ts, context_topic=context_topic, door_id=door_id, other_room_id=other_room_id)

  def exited(self, door_id=None, other_room_id=None, reason='exit', context_ts=None, context_topic=None):
    if self.count > 0:
      self.update_count(self.count - 1, reason=reason, context_ts=context_ts, context_topic=context_topic, door_id=door_id, other_room_id=other_room_id)
    else:
      self.publish('negative', context_ts, context_topic, door_id, other_room_id, 0)
      self.exit_suspicious_room(context_ts, context_topic)

  def add_suspicious_room(self, room, sensor_id=None, entry_ts=None):
    if self.hidden: return
    self.suspicious_rooms.append((room, datetime.datetime.now(), sensor_id, entry_ts))
    while len(self.suspicious_rooms) > 10:
      # drop items from front until list is at 10 length max
      self.suspicious_rooms.pop(0)

  def exitable(self):
    # room either has more than 1 person or the one person isn't the entry that just happened
    return self.hidden or self.count > 1 or (self.count == 1 and (self.occupied_since is None or 
      self.occupied_since + datetime.timedelta(milliseconds=100) < datetime.datetime.now()))

  def exit_suspicious_room(self, context_ts, context_topic):
    if self.hidden: return
    # loop through suspicious rooms until we find one to exit
    while len(self.suspicious_rooms) > 0:
      room, suspicious_at, sensor_id, entry_ts = self.suspicious_rooms.pop()
      if room is None: return # external room, assume that's where person came from
      if room.exitable(): # room is occupied
        # but if it's been empty since it was suspicious, so skip it anyway
        if room.empty_since is not None and room.empty_since > suspicious_at: continue
        # otherise, if there's an entry attached, try reverting it
        if entry_ts is not None and Logger.revert_entry(sensor_id, entry_ts) is not None:
          self.manager.homestream.write('entry', 'reverted', payload={
            'entry_ts': entry_ts,
            'tmpl': 'auto_revert',
            'context_ts': context_ts,
            'context_topic': context_topic
          }, retain=False, author=sensor_id)
        # finally perform the exit
        room.exited(other_room_id=self.id, reason='siphoned', context_ts=context_ts, context_topic=context_topic)
        return

    # check all linked rooms. If there's only 1 occupied one, exit it
    closed_rooms = []
    occupied_room = None
    for sensor in self.manager.devices.itervalues():
      if sensor.type == 'door':
        if sensor.in_room(self.id):
          if (sensor.data == 'closed' and sensor.door_closed_at + datetime.timedelta(hours=2) < datetime.datetime.now()) or \
             (sensor.data == 'ajar' and sensor.door_ajar_at + datetime.timedelta(hours=2) < datetime.datetime.now()):
            # door has been closed or ajar for over 2 hours, so it's probably not the room that person came from
            closed_rooms.append(sensor)
            # skip this door
            continue
          if sensor.room1 is None or sensor.room2 is None:
            # there's an external door in this room, we have no idea if person came from there or not
            return
          other_room = sensor.room2 if sensor.room1.id == self.id else sensor.room1
          if other_room.hidden: return
          if other_room.exitable():
            if occupied_room is None:
              # we found a candidate
              occupied_room = other_room
            else:
              # more than one room found, give up
              return

    if occupied_room is None:
      closed_rooms.sort(key=lambda x: max(x.door_closed_at, x.door_ajar_at), reverse=True)
      last_closed_at = datetime.datetime.now()
      # no occupied room was open in the last 2 hours, let's look at the rooms with closed doors
      for sensor in closed_rooms:
        if occupied_room is not None:
          timediff = int((datetime.datetime.now() - last_closed_at).total_seconds())
          if max(sensor.door_closed_at, sensor.door_ajar_at) + datetime.timedelta(seconds=timediff) < last_closed_at:
            # this door closed more than 2*x seconds ago, where x is how long ago the currently selected door closed.
            # we already found a potential room and that difference is big enough, so we're going to stop looking
            break
        if sensor.room1 is None or sensor.room2 is None:
          # there's an external door in this room, we have no idea if person came from there or not
          return
        other_room = sensor.room2 if sensor.room1.id == self.id else sensor.room1
        if other_room.hidden: return
        if other_room.exitable():
          if occupied_room is None:
            # we found a candidate
            occupied_room = other_room
            last_closed_at = max(sensor.door_closed_at, sensor.door_ajar_at)
          else:
            # more than one room found, give up
            return

    if occupied_room is not None:
      occupied_room.exited(other_room_id=self.id, reason='siphoned', context_ts=context_ts, context_topic=context_topic)

  def write(self, attr, val, payload={}, retain=True):
    return self.manager.homestream.write(attr, val, payload=payload, retain=retain, author=self.id)

  def write_to(self, namespace, object_id, attr, val, payload={}):
    return self.manager.homestream.write_to(namespace, object_id, attr, val, payload=payload, author=self.id)

  def erase(self, attr):
    self.manager.homestream.erase(attr, author=self.id)
