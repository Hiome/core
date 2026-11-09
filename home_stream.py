# coding=utf-8

import json
import time
import paho.mqtt.client as mqtt
import urllib2

HOMESTREAM_HOST = 'hiome'
HOMESTREAM_PORT = 1883
HOMESTREAM_PROTOCOL = 'hs'
HOMESTREAM_VERSION = '1'

class HomeStream(object):
  def __init__(self, namespace, object_id, on_connect=None, on_message=None, on_deleted=None,
                write_status=None, clean_session=None, client_id=None, on_error=None):
    self.namespace = namespace
    self.object_id = str(object_id)
    self.on_connect = on_connect
    self.on_message = on_message
    self.on_deleted = on_deleted
    self.on_error = on_error
    self.write_status = write_status if write_status is not None else self.on_message is not None or self.on_deleted is not None

    if clean_session is None: clean_session = self.on_message is None
    if not clean_session and client_id is None:
      client_id = self.namespace + ':' + self.object_id
    self.client = mqtt.Client(client_id=client_id, clean_session=clean_session)

    if self.write_status or self.on_connect is not None or self.on_message is not None or self.on_deleted is not None:
      self.client.on_connect = self._on_connect_wrapper
    if self.on_message is not None or self.on_deleted is not None:
      self.client.on_message = self._on_message_wrapper
    if self.write_status:
      self.client.will_set(self._topic_for('connected'), payload=json.dumps(self._payload_for(False)), qos=1, retain=True)

  def read(self, namespace="+", object_id="+", attribute="+", to_namespace=None, to_object_id=None, to_attribute=None,
            after='', until=None, limit=None, reverse=None):
    """ Return the next n messages after ts, optionally filtered by topic """
    if '/' in namespace:
      # topic was provided as a single string, but we need to split the components
      # apart to substitute +/# wildcards with ~/~~ before rejoining
      ns = namespace.split('/', 2)
      namespace = ns[0]
      object_id = ns[1]
      attribute = ns[2]
      if '/' in attribute:
        a = attribute.split('/', 3)
        attribute = a[0]
        to_namespace = a[1]
        to_object_id = a[2]
        to_attribute = a[3]
    # make MQTT wildcards safe for HTTP
    if namespace == '+': namespace = '~'
    if object_id == '+': object_id = '~'
    if to_namespace is not None or to_object_id is not None or to_attribute is not None:
      if to_namespace is None or to_namespace == '+': to_namespace = '~'
      if to_object_id is None or to_object_id == '+': to_object_id = '~'
      if to_attribute is None or to_attribute == '+': to_attribute = '~'
      attribute = self._address_for(to_namespace, to_object_id, to_attribute)
    elif attribute == '+': attribute = '~'
    elif attribute == '#': attribute = '~~'
    topic = self._topic_for(namespace=namespace, object_id=object_id, attribute=attribute)
    url = 'http://'+HOMESTREAM_HOST+':3000/api/1/'+topic+'/'+str(after)
    q = []
    if until is not None: q.append('until='+str(until))
    if limit is not None: q.append('limit='+str(limit))
    if reverse is not None: q.append('reverse='+str(reverse).lower())
    if len(q) > 0: url += '?' + '&'.join(q)

    for attempt in range(5): # retry up to 5 times, in case server is still booting up
      try: # fetch url
        rsp = json.load(urllib2.urlopen(url))
      except urllib2.URLError: # network failure
        if attempt == 4: # we're out of lives
          raise
        else: # wait 2+ seconds before trying again
          time.sleep(2 + attempt)
      else: # got a response!
        break

    return map(lambda r: HomeStreamMessage(**r), rsp)

  def write(self, attribute, val, payload={}, retain=True, qos=1, author=None):
    payload = self._payload_for(val, payload=payload)
    self.client.publish(self._topic_for(attribute, object_id=author), payload=json.dumps(payload), qos=qos, retain=retain)
    return payload['ts']

  def write_to(self, namespace, object_id, attribute, val, payload={}, author=None):
    return self.write(self._address_for(namespace, object_id, attribute), val, payload=payload, retain=False, author=author)

  def erase(self, attribute, author=None):
    self.client.publish(self._topic_for(attribute, object_id=author), payload=None, qos=1, retain=True)

  def subscribe(self, namespace="+", object_id="+", attribute="#"):
    if '/' in namespace:
      ns = namespace.split('/', 2)
      namespace = ns[0]
      object_id = ns[1]
      attribute = ns[2]
    self.client.subscribe(self._topic_for(attribute, namespace=namespace, object_id=object_id), qos=1)

  def represent(self, object_id="+", attribute="+"):
    if object_id == "+" and attribute == "+":
      # If you stand for nothing, what'll you fall for?
      raise ValueError("You cannot represent everything. Specify an object_id and/or attribute")
    self.subscribe(attribute=self._address_for(self.namespace, object_id, attribute))

  def listen_forever(self):
    self.client.connect(HOMESTREAM_HOST, HOMESTREAM_PORT, 60)
    self.client.loop_forever()

  def listen_async(self):
    self.client.connect_async(HOMESTREAM_HOST, HOMESTREAM_PORT, 60)
    self.client.loop_start()
    return self # allowing chaining

  def stop_listening_async(self):
    self.client.disconnect()
    self.client.loop_stop()

  def _topic_for(self, attribute, namespace=None, object_id=None):
    return '/'.join([HOMESTREAM_PROTOCOL, HOMESTREAM_VERSION, (namespace or self.namespace), (object_id or self.object_id), attribute]).lower()

  def _address_for(self, targetNamespace, targetId, targetAttr):
    return '/'.join(['to', targetNamespace, targetId, targetAttr])

  def _payload_for(self, val, payload={}):
    payload["val"] = val
    payload["ts"] = int(round(time.time()*1000.0))
    return payload

  def _handle_exception(self, e):
    if self.on_error is not None:
      self.on_error(e)
    else:
      raise e

  def _on_connect_wrapper(self, client, userdata, flags, rc):
    try:
      if self.write_status:
        self.write('connected', True)
      if self.on_message is not None:
        self.represent(self.object_id)
      if self.on_connect is not None:
        self.on_connect(self, rc)
    except Exception as e:
      self._handle_exception(e)

  def _on_message_wrapper(self, client, userdata, payload):
    try:
      # parse json body
      try:
        msg = HomeStreamMessage(topic=payload.topic, payload=payload.payload)
      except (ValueError, KeyError):
        # payload must be a valid json message
        return

      # don't parse empty messages
      if not msg.payload:
        if self.on_deleted is not None:
          self.on_deleted(self, msg)
        return
      elif self.on_message is None:
        # we only registed an on_deleted callback, so stop parsing
        return

      # pass it to callback
      self.on_message(self, msg)
    except Exception as e:
      self._handle_exception(e)

