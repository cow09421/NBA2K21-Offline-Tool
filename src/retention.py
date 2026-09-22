"""Log retention / cleanup for session outputs and read caches.

Protects: project docs, PHASE reports, signatures, historical clean baselines,
and active per-player baselines. Transactions are grouped by process session under
logs|dumps|analysis/sessions/<session_key>/; read artifacts live in read caches.
"""
import sys, json, time
from pathlib import Path
sys.dont_write_bytecode = True
from locator import ROOT
from sessions import (READ_CACHE_LOGS, READ_CACHE_DUMPS, SESSION_LOGS, SESSION_DUMPS,
                      SESSION_ANALYSIS)

RETENTION_DAYS = 14
KEEP_READ = 10
KEEP_SESSIONS = 3
KEEP_TRANSACTIONS = 50

# Paths that must never be auto-removed.
PROTECTED_FILES = [
    ROOT / 'PROJECT_STATUS.md',
    ROOT / 'README.md',
    ROOT / 'analysis' / 'current_signatures.json',
]
SESSION_ROOTS = [SESSION_LOGS, SESSION_DUMPS, SESSION_ANALYSIS]


def _size_of(path):
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())
    return 0


def _read_cache_files():
    files = []
    for d in (READ_CACHE_LOGS, READ_CACHE_DUMPS):
        if d.exists():
            files += [p for p in d.iterdir() if p.is_file()]
    files.sort(key=lambda p: p.name)
    return files


def _all_session_keys():
    keys = set()
    for root in SESSION_ROOTS:
        if root.exists():
            keys.update(d.name for d in root.iterdir() if d.is_dir())
    return sorted(keys)


def _session_mtime(key):
    times = []
    for root in SESSION_ROOTS:
        d = root / key
        if d.exists():
            times.append(d.stat().st_mtime)
    return max(times) if times else 0


def _transaction_results_in(key):
    d = SESSION_LOGS / key
    if not d.exists():
        return []
    return [p for p in d.iterdir() if p.is_file() and p.name.endswith('_result.json')]


def _transaction_count(keys):
    return sum(len(_transaction_results_in(k)) for k in keys)


def _delete_session(key):
    for root in SESSION_ROOTS:
        d = root / key
        if d.exists():
            for f in d.rglob('*'):
                if f.is_file():
                    try: f.unlink()
                    except OSError: pass
            try: d.rmdir()
            except OSError: pass


def _trim_read_cache(keep):
    files = _read_cache_files()
    if len(files) <= keep:
        return 0
    removed = 0
    for p in files[:-keep]:
        try: p.unlink(); removed += 1
        except OSError: pass
    return removed


def summarize():
    total = sum(_size_of(p) for p in [ROOT / 'logs', ROOT / 'dumps', ROOT / 'analysis'] if p.exists())
    keys = _all_session_keys()
    now = time.time()
    cutoff = now - RETENTION_DAYS * 86400
    old = [k for k in keys if _session_mtime(k) < cutoff]
    return dict(status='SUMMARY', size_bytes=total, transactions=_transaction_count(keys),
                sessions=len(keys), old_sessions=len(old),
                read_files=len(_read_cache_files()), retention_days=RETENTION_DAYS,
                keep_read=KEEP_READ, keep_sessions=KEEP_SESSIONS, keep_transactions=KEEP_TRANSACTIONS)


def cleanup(auto=True):
    retention = RETENTION_DAYS if auto else 7
    keep_read = KEEP_READ if auto else 3
    keep_sessions = KEEP_SESSIONS if auto else 1
    cutoff = time.time() - retention * 86400

    removed_read = _trim_read_cache(keep_read)

    keys = _all_session_keys()
    by_mtime = sorted(keys, key=lambda k: _session_mtime(k), reverse=True)
    keep_newest = set(by_mtime[:keep_sessions])
    removed_sessions = []
    remaining_keys = set(keys)

    for key in by_mtime:
        if key in keep_newest:
            continue
        if _session_mtime(key) > cutoff:
            continue
        # Never drop below the write-transaction floor.
        if _transaction_count(remaining_keys) <= KEEP_TRANSACTIONS:
            break
        _delete_session(key)
        remaining_keys.discard(key)
        removed_sessions.append(key)

    result = dict(status='CLEANED', mode='auto' if auto else 'purge',
                  removed_read_files=removed_read, removed_sessions=len(removed_sessions),
                  retention_days=retention, keep_read=keep_read, keep_sessions=keep_sessions,
                  kept_transactions=_transaction_count(remaining_keys),
                  kept_sessions=len(remaining_keys))
    return result


def run(subcommand):
    if subcommand == 'summary':
        return summarize()
    if subcommand == 'auto':
        return cleanup(auto=True)
    if subcommand == 'purge':
        return cleanup(auto=False)
    raise RuntimeError(f'Unknown retention command: {subcommand}')


if __name__ == '__main__':
    sub = sys.argv[1] if len(sys.argv) > 1 else 'summary'
    try:
        print(json.dumps(run(sub), ensure_ascii=True, indent=2))
    except Exception as e:
        print(json.dumps(dict(status='STOPPED', error=str(e)), ensure_ascii=False))
        sys.exit(1)