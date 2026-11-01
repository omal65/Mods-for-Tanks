# -*- coding: utf-8 -*-
#
# MarkBattle v0.9 - серверные пороги отметок + дисковый кэш и очередь для таблицы.
#
from __future__ import print_function

import json
import os
import time

import BigWorld

from . import _log, CONF_DIR

CACHE_FILE = CONF_DIR + '/moe_thresholds.json'
CACHE_TIME = 60.0 * 30          # 30 минут для живого запроса
DISK_TTL = 60.0 * 60.0 * 12     # 12 часов для дискового кэша таблицы
REQUEST_MIN_DELAY = 0.65

PERCENT_BY_INDEX = [0, 20, 40, 55, 65, 75, 85, 95, 100]
TARGET_PERCENTS = (0, 20, 40, 55, 65, 75, 85, 95, 100)

_cache = {}                     # intCD (int) -> {'time': float, 'ts': float, 'data': {pct(int): val(int)}}
_pending = {}                   # intCD -> время начала запроса
PENDING_TIMEOUT = 10.0
_last_request_time = 0.0
_on_ready_callback = None
_updated_time_str = u''

_queue = []                     # очередь intCD для фоновой подкачки таблицы
_queue_running = False
_save_scheduled = False
_bulk_fetched = False


def init_cache():
    """Загружает сохранённые пороги с диска при старте."""
    global _updated_time_str
    try:
        if os.path.isfile(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                _updated_time_str = unicode(raw.get('updated_str', u'') or u'')
                items = raw.get('items', {})
                now_bw = BigWorld.time()
                now_ts = time.time()
                for k, v in items.items():
                    try:
                        int_cd = int(k)
                        ts = float(v.get('ts', 0) or 0)
                        data_raw = v.get('data', {})
                        data = {}
                        for pk, pv in data_raw.items():
                            data[int(pk)] = int(pv)
                        if data:
                            # Если дисковая запись свежая (< DISK_TTL), даём ей базовый запас времени
                            bw_t = now_bw if (now_ts - ts < DISK_TTL) else -9999.0
                            _cache[int_cd] = {'time': bw_t, 'ts': ts, 'data': data}
                    except Exception:
                        continue
                _log(u'[MOE] disk cache loaded: %d vehicles' % len(_cache))
    except Exception as e:
        _log(u'[MOE] init_cache failed: %r' % e)


def _schedule_save():
    global _save_scheduled
    if _save_scheduled:
        return
    _save_scheduled = True
    BigWorld.callback(2.0, _save_cache_to_disk)


def _save_cache_to_disk():
    global _save_scheduled, _updated_time_str
    _save_scheduled = False
    try:
        if not os.path.exists(CONF_DIR):
            os.makedirs(CONF_DIR)
        _updated_time_str = unicode(time.strftime('%H:%M:%S'))
        items = {}
        for int_cd, entry in _cache.items():
            data = entry.get('data')
            if data:
                items[str(int_cd)] = {
                    'ts': entry.get('ts', time.time()),
                    'data': data,
                }
        payload = {
            'updated_str': _updated_time_str,
            'items': items,
        }
        with open(CACHE_FILE, 'w') as f:
            json.dump(payload, f)
    except Exception as e:
        _log(u'[MOE] save disk cache failed: %r' % e)


def get_updated_time_str():
    if _updated_time_str:
        return _updated_time_str
    return unicode(time.strftime('%H:%M:%S'))


def set_ready_callback(cb):
    global _on_ready_callback
    _on_ready_callback = cb


def get_thresholds(int_cd):
    if int_cd <= 0:
        return None
    entry = _cache.get(int(int_cd))
    if entry is None:
        return None
    return entry.get('data')


def has_fresh_thresholds(int_cd):
    entry = _cache.get(int(int_cd))
    if entry is None:
        return False
    now_ts = time.time()
    return (now_ts - float(entry.get('ts', 0) or 0)) < DISK_TTL


def enqueue_batch(int_cds, priority=False):
    """Ставит список танков в фоновую очередь опроса CMD_GET_VEHICLE_DAMAGE_DISTRIBUTION.
    Нужно для автоматического заполнения таблицы без перегрузки сервера."""
    global _queue
    added = 0
    for cd in int_cds:
        cd = int(cd)
        if cd <= 0:
            continue
        if has_fresh_thresholds(cd):
            continue
        if cd in _queue:
            if priority:
                try:
                    _queue.remove(cd)
                    _queue.insert(0, cd)
                except Exception:
                    pass
            continue
        if priority:
            _queue.insert(0, cd)
        else:
            _queue.append(cd)
        added += 1
    if added > 0 and not _queue_running:
        _pump_queue()


def _pump_queue():
    global _queue_running
    if not _queue:
        _queue_running = False
        return
    _queue_running = True
    while _queue:
        next_cd = _queue.pop(0)
        if not has_fresh_thresholds(next_cd):
            ensure_requested(next_cd, force=True)
            BigWorld.callback(REQUEST_MIN_DELAY + 0.1, _pump_queue)
            return
    _queue_running = False


def ensure_requested(int_cd, force=False):
    global _last_request_time
    if int_cd <= 0:
        return
    int_cd = int(int_cd)
    now = BigWorld.time()
    entry = _cache.get(int_cd)
    if entry is not None and not force:
        if now - entry.get('time', -9999.0) < CACHE_TIME:
            return
    started = _pending.get(int_cd)
    if started is not None and now - started < PENDING_TIMEOUT:
        return
    if now - _last_request_time < REQUEST_MIN_DELAY:
        delay = REQUEST_MIN_DELAY - (now - _last_request_time)
        BigWorld.callback(delay, lambda: ensure_requested(int_cd, force))
        return
    _last_request_time = now
    _pending[int_cd] = now
    _do_request(int_cd)


def _do_request(int_cd):
    try:
        from AccountCommands import CMD_GET_VEHICLE_DAMAGE_DISTRIBUTION
    except ImportError:
        _pending.pop(int_cd, None)
        _log(u'[MOE] CMD_GET_VEHICLE_DAMAGE_DISTRIBUTION not available')
        return
    player = BigWorld.player()
    if player is None or not hasattr(player, '_doCmdInt'):
        _pending.pop(int_cd, None)
        return
    try:
        player._doCmdInt(
            CMD_GET_VEHICLE_DAMAGE_DISTRIBUTION,
            int_cd,
            lambda requestID, responseID, errorStr, ext=None:
                _on_response(int_cd, errorStr, ext))
    except Exception as e:
        _log(u'[MOE] _doCmdInt failed: %r' % e)
        _pending.pop(int_cd, None)


def _on_response(int_cd, error_str, ext):
    _pending.pop(int_cd, None)
    if error_str:
        return
    if not ext:
        return
    raw = ext.get('damageBetterThanNPercent')
    if not raw:
        return
    try:
        values = list(raw)
    except Exception:
        return
    result = {}
    for i, pct in enumerate(PERCENT_BY_INDEX):
        if i < len(values):
            try:
                v = int(values[i])
                if v > 0:
                    result[pct] = v
            except Exception:
                pass
    if not result:
        return
    _cache[int(int_cd)] = {
        'time': BigWorld.time(),
        'ts': time.time(),
        'data': result,
    }
    _schedule_save()
    if _on_ready_callback is not None:
        try:
            _on_ready_callback(int(int_cd), result)
        except Exception as e:
            _log(u'[MOE] ready callback failed: %r' % e)