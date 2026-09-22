"""Per-selected-player session baseline: capture/load for ANY highlighted MyLEAGUE player.

Not bound to LeBron. Each baseline is keyed by (process creation time + player identity +
player address + team/slot + Face ID), so a game restart naturally creates a new baseline
and old ones remain as historical records.
"""
import sys, json, hashlib
from pathlib import Path
sys.dont_write_bytecode = True
from locator import ROOT
from clean_baseline import process_created, persist_new, digest, utc

BASELINE_DIR = ROOT / 'dumps' / 'player_baselines'

MAX_BADGE_TEMPLATE = bytes.fromhex(
    '92 91 91 91 91 90 92 90 93 49 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 04 24 E4')


def _member(report):
    members = report.get('membership') or []
    return members[0] if members else {}


def identity_key(report, created):
    m = _member(report)
    canon = '|'.join([str(created), str(report.get('player_address')), str(report.get('name')),
                      str(report.get('face_id')), str(m.get('team_index')), str(m.get('slot')),
                      str(m.get('team_name'))])
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()[:16]


def paths(key):
    d = BASELINE_DIR / key
    return d, d / 'meta.json', d / 'structure.bin', d / 'abilities.bin', d / 'badges.bin'


def validate_capturable(report, data):
    if len(data) != 0x4e8:
        raise RuntimeError('Player snapshot must contain exactly 0x4E8 bytes')
    abilities = data[0x41b:0x453]
    badges = data[0x4b7:0x4dc]
    if abilities == bytes([255]) * 56:
        raise RuntimeError('目前球員能力已是全110（疑為工具先前寫入）；沒有乾淨基準。請先切換正確球員再讀取，或確認存檔。')
    if badges == MAX_BADGE_TEMPLATE:
        raise RuntimeError('目前球員徽章已是滿徽章模板（疑為工具先前寫入）；沒有乾淨基準。請先切換正確球員再讀取，或確認存檔。')


def capture_or_load(r, report, data, created, require_existing=False):
    """Return (meta, original_structure_bytes, baseline_dir, mode).

    - require_existing=True (write/restore): require a baseline for the current player,
      otherwise refuse with a clear message.
    - require_existing=False (read): capture the clean baseline on first sight of this
      identity; never overwrite an existing baseline.
    """
    key = identity_key(report, created)
    d, meta_p, bin_p, ab_p, bd_p = paths(key)
    if all(p.exists() for p in [meta_p, bin_p, ab_p, bd_p]):
        meta = json.loads(meta_p.read_text(encoding='utf-8'))
        original = bin_p.read_bytes()
        if digest(original) != meta['player_sha256']:
            raise RuntimeError('Baseline checksum mismatch')
        if ab_p.read_bytes() != original[0x41b:0x453] or bd_p.read_bytes() != original[0x4b7:0x4dc]:
            raise RuntimeError('Baseline block copies disagree')
        return meta, original, d, 'LOADED'
    if require_existing:
        raise RuntimeError('目前高亮球員尚無已建立的 baseline；請先按「讀取目前球員」建立後再操作。')
    validate_capturable(report, data)
    meta = dict(schema=2, captured_utc=utc(), process_creation_filetime=created,
                player_sha256=digest(data), abilities_sha256=digest(data[0x41b:0x453]),
                badges_sha256=digest(data[0x4b7:0x4dc]), read_report=report,
                structure_size=hex(len(data)))
    d.mkdir(parents=True, exist_ok=True)
    persist_new(bin_p, data)
    persist_new(ab_p, data[0x41b:0x453])
    persist_new(bd_p, data[0x4b7:0x4dc])
    persist_new(meta_p, json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8'))
    return meta, data, d, 'CAPTURED'