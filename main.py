#!/usr/bin/python
# coding=utf-8

## Gateway Service
# 
# Interfaces with Hiome sensors and manages sensor state

from home_stream_wrapper import HomeStreamWrapper as HomeStream
from room_manager import RoomManager
from logger import Logger
import sentry_sdk

sentry_sdk.init()

last_msg_store = {}

def on_connect(client, rc):
  # register API commands we understand
  client.subscribe('com.hiome', '1', 'message')
  client.subscribe('com.hiome', 'updater', 'updating')
  client.represent(attribute='occupancy')
  client.represent(attribute='entry')
  client.represent(attribute='version')
  client.represent(attribute='hidden')
  client.represent(attribute='name')
  client.represent(attribute='room')
  client.represent(attribute='connected')
  client.represent(attribute='activity_expired')
  client.represent(attribute='occupancy_expired')
  client.represent(attribute='device_online_expired')

def on_message(client, msg):
  global last_msg_store
  if msg.object_id == '1':
    parse_input(client, msg.val)
  elif msg.object_id == 'updater' and msg.attribute == 'updating':
    last_msg_store = {}
  elif msg.attribute == 'to':
    parse_command(client, msg)

# HiomeRF API
def parse_input(client, msg):
  # attempt to filter out noise from input
  msg = ''.join([s for s in msg if s in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.:;-+'])
  senderid, message, voltage = msg[:-1].split(';')
  msg_id = int(msg[-1])

  try:
    last_msg = last_msg_store[senderid]
  except KeyError:
    last_msg = '0'

  # if this is a duplicate packet, ignore it
  if last_msg == msg and message[0] != 'V':
    # sentry_sdk.capture_message('duplicate packet ' + str(msg_id) + ' for sensor ' + senderid)
    return

  device = room_manager.find_device(senderid)

  if device is None:
    # should only happen if we forgot to update manifest
    sentry_sdk.capture_message('unknown device ' + senderid)
    return

  device.update(message, voltage)

  if msg_id > 0:
    last_id = int(last_msg[-1])
    if last_id > 0 and message[0] != 'V':
      next_id = last_id + 1 if last_id < 9 else 1
      if msg_id != next_id:
        # packet sequence number did not increase sequentially like we expected
        # device.write('error', 'missed_packet', {
        #   'received_packet': msg_id,
        #   'expected_packet': next_id
        # }, retain=False)
        sentry_sdk.capture_message('missed packet between ' + str(next_id) + ' and ' + str(msg_id) + ' for sensor ' + senderid)
        # if sender was a door sensor, get suspicious of that door
        if device.type == 'door': device.add_suspicious_rooms()

  last_msg_store[senderid] = msg

# user/services API
def parse_command(client, msg):
  if msg.object_id == 'timer' and msg.namespace == 'com.hiome':
    if msg.to_attribute == 'activity_expired':
      if msg.to_object_id in room_manager.rooms:
        room_manager.rooms[msg.to_object_id].clear_occupancy()
    elif msg.to_attribute == 'occupancy_expired':
      if msg.to_object_id in room_manager.rooms:
        room_manager.rooms[msg.to_object_id].decay_occupancy()
    elif msg.to_attribute == 'device_online_expired':
      if msg.to_object_id in room_manager.devices:
        room_manager.devices[msg.to_object_id].mark_offline()

  elif msg.to_attribute == 'occupancy':
    if msg.val is None or msg.val == '': return
    if msg.to_object_id in room_manager.rooms:
      room_manager.rooms[msg.to_object_id].override_count(int(msg.val))

  elif msg.to_attribute == 'entry':
    if msg.to_object_id in room_manager.devices:
      room_manager.devices[msg.to_object_id].revert_entry(int(msg.data['entry_ts']), msg.val)

  elif msg.to_attribute == 'version':
    if msg.to_object_id in room_manager.devices:
      if room_manager.devices[msg.to_object_id].update_version(msg.val):
        room_manager.devices[msg.to_object_id].save()

  elif msg.to_attribute == 'hidden':
    # update hidden state of rooms
    if msg.to_object_id in room_manager.rooms:
      room_manager.rooms[msg.to_object_id].hide_room(msg.val)

  elif msg.to_attribute == 'name':
    # update name of object
    if msg.to_object_id in room_manager.rooms:
      room_manager.rooms[msg.to_object_id].update_name(msg.val)
    elif msg.to_object_id in room_manager.devices:
      room_manager.devices[msg.to_object_id].update_name(msg.val)

  elif msg.to_attribute == 'room':
    # update sensor room id
    if msg.to_object_id in room_manager.devices:
      room_manager.devices[msg.to_object_id].update_room_id(msg.val)

  elif msg.to_attribute == 'connected' and msg.val == 'delete':
    # delete object
    if msg.to_object_id in room_manager.rooms:
      room_manager.delete_room(msg.to_object_id)
    elif msg.to_object_id in room_manager.devices:
      room_manager.delete_device(msg.to_object_id)

  elif msg.to_object_id == 'gateway':
    if msg.to_attribute == 'create_room':
      room_manager.create_room(
        msg.val,
        msg.data['name'],
        count=msg.data.get('occupancy', 0),
        hidden=msg.data.get('hidden', False),
        persist=True
      )
    elif msg.to_attribute == 'create_sensor':
      room_manager.create_device(
        msg.val,
        msg.data['type'],
        name=msg.data.get('name'),
        room_id=msg.data.get('room_id'),
        version=msg.data.get('version'),
        persist=True
      )

hs = HomeStream('com.hiome', 'gateway', on_connect=on_connect, on_message=on_message)
room_manager = RoomManager(hs)
hs.listen_forever()
