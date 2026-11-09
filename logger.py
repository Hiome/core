# coding=utf-8

import psycopg2
import psycopg2.extras

class Logger:
  """ Logs all agent activity in databases for persistence and analysis. """

  @classmethod
  def rooms(klass):
    """ Returns all known rooms """
    with psycopg2.connect("") as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as db:
        db.execute("SELECT * FROM rooms")
        return db.fetchall()

  @classmethod
  def create_room(klass, room_id, name, hidden, occupancy_count):
    with psycopg2.connect("") as conn:
      with conn.cursor() as db:
        db.execute("INSERT INTO rooms (id, name, hidden, occupancy_count) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (room_id, name, hidden, occupancy_count))

  @classmethod
  def delete_room(klass, room_id):
    with psycopg2.connect("") as conn:
      with conn.cursor() as db:
        db.execute("DELETE FROM rooms WHERE id = %s", (room_id,))

  @classmethod
  def update_occupancy_count(klass, room_id, count):
    with psycopg2.connect("") as conn:
      with conn.cursor() as db:
        db.execute("UPDATE rooms SET occupancy_count = %s WHERE id = %s", (count, room_id))

  @classmethod
  def hide_room(klass, room_id, hidden):
    with psycopg2.connect("") as conn:
      with conn.cursor() as db:
        db.execute("UPDATE rooms SET hidden = %s WHERE id = %s", (hidden, room_id))

  @classmethod
  def name_room(klass, room_id, name):
    with psycopg2.connect("") as conn:
      with conn.cursor() as db:
        db.execute("UPDATE rooms SET name = %s WHERE id = %s", (name, room_id))

  @classmethod
  def sensors(klass):
    """ Returns all known room mappings """
    with psycopg2.connect("") as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as db:
        db.execute("SELECT * FROM sensors")
        return db.fetchall()

  @classmethod
  def create_sensor(klass, sensor_id, name, sensor_type, room_id, version):
    with psycopg2.connect("") as conn:
      with conn.cursor() as db:
        db.execute("""
          INSERT INTO sensors (id, name, type, room_id, version) VALUES (%s, %s, %s, %s, %s)
          ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name, type = EXCLUDED.type, room_id = EXCLUDED.room_id, version = EXCLUDED.version
        """, (sensor_id, name, sensor_type, room_id, version))

  @classmethod
  def delete_sensor(klass, device_id):
    with psycopg2.connect("") as conn:
      with conn.cursor() as db:
        db.execute("""
          UPDATE sensors SET
            room_id = NULL,
            name = NULL,
            data = NULL,
            battery = NULL,
            last_seen = NULL,
            sensitivity = NULL
          WHERE id = %s
        """, (device_id,))

  @classmethod
  def name_sensor(klass, device_id, name):
    with psycopg2.connect("") as conn:
      with conn.cursor() as db:
        db.execute("UPDATE sensors SET name = %s WHERE id = %s", (name, device_id))

  @classmethod
  def put_sensor_in_room(klass, device_id, room_id):
    with psycopg2.connect("") as conn:
      with conn.cursor() as db:
        db.execute("UPDATE sensors SET room_id = %s WHERE id = %s", (room_id, device_id))

  @classmethod
  def save_sensor(klass, sensor_id, data, battery, version, last_seen):
    with psycopg2.connect("") as conn:
      with conn.cursor() as db:
        db.execute("""
          UPDATE sensors SET
            data = %s,
            battery = %s,
            version = %s,
            last_seen = coalesce(%s, last_seen)
          WHERE id = %s
        """, (data, battery, version, last_seen, sensor_id))

  @classmethod
  def validate_entry(klass, sensor_id, ts, valid):
    with psycopg2.connect("") as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as db:
        db.execute("SELECT direction, is_valid, corrected FROM entries WHERE sensor_id = %s AND ts = %s", (sensor_id, ts))
        results = db.fetchone()
        db.execute("UPDATE entries SET is_valid = %s, corrected = TRUE WHERE sensor_id = %s AND ts = %s", (valid, sensor_id, ts))
        return results

  @classmethod
  def revert_entry(klass, sensor_id, ts):
    with psycopg2.connect("") as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as db:
        db.execute("""
          UPDATE entries SET
            is_valid = NOT is_valid
          WHERE sensor_id = %s AND ts = %s AND corrected IS FALSE
          RETURNING direction, is_valid
        """, (sensor_id, ts))
        return db.fetchone()

  @classmethod
  def occupancy_events_for_context(klass, ts, topic):
    with psycopg2.connect("") as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as db:
        db.execute("""
          SELECT object_id, payload AS data
          FROM events WHERE
            context_ts = %s AND context_topic = %s AND namespace = 'com.hiome' AND attribute = 'occupancy'
        """, (ts, topic))
        return db.fetchall()

  @classmethod
  def naive_stats(klass, sensor_id, msg):
    with psycopg2.connect("") as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as db:
        db.execute("""
          WITH filtered_entries AS (
            SELECT is_valid, corrected, bgm, fgm, neighbors, height, width, noise_size, blob_size, tempc
            FROM entries WHERE
              sensor_id = %(sensor_id)s AND
              -- only count entries that started and ended in the same sector
              (start_position/16 * 10 + (start_position %% 8)/4) = (%(start_pos)s/16 * 10 + (%(start_pos)s %% 8)/4) AND
              (end_position/16 * 10 + (end_position %% 8)/4) = (%(end_pos)s/16 * 10 + (%(end_pos)s %% 8)/4)
          ), avgs AS (
            SELECT avg(tempc) as valid_tempc FROM filtered_entries WHERE is_valid is true
          ), totals AS (
            SELECT
              SUM(case when is_valid = TRUE then case when corrected = TRUE then 5 else 1 end else 0 end) AS valid_count,
              SUM(case when is_valid = FALSE then case when corrected = TRUE then 5 else 1 end else 0 end) AS invalid_count
            FROM filtered_entries
          ), bgm AS (
            SELECT
              SUM(case when is_valid = TRUE then case when corrected = TRUE then 5 else 1 end else 0 end) AS valid_count,
              SUM(case when is_valid = FALSE then case when corrected = TRUE then 5 else 1 end else 0 end) AS invalid_count
            FROM filtered_entries, avgs WHERE
              bgm/100 = %(bgm)s/100 AND
              CASE
                WHEN %(tempc)s < (avgs.valid_tempc - %(bgm)s/50) THEN tempc < (avgs.valid_tempc - %(bgm)s/50)
                WHEN %(tempc)s > (avgs.valid_tempc + %(bgm)s/50) THEN tempc > (avgs.valid_tempc + %(bgm)s/50)
                ELSE TRUE
              END
          ), fgm AS (
            SELECT
              SUM(case when is_valid = TRUE then case when corrected = TRUE then 5 else 1 end else 0 end) AS valid_count,
              SUM(case when is_valid = FALSE then case when corrected = TRUE then 5 else 1 end else 0 end) AS invalid_count
            FROM filtered_entries, avgs WHERE
              fgm/100 = %(fgm)s/100 AND
              CASE
                WHEN %(tempc)s < (avgs.valid_tempc - %(fgm)s/50) THEN tempc < (avgs.valid_tempc - %(fgm)s/50)
                WHEN %(tempc)s > (avgs.valid_tempc + %(fgm)s/50) THEN tempc > (avgs.valid_tempc + %(fgm)s/50)
                ELSE TRUE
              END
          ), hw_ratio AS (
            SELECT
              SUM(case when is_valid = TRUE then case when corrected = TRUE then 5 else 1 end else 0 end) AS valid_count,
              SUM(case when is_valid = FALSE then case when corrected = TRUE then 5 else 1 end else 0 end) AS invalid_count
            FROM filtered_entries WHERE
              -- only count entries with same neighbors, height, and width
              neighbors/2 = %(neighbors)s/2 AND
              CASE
                WHEN %(height)s < %(width)s THEN
                  CASE
                    WHEN height < width THEN height/2 = %(height)s/2 AND width/2 = %(width)s/2
                    ELSE width/2 = %(height)s/2 AND height/2 = %(width)s/2
                  END
                ELSE
                  CASE
                    WHEN height < width THEN height/2 = %(width)s/2 AND width/2 = %(height)s/2
                    ELSE width/2 = %(width)s/2 AND height/2 = %(height)s/2
                  END
              END
          ), noise_size AS (
            SELECT
              SUM(case when is_valid = TRUE then case when corrected = TRUE then 5 else 1 end else 0 end) AS valid_count,
              SUM(case when is_valid = FALSE then case when corrected = TRUE then 5 else 1 end else 0 end) AS invalid_count
            FROM filtered_entries WHERE
              CASE
                -- bucket noise_size into 4 possible categories on the fly
                WHEN %(noise_size)s = 0 THEN noise_size = 0
                WHEN %(noise_size)s <= %(blob_size)s/5 THEN noise_size > 0 AND noise_size <= blob_size/5
                WHEN %(noise_size)s <= %(blob_size)s THEN noise_size > blob_size/5 AND noise_size <= blob_size
                ELSE noise_size > blob_size
              END
          )
          SELECT
            coalesce(totals.valid_count, 0) as total_valid_count,
            coalesce(totals.invalid_count, 0) as total_invalid_count,
            coalesce(bgm.valid_count, 0) as bgm_valid_count,
            coalesce(bgm.invalid_count, 0) as bgm_invalid_count,
            coalesce(fgm.valid_count, 0) as fgm_valid_count,
            coalesce(fgm.invalid_count, 0) as fgm_invalid_count,
            coalesce(hw_ratio.valid_count, 0) as hw_ratio_valid_count,
            coalesce(hw_ratio.invalid_count, 0) as hw_ratio_invalid_count,
            coalesce(noise_size.valid_count, 0) as noise_size_valid_count,
            coalesce(noise_size.invalid_count, 0) as noise_size_invalid_count,
            coalesce(avgs.valid_tempc, 0) as valid_tempc_avg
          FROM totals, bgm, fgm, hw_ratio, noise_size, avgs
        """, {'sensor_id': sensor_id, 'start_pos': msg['start_position'], 'end_pos': msg['end_position'],
              'neighbors': msg['neighbors'], 'height': msg['height'], 'width': msg['width'], 'bgm': msg['bgm'], 'fgm': msg['fgm'],
              'noise_size': msg['noise_size'], 'blob_size': msg['blob_size'], 'tempc': msg['tempc']})
        return db.fetchone()
