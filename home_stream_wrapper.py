# coding=utf-8

import psycopg2
import psycopg2.extras
import sentry_sdk
from home_stream import HomeStream, HomeStreamMessage

class HomeStreamWrapper(HomeStream):
  def __init__(self, *args, **kwargs):
    kwargs['on_error'] = sentry_sdk.capture_exception
    super(HomeStreamWrapper, self).__init__(*args, **kwargs)

  def read(self, namespace="+", object_id="+", attribute="+", to_namespace=None, to_object_id=None, to_attribute=None,
            after='', until=None, limit=1000, reverse=False):
    if after == '':
      return self._read_latest(namespace, object_id, attribute)
    return self._read(namespace, object_id, attribute, to_namespace, to_object_id, to_attribute, after, until, limit, reverse)

  def _read_latest(self, namespace, object_id, attribute):
    q = """SELECT DISTINCT ON (topic) topic, namespace, object_id, attribute, to_namespace, to_object_id, to_attribute, payload AS data
            FROM events WHERE """
    t = ()
    if attribute != '+' and attribute != '#':
      q += 'attribute = %s '
      t += (attribute,)
    else:
      q += "attribute <> 'to' "
    if namespace != '+':
      q += 'AND namespace = %s '
      t += (namespace,)
    if object_id != '+':
      q += 'AND object_id = %s '
      t += (object_id,)

    q += "ORDER BY topic, ts DESC"
    with psycopg2.connect("") as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as db:
        db.execute(q, t)
        rsp = db.fetchall()
        return map(lambda r: HomeStreamMessage(**r), rsp)

  def _read(self, namespace, object_id, attribute, to_namespace, to_object_id, to_attribute, after, until, limit, reverse):
    if until is None:
      # default to current time
      until = int(round(time.time()*1000.0))

    q = """SELECT topic, namespace, object_id, attribute, to_namespace, to_object_id, to_attribute, payload AS data
            FROM events WHERE ts > %s AND ts <= %s """
    t = (after, until)
    if namespace != '+':
      q += 'AND namespace = %s '
      t += (namespace,)
    if object_id != '+':
      q += 'AND object_id = %s '
      t += (object_id,)
    if to_namespace is None:
      if attribute == '+':
        q += "AND attribute <> 'to' "
      elif attribute != '#':
        q += 'AND attribute = %s '
        t += (attribute,)
    else:
      q += "AND attribute = 'to' "
      if to_namespace != '+':
        q += 'AND to_namespace = %s '
        t += (to_namespace,)
      if to_object_id != '+':
        q += 'AND to_object_id = %s '
        t += (to_object_id,)
      if to_attribute != '+':
        q += 'AND to_attribute = %s '
        t += (to_attribute,)

    q += "ORDER BY ts %s LIMIT %s"
    t += (reverse, limit,)
    with psycopg2.connect("") as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as db:
        db.execute(q, t)
        rsp = db.fetchall()
        return map(lambda r: HomeStreamMessage(**r), rsp)