class HomeStreamMessage(object):
  def __init__(self, topic, payload=None, data=None, namespace=None, object_id=None, attribute=None,
                to_namespace=None, to_object_id=None, to_attribute=None, **kwargs):
    self.topic = topic
    if attribute is None:
      # skipped if loading from database where we have all these components already
      tp = topic.split('/', 4)
      namespace = tp[2]
      object_id = tp[3]
      attribute = tp[4]
      if attribute.startswith('to/'):
        attribute, to_namespace, to_object_id, to_attribute = attribute.split('/', 3)
    self.namespace = namespace
    self.object_id = object_id
    self.attribute = attribute
    self.to_namespace = to_namespace
    self.to_object_id = to_object_id
    self.to_attribute = to_attribute
    self.payload = payload
    self.data = data
    if self.payload and self.data is None:
      self.data = json.loads(self.payload)
    if self.data:
      self.val = self.data['val']
      self.ts = self.data['ts']
      if self.payload is None:
        self.payload = json.dumps(self.data)
    else:
      self.val = self.ts = None

  def context_ts(self):
    return self.data.get('context_ts', self.ts)

  def context_topic(self):
    return self.data.get('context_topic', self.topic)

  def __repr__(self):
    return '<HomeStreamMessage topic: ' + self.topic + ', val: ' + str(self.val) + ', ts: ' + str(self.ts) + '>'
