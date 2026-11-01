# -*- coding: utf-8 -*-
#
# MarkBattle v0.7 - расчёты (формула WotStat + дельта прошлого боя).
#
from __future__ import print_function

ROMAN_LEVELS = {
    1: u'I', 2: u'II', 3: u'III', 4: u'IV', 5: u'V', 6: u'VI',
    7: u'VII', 8: u'VIII', 9: u'IX', 10: u'X', 11: u'XI',
}

CLASS_SHORT = {
    'heavyTank': u'ТТ',
    'mediumTank': u'СТ',
    'lightTank': u'ЛТ',
    'AT-SPG': u'ПТ-САУ',
    'SPG': u'САУ',
}
CLASS_TAGS = frozenset(CLASS_SHORT.keys())

EMA_K = 2.0 / 101.0


def roman_level(level):
    try:
        return ROMAN_LEVELS.get(int(level), u'')
    except Exception:
        return u''


def short_type(tags):
    try:
        for tag in (tags or []):
            if tag in CLASS_SHORT:
                return CLASS_SHORT[tag]
    except Exception:
        pass
    return u''


def _read_record(dossier, block, key):
    if dossier is None:
        return None
    try:
        v = dossier.getRecordValue(block, key)
        if v is not None:
            return int(v)
    except Exception:
        pass
    try:
        descr = dossier.getDossierDescr()
        if descr is not None:
            b = descr[block]
            if b is not None:
                return int(b[key])
    except Exception:
        pass
    return None


def dossier_to_dict(dossier):
    if dossier is None:
        return None
    try:
        battles = 0
        try:
            battles = int(dossier.getRandomStats().getBattlesCount())
        except Exception:
            battles = 0
        rating_raw = _read_record(dossier, 'achievements', 'damageRating') or 0
        moving_avg = _read_record(dossier, 'achievements', 'movingAvgDamage') or 0
        marks = _read_record(dossier, 'achievements', 'marksOnGun') or 0
        return {
            'damageRating': round(rating_raw / 100.0, 2) if rating_raw > 0 else 0.0,
            'movingAvgDamage': int(moving_avg),
            'marksOnGun': int(marks),
            'battlesCount': battles,
        }
    except Exception:
        return None


def is_dossier_dict_empty(d):
    if not d:
        return True
    return (int(d.get('damageRating', 0) or 0) == 0 and
            int(d.get('movingAvgDamage', 0) or 0) == 0 and
            int(d.get('battlesCount', 0) or 0) == 0)


PERCENT_POINTS = (0, 20, 40, 55, 65, 75, 85, 95, 100)

def interpolate_percent(value, thresholds):
    """Линейная интерполяция по серверным точкам.
    thresholds — dict {percent: damage}, например {65: 2208, 85: 3044}.
    Возвращает прогноз процента для данного среднего урона."""
    if not thresholds:
        return None
    points = []
    for pct in PERCENT_POINTS:
        dmg = thresholds.get(pct, 0)
        if dmg and dmg > 0:
            points.append((pct, dmg))
    if len(points) < 2:
        return None
    value = float(value)
    if value <= points[0][1]:
        return float(points[0][0])
    if value >= points[-1][1]:
        return float(points[-1][0])
    for i in range(len(points) - 1):
        p1, d1 = points[i]
        p2, d2 = points[i + 1]
        if d1 <= value <= d2:
            if d2 == d1:
                return float(p1)
            t = (value - d1) / float(d2 - d1)
            return float(p1) + t * float(p2 - p1)
    return None


def compute_display(cached_percent, cached_avg, cached_delta, current_total,
                    thresholds=None):
    """Возвращает (display_percent, display_delta, display_avg).

    Если есть серверные пороги — используем интерполяцию (точнее).
    Иначе — фолбэк на линейный K.
    """
    cached_percent = float(cached_percent or 0)
    cached_avg = float(cached_avg or 0)
    cached_delta = float(cached_delta or 0)
    total = float(current_total or 0)

    if total <= 0 or cached_percent <= 0 or cached_avg <= 0:
        return (cached_percent, cached_delta, int(cached_avg))

    new_avg = cached_avg * (1.0 - EMA_K) + total * EMA_K

    interp = interpolate_percent(new_avg, thresholds)
    if interp is not None:
        display_delta = cached_delta + (interp - cached_percent)
        return (round(interp, 2), round(display_delta, 2),
                int(round(new_avg)))

    # Фолбэк: линейный коэффициент.
    K = cached_avg / cached_percent
    if K <= 0:
        return (cached_percent, cached_delta, int(round(new_avg)))
    new_rating = cached_percent + (new_avg - cached_avg) / K
    display_delta = cached_delta + (new_rating - cached_percent)
    return (round(new_rating, 2), round(display_delta, 2),
            int(round(new_avg)))


def next_mark_info(marks, thresholds):
    """Возвращает (percent, value) для СЛЕДУЮЩЕЙ отметки.
    marks = 0 -> 65%, 1 -> 85%, 2 -> 95%, 3 -> 100%.
    Если порога нет в thresholds — вернёт (percent, 0)."""
    order = [65, 85, 95, 100]
    try:
        idx = max(0, min(3, int(marks or 0)))
    except Exception:
        idx = 0
    target_pct = order[idx]
    target_val = 0
    if thresholds:
        target_val = int(thresholds.get(target_pct, 0) or 0)
    return (target_pct, target_val)


def build_snapshot(cached, veh, current_damage, assist_damage=0,
                   thresholds=None):
    snap = {
        'percent': 0.0,
        'delta': 0.0,
        'marksOnGun': 0,
        'currentAvg': 0,
        'nextMarkPercent': 0,
        'nextMarkValue': 0,
        'hasNextMark': False,
        'hasVehicle': False,
    }
    if veh is None or not veh.get('name'):
        return snap
    snap['hasVehicle'] = True
    if cached:
        marks = int(cached.get('marksOnGun', 0))
        snap['marksOnGun'] = marks
        cached_percent = float(cached.get('damageRating', 0.0))
        cached_avg = int(cached.get('movingAvgDamage', 0))
        cached_delta = float(cached.get('lastDelta', 0.0))
        total = int(current_damage or 0) + int(assist_damage or 0)
        p, d, avg = compute_display(cached_percent, cached_avg,
                                     cached_delta, total,
                                     thresholds)
        snap['percent'] = p
        snap['delta'] = d
        snap['currentAvg'] = avg
        pct, val = next_mark_info(marks, thresholds)
        snap['nextMarkPercent'] = pct
        snap['nextMarkValue'] = val
        snap['hasNextMark'] = (val > 0)
    return snap