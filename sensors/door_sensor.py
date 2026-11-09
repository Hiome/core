# coding=utf-8

import sys
sys.path.insert(0, '..')
from logger import Logger
from abstract_sensor import AbstractSensor
import datetime
import math

class DoorSensor(AbstractSensor):
  def __init__(self, sensor_id, name, room_id, data, battery, version, last_seen, manager, sensor_type='door'):
    super(DoorSensor, self).__init__(sensor_id, name, room_id, data, battery, version, last_seen, manager, sensor_type)
    if room_id is not None:
      room1_id, room2_id = room_id.split('::')
      self.room1 = self.manager.find_room(room1_id)
      self.room2 = self.manager.find_room(room2_id)
    else:
      self.room1 = self.room2 = None
    self.door_ajar_at = datetime.datetime.now()
    self.door_opened_at = datetime.datetime.now()
    self.door_closed_at = datetime.datetime.now()
    self.last_entered_at = datetime.datetime.now()

  def update_room_id(self, room_id):
    if room_id is not None: room_id = str(room_id)
    if room_id != self.room_id:
      raise ValueError('Cannot update room for door sensor. Delete first')

  def in_room(self, room_id):
    if self.room1 is not None and self.room1.id == room_id: return True
    if self.room2 is not None and self.room2.id == room_id: return True
    return False

  def erase_all(self):
    super(DoorSensor, self).erase_all()
    self.erase('entry')

  def revert_entry(self, entry_ts, validated):
    entry = Logger.validate_entry(self.id, entry_ts, validated)
    if entry is None: return

    if entry['is_valid'] == validated:
      if entry['corrected'] is False:
        # user validated an already valid entry
        self.write('entry', 'validated', payload={'entry_ts': entry_ts, 'tmpl': 'validated'}, retain=False)
      return

    context_ts = self.write('entry', 'reverted', payload={'entry_ts': entry_ts, 'tmpl': 'revert'}, retain=False)
    context_topic = 'hs/1/com.hiome/' + self.id + '/entry'

    if entry['direction'] == '1':
      entry_room = self.room1
      exit_room = self.room2
    else:
      entry_room = self.room2
      exit_room = self.room1
    if entry['is_valid']:
      # entry was valid and now it's not, so undo it if possible
      events = Logger.occupancy_events_for_context(entry_ts, 'hs/1/com.hiome/' + self.id + '/entry')
      total_change = 0
      reverted_change = 0
      for e in events:
        r = self.manager.find_room(e['object_id'])
        if r is None: continue
        total_change += (e['data']['val'] - e['data']['was_val'])
        if r.last_activity_context_ts == entry_ts:
          # room hasn't done anything since this bad entry happened
          r.override_count(e['data']['was_val'], reason='revert', context_ts=context_ts, context_topic=context_topic)
          reverted_change += (e['data']['val'] - e['data']['was_val'])
      if total_change != reverted_change:
        # this means we either created or destroyed a person and have not properly reverted them
        if total_change < 0 or reverted_change > 0:
          if exit_room is not None: # room must always exist if we reached here, but let's practice safe coding
            other_room_id = entry_room.id if entry_room is not None else None
            exit_room.entered(self.id, other_room_id, reason='revert', context_ts=context_ts, context_topic=context_topic)
        elif total_change > 0 or reverted_change < 0:
          if entry_room is not None: # room must always exist if we reached here, but let's practice safe coding
            other_room_id = exit_room.id if exit_room is not None else None
            entry_room.exited(self.id, other_room_id, reason='revert', context_ts=context_ts, context_topic=context_topic)
    else:
      self.enter_room_frd(entry_room, exit_room, context_ts, context_topic)

  def enter_room(self, msg):
    entry_room, exit_room, context_ts, context_topic = self.validate(msg)
    self.enter_room_frd(entry_room, exit_room, context_ts, context_topic)

  def enter_room_frd(self, entry_room, exit_room, context_ts, context_topic):
    if entry_room is not None:
      other_room_id = exit_room.id if exit_room is not None else None
      entry_room.entered(self.id, other_room_id, context_ts=context_ts, context_topic=context_topic)
      self.last_entered_at = datetime.datetime.now()
    if exit_room is not None:
      other_room_id = entry_room.id if entry_room is not None else None
      exit_room.exited(self.id, other_room_id, context_ts=context_ts, context_topic=context_topic)
      self.last_entered_at = datetime.datetime.now()

  def add_suspicious_rooms(self):
    if self.room1:
      self.room1.add_suspicious_room(self.room2)
    if self.room2:
      self.room2.add_suspicious_room(self.room1)

  def update(self, msg, battery=None, should_update_last_seen=True):
    if battery is not None and 'x' in battery:
      # parse meta info out of battery and append to message
      # this can be removed once we migrate all sensors to a more sane packet format
      meta = battery.split('x')
      battery = meta[-1][1:] or None
      meta[-1] = meta[-1][0]
      msg = msg + 'x' + 'x'.join(meta)

    super(DoorSensor, self).update(msg, battery, should_update_last_seen)

  def update_data(self, data):
    if data[0] == 'd':
      if data == 'd1':
        # don't publish the default d1 door state
        if self.data is None: return True
        self.door_opened_at = datetime.datetime.now()
      elif data == 'd0':
        self.door_closed_at = datetime.datetime.now()
        if self.last_entered_at < self.door_opened_at:
          # door just closed and there was no entry since it opened
          self.add_suspicious_rooms()
      elif data == 'd2':
        self.door_ajar_at = datetime.datetime.now()

      # translate d# to readable data val
      possibleStates = ['closed', 'open', 'ajar']
      door_state = possibleStates[int(data[1])]
      return super(DoorSensor, self).update_data(door_state)
    elif data[0].isdigit():
      self.enter_room(data)
    return True

  def initialize_data(self, data):
    # ensure this data was set using the new update_data method
    # and not restoring an old data val. This will temporarily delete
    # door values from HomeKit, but will be added back when the door is used
    if data in ['closed', 'open', 'ajar']:
      return data
    return None

  def categorical_pdf(self, cnt, total, categories=2, modifier=0, total_modifier=0):
    return float(cnt + 1 + modifier)/float(total + categories + total_modifier)

  def validate(self, msg):
    msg_dict = self.parse_msg(msg)
    # fetches mean and variance for all dimensions we care about
    stats = Logger.naive_stats(self.id, msg_dict)

    total = stats['total_valid_count'] + stats['total_invalid_count']
    valid_modifier = invalid_modifier = 0
    if total < 500:
      start_side1 = msg_dict['start_position'] < 32
      end_side1 = msg_dict['end_position'] < 32
      # person ended on same side as starting
      if start_side1 == end_side1:
        invalid_modifier = 100
      # person ends in middle of grid
      # we don't like a start position in middle of grid either, but that could be due to a door opening, so #nojudgement
      if msg_dict['end_position'] >= 24 and msg_dict['end_position'] < 40:
        invalid_modifier += 20
      elif (msg_dict['start_position']/8 < 24 or msg_dict['start_position']/8 >= 40) and \
            abs(msg_dict['end_position']/8 - msg_dict['start_position']/8) > 3:
        valid_modifier = 5

    total_modifier = valid_modifier + invalid_modifier
    valid = math.log(max(self.categorical_pdf(stats['total_valid_count'], total, 2, valid_modifier, total_modifier), 0.1))
    invalid = math.log(max(self.categorical_pdf(stats['total_invalid_count'], total, 2, invalid_modifier, total_modifier), 0.1))

    # are we less confident about bgm or fgm?
    csm_type = 'bgm' if stats['bgm_valid_count'] < stats['fgm_valid_count'] else 'fgm'

    # todo: consider adding a time_to_last_entry dimension that buckets entries by whether they are following another entry by a few ms or not
    # Then we can check whether fast follow entries tend to be valid or not. In some homes, they are. in others, they are not.
    for d in (csm_type, 'hw_ratio', 'noise_size'):
      valid_modifier = invalid_modifier = 0
      weight = 1
      subtotal = stats[d+'_valid_count'] + stats[d+'_invalid_count']
      # add some default weights for each category
      if d == csm_type:
        categories = 5
        if subtotal < 500:
          if msg_dict[csm_type] < 200:
            invalid_modifier = 20
            if msg_dict[csm_type] < 150:
              invalid_modifier = 40
              if msg_dict[csm_type] < 100:
                invalid_modifier = 60
          elif msg_dict[csm_type] > 300:
            if msg_dict['tempc'] is not None and msg_dict['tempc'] < (stats['valid_tempc_avg'] - msg_dict[csm_type]/50):
              # this is actually a negative csm, boost invalid confidence
              invalid_modifier = 30
            else:
              valid_modifier = 20
          elif msg_dict['sensor_conf'] > 80:
            valid_modifier = 20
          elif msg_dict['sensor_conf'] > 60:
            valid_modifier = 5
          else:
            invalid_modifier = 5
      elif d == 'hw_ratio':
        categories = 10 # (0..6)/2 height x width pairings (ignoring 7 as a possibility)
        weight = 0.5
        if subtotal < 500:
          if msg_dict['neighbors'] < 4:
            invalid_modifier = 10
          elif msg_dict['neighbors'] > 5:
            valid_modifier = 20
          if msg_dict['width'] == 0 or msg_dict['width'] >= 6:
            invalid_modifier += 10
          elif msg_dict['width'] > 1 and msg_dict['width'] < 5:
            valid_modifier += 10
          if msg_dict['height'] == 0 or msg_dict['height'] >= 6:
            invalid_modifier += 10
          elif msg_dict['height'] > 1 and msg_dict['height'] < 5:
            valid_modifier += 10
      elif d == 'noise_size':
        if msg_dict['noise_size'] is None or msg_dict['noise_size'] == 0: continue
        categories = 2
        if subtotal < 500:
          if msg_dict['noise_size'] <= msg_dict['blob_size']/5:
            # some noise
            invalid_modifier = 1
            weight = 0.25
          elif msg_dict['noise_size'] <= msg_dict['blob_size']:
            invalid_modifier = 10
            weight = 0.5
          else:
            # lots of noise /o\
            invalid_modifier = 100
            weight = 2

      total_modifier = valid_modifier + invalid_modifier
      total_pdf = self.categorical_pdf(stats[d + '_valid_count'], stats['total_valid_count'], categories, valid_modifier, total_modifier)
      subtotal_pdf = self.categorical_pdf(stats[d + '_valid_count'], subtotal, categories, valid_modifier, total_modifier)
      # we're optimistic scorers... choose the most favorable way to deal with data imbalance
      if total_pdf > subtotal_pdf:
        validc = max(total_pdf, 0.1)
        invalidc = max(self.categorical_pdf(stats[d + '_invalid_count'], stats['total_invalid_count'], categories, invalid_modifier, total_modifier), 0.1)
      else:
        validc = subtotal_pdf
        invalidc = max(self.categorical_pdf(stats[d + '_invalid_count'], subtotal, categories, invalid_modifier, total_modifier), 0.1)

      # don't overweight the final score on a single dimension if both classes are highly unlikely
      validc = validc/(validc+invalidc)
      valid += (math.log(validc)*weight)
      invalid += (math.log(1-validc)*weight)

    msg_dict['valid_score'] = str(valid)
    msg_dict['invalid_score'] = str(invalid)
    msg_dict['confidence'] = min(max(1 - (valid/(valid+invalid)), 0.01), 0.99)
    msg_dict['is_valid'] = msg_dict['confidence'] > 0.5

    entry_room = exit_room = None
    if msg_dict['start_position'] < msg_dict['end_position']:
      direction = 2
      if self.room2 is not None:
        entry_room = self.room2
        msg_dict['entered'] = self.room2.id
      if self.room1 is not None:
        exit_room = self.room1
        msg_dict['exited'] = self.room1.id
    else:
      direction = 1
      if self.room1 is not None:
        entry_room = self.room1
        msg_dict['entered'] = self.room1.id
      if self.room2 is not None:
        exit_room = self.room2
        msg_dict['exited'] = self.room2.id

    if msg_dict['is_valid'] and exit_room is not None and exit_room.count == 0 and not exit_room.hidden and msg_dict['confidence'] < 0.7:
      # need more than 70% confidence if room is already empty
      msg_dict['is_valid'] = False

    if msg_dict['is_valid']:
      if entry_room and exit_room:
        msg_dict['tmpl'] = 'entry_exit'
      elif exit_room is None:
        msg_dict['tmpl'] = 'entry_only'
      elif entry_room is None:
        msg_dict['tmpl'] = 'exit_only'
    elif msg_dict['confidence'] > 0.3 or msg_dict['sensor_conf'] > 80:
      msg_dict['tmpl'] = 'suspicious'

    context_ts = self.write('entry', direction, payload=msg_dict, retain=False)
    context_topic = 'hs/1/com.hiome/' + self.id + '/entry'

    if (msg_dict['confidence'] > 0.3 and msg_dict['confidence'] < 0.7) or msg_dict.get('tmpl') == 'suspicious':
      # this was a close call or sensor had high confidence in an event but it still got ignored
      if msg_dict['is_valid']:
        if exit_room is not None and (entry_room is None or entry_room.count > 0 or entry_room.hidden):
          # entry will be counted, but maybe it shouldn't? Exit room should be suspicious
          # of entry since it is at risk of going negative now
          exit_room.add_suspicious_room(entry_room, self.id, context_ts)
      else:
        if entry_room is not None and (exit_room is None or exit_room.count > 0 or exit_room.hidden):
          # entry will not be counted, but maybe it should? Entry room should be suspicious
          # of exit since it is at risk of going negative now
          entry_room.add_suspicious_room(exit_room, self.id, context_ts)

    if msg_dict['is_valid']:
      return (entry_room, exit_room, context_ts, context_topic)
    else:
      return (None, None, context_ts, context_topic)

  def parse_msg(self, msg):
    meta = msg.split('x')
    if len(meta) > 15: # v0.8.19+, v20.3.20+
      conf = int(meta[1])
      bgm = int(meta[2])
      fgm = int(meta[3])
      startp = int(meta[4])
      endp = int(meta[5])
      history = int(meta[6])
      count = int(meta[7])
      blob_size = int(meta[8])
      neighbors = int(meta[9])
      height = int(meta[10])
      width = int(meta[11])
      max_jump = int(meta[12])
      noise_size = int(meta[13])
      temp_drift = int(meta[14])
      raw_temp = int(meta[15])
      d1_count = d2_count = None
      if neighbors > 8 or height > 7 or width > 7:
        count += blob_size
        neighbors /= 10
        height /= 10
        width /= 10
        noise_size = None
    elif len(meta) > 14: # v20.1.14
      conf = int(meta[1])
      bgm = int(meta[2])
      fgm = int(meta[3])
      startp = int(meta[4])
      endp = int(meta[5])
      history = int(meta[6])
      count = int(meta[7])
      neighbors = int(meta[8])/10
      height = int(meta[9])/10
      width = int(meta[10])/10
      max_jump = int(meta[11])
      temp_drift = int(meta[13])
      blob_size = None
      noise_size = None
      raw_temp = None
      d1_count = d2_count = None
    elif len(meta) > 13:
      try:
        use_new_format = int(meta[0]) > 2
      except ValueError: # a character like "s"
        use_new_format = False

      if use_new_format: # v20.6.10
        # 96x522x476x60x22x3x0x5x15x0x6x2x2x24
        conf = int(meta[0])
        bgm = int(meta[1])
        fgm = int(meta[2])
        startp = int(meta[3])
        endp = int(meta[4])
        d1_count = int(meta[5])
        d2_count = int(meta[6])
        count = int(meta[7])
        blob_size = int(meta[8])
        noise_size = int(meta[9])
        neighbors = int(meta[10])
        height = int(meta[11])
        width = int(meta[12])
        raw_temp = int(meta[13])
        max_jump = None
        temp_drift = None
        if startp < endp:
          history = d2_count - d1_count
        else:
          history = d1_count - d2_count
      else: # v20.3.4
        conf = int(meta[1])
        bgm = int(meta[2])
        fgm = int(meta[3])
        startp = int(meta[4])
        endp = int(meta[5])
        history = int(meta[6])
        count = int(meta[7])
        neighbors = int(meta[8])
        height = int(meta[9])
        width = int(meta[10])
        max_jump = int(meta[11])
        temp_drift = int(meta[12])
        blob_size = None
        noise_size = None
        raw_temp = None
        d1_count = d2_count = None
    else:
      raise ValueError("Unknown message format")

    if width > height:
      ratio = float(width+1)/float(height+1)
    else:
      ratio = float(height+1)/float(width+1)
    ratio = min(ratio, 4) # between 1.0 - 4.0

    return {
      "sensor_conf": conf,
      "bgm": bgm,
      "fgm": fgm,
      "start_position": startp,
      "end_position": endp,
      "history": history,
      "d1_count": d1_count,
      "d2_count": d2_count,
      "count": count,
      "neighbors": neighbors,
      "height": height,
      "width": width,
      "hw_ratio": ratio,
      "max_jump": max_jump,
      "temp_drift": temp_drift,
      "noise_size": noise_size,
      "blob_size": blob_size,
      "tempc": raw_temp,
      "raw": msg
    }
