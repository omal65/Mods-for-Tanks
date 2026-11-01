# -*- coding: utf-8 -*-
#
# MarkBattle v0.8 - базовые утилиты пакета.
#
from __future__ import print_function

import codecs
import json
import os
import time

MOD_ID = 'user.markbattle'
LOG_PREFIX = 'MARK_BATTLE'
CONF_DIR = 'mods/configs/mark_battle'
CONFIG_FILE = CONF_DIR + '/config.json'
LOG_FILE = CONF_DIR + '/mark_battle.log'
LOG_MAX = 512 * 1024

RES_MAP_ITEM_ID = 'user.markbattle.panel'
RES_MAP_TABLE_ITEM_ID = 'user.markbattle.table'

RES_MAP_TARGET = 'mods/configs/res_map/mark_battle.json'
RES_MAP_JSON = (
    '[\n'
    '  {\n'
    '    "itemID": "user.markbattle.panel",\n'
    '    "type": "Layout",\n'
    '    "path": "coui://gui/gameface/mods/mark_battle/index.html",\n'
    '    "parameters": {\n'
    '      "extension": "",\n'
    '      "entrance": "MarkBattlePanel",\n'
    '      "impl": "gameface"\n'
    '    }\n'
    '  },\n'
    '  {\n'
    '    "itemID": "user.markbattle.table",\n'
    '    "type": "Layout",\n'
    '    "path": "coui://gui/gameface/mods/mark_battle/table.html",\n'
    '    "parameters": {\n'
    '      "extension": "",\n'
    '      "entrance": "MarkBattleTable",\n'
    '      "impl": "gameface"\n'
    '    }\n'
    '  }\n'
    ']\n'
)


def _find_res_mods_dirs():
    raw = []
    try:
        import ResMgr
        for xml_name in ('../paths.xml', 'paths.xml'):
            try:
                section = ResMgr.openSection(xml_name)
            except Exception:
                section = None
            if section is None:
                continue
            try:
                paths_section = section['Paths']
            except Exception:
                paths_section = None
            if paths_section is None:
                continue
            for item in paths_section.values():
                try:
                    s = item.asString
                except Exception:
                    continue
                if not s:
                    continue
                norm = s[2:] if s.startswith('./') else s
                if norm not in raw:
                    raw.append(norm)
            break
    except Exception:
        pass
    for cand in ('res_mods', '../res_mods'):
        if cand not in raw:
            raw.append(cand)
    existing = []
    for d in raw:
        try:
            if os.path.isdir(d):
                ap = os.path.abspath(d)
                if ap not in existing:
                    existing.append(ap)
        except Exception:
            continue
    existing.sort(key=lambda p: 0 if 'res_mods' in p.replace('/', os.sep) else 1)
    return existing


def ensure_res_map_configs():
    written = 0
    infos = []
    targets = []
    candidates = _find_res_mods_dirs()
    seen = set()
    for d in candidates:
        if 'res_mods' not in d.replace('/', os.sep):
            continue
        p = os.path.join(d, 'mods', 'configs', 'res_map', 'mark_battle.json')
        if p not in seen:
            seen.add(p)
            targets.append(p)
        if len(targets) >= 3:
            break
    if RES_MAP_TARGET not in targets:
        targets.append(RES_MAP_TARGET)
    if not infos:
        if not candidates:
            infos.append(u'res_mods candidates: NONE FOUND')
        else:
            infos.append(u'res_mods candidates: %s' % u' | '.join(candidates[:3]))
    for path in targets:
        try:
            need = True
            if os.path.isfile(path):
                try:
                    with open(path, 'r') as f:
                        need = (f.read() != RES_MAP_JSON)
                except Exception:
                    need = True
            folder = os.path.dirname(path)
            if folder and not os.path.isdir(folder):
                os.makedirs(folder)
            if need:
                with open(path, 'w') as f:
                    f.write(RES_MAP_JSON)
                written += 1
            infos.append(u'%s (present=%s)'
                         % (os.path.abspath(path), os.path.isfile(path)))
        except Exception as e:
            infos.append(u'%s FAILED: %r' % (os.path.abspath(path), e))
    return written, u'; '.join(infos)


def _log(msg):
    if isinstance(msg, str):
        try:
            msg = msg.decode('utf-8', 'replace')
        except Exception:
            msg = repr(msg)
    try:
        msg = msg.replace(u'\u2014', u'-').replace(u'\u2013', u'-')
    except Exception:
        pass
    try:
        if not os.path.exists(CONF_DIR):
            os.makedirs(CONF_DIR)
    except Exception:
        pass
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX:
            os.remove(LOG_FILE)
    except Exception:
        pass
    try:
        with codecs.open(LOG_FILE, 'a', 'utf-8') as f:
            f.write(u'%s [%s] %s\n'
                    % (time.strftime('%Y-%m-%d %H:%M:%S'), LOG_PREFIX, msg))
    except Exception:
        pass
    try:
        print('[%s] %s' % (LOG_PREFIX, msg))
    except Exception:
        pass


def _load_json(path, default=None):
    if not os.path.isfile(path):
        return default
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        _log(u'_load_json(%s) failed: %r' % (path, e))
        return default


def _save_json(path, data):
    try:
        folder = os.path.dirname(path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(path, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        _log(u'_save_json(%s) failed: %r' % (path, e))
        return False


def load_position_for(mode):
    """mode: 'battle' | 'hangar' | 'table'. Возвращает (x, y) или (None, None)."""
    data = _load_json(CONFIG_FILE, {})
    block = data.get(mode, {})
    try:
        x = block.get('x')
        y = block.get('y')
    except Exception:
        x, y = None, None
    if x is None or y is None:
        return (None, None)
    try:
        return (int(x), int(y))
    except Exception:
        return (None, None)


def save_position_for(mode, x, y):
    """mode: 'battle' | 'hangar' | 'table'. Сохраняет позицию в конфиг."""
    if x is None or y is None:
        return False
    data = _load_json(CONFIG_FILE, {})
    if not isinstance(data, dict):
        data = {}
    try:
        data[mode] = {'x': int(x), 'y': int(y)}
    except Exception:
        return False
    return _save_json(CONFIG_FILE, data)


def load_window_config():
    x, y = load_position_for('battle')
    return {'x': x, 'y': y}


def save_window_config(x, y):
    return save_position_for('battle', x, y)