# coding=utf-8

def parse_bool(b, default=None):
  if isinstance(b, bool): return b
  if str(b).lower() in ['true', '1', 't', 'y', 'yes']: return True
  if str(b).lower() in ['false', '0', 'f', 'n', 'no']: return False
  return default