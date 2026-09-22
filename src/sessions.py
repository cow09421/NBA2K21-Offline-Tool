"""Path management for session-grouped outputs, read caches, and filetime helpers."""
import sys, datetime
from pathlib import Path
sys.dont_write_bytecode = True
from locator import ROOT

READ_CACHE_LOGS = ROOT / 'logs' / 'read_cache'
READ_CACHE_DUMPS = ROOT / 'dumps' / 'read_cache'
SESSION_LOGS = ROOT / 'logs' / 'sessions'
SESSION_DUMPS = ROOT / 'dumps' / 'sessions'
SESSION_ANALYSIS = ROOT / 'analysis' / 'sessions'

FILETIME_EPOCH_DIFF = 116444736000000000  # 100ns units between 1601-01-01 and 1970-01-01


def filetime_to_utc(ft):
    seconds = (ft - FILETIME_EPOCH_DIFF) // 10_000_000
    return datetime.datetime.utcfromtimestamp(seconds)


def session_key(created, pid):
    return f"{filetime_to_utc(created):%Y%m%dT%H%M%S}_{pid}"


def session_dirs(created, pid):
    key = session_key(created, pid)
    return (SESSION_LOGS / key, SESSION_DUMPS / key, SESSION_ANALYSIS / key)


def read_cache_dirs():
    return READ_CACHE_LOGS, READ_CACHE_DUMPS


def ensure(path):
    path.mkdir(parents=True, exist_ok=True)
    return path