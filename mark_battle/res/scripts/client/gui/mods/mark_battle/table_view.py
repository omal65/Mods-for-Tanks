# -*- coding: utf-8 -*-
#
# MarkBattle v1.0 - окно таблицы отметок по всем танкам (Вариант А).
#
from __future__ import print_function

import json
import traceback

import BigWorld
import GUI

from . import (_log, load_position_for, save_position_for,
               RES_MAP_TABLE_ITEM_ID)
from . import moe_info
from . import stats as stats_mod

_Keys = None
try:
    import Keys as _Keys
except ImportError:
    try:
        from gui import Keys as _KeysGui
        _Keys = _KeysGui
    except ImportError:
        _Keys = None

TABLE_CLS = None
TABLE_WINDOW = None
_OPENWG = None

TABLE_POS_KEY = 'table_v3'
TABLE_SIZE = (1520, 930)
TABLE_STATE = {'x': None, 'y': None, 'view': TABLE_SIZE}
TABLE_DRAG = {'active': False, 'card0': None, 'cursor0': None, 'ticking': False}

NATION_ORDER = (
    'ussr', 'germany', 'usa', 'china', 'france',
    'uk', 'japan', 'czech', 'sweden', 'poland', 'italy'
)

CLASS_TO_CODE = {
    'lightTank': u'LT',
    'mediumTank': u'MT',
    'heavyTank': u'HT',
    'AT-SPG': u'TD',
    'SPG': u'SPG',
}

CLASS_TO_RU = {
    'lightTank': u'ЛТ',
    'mediumTank': u'СТ',
    'heavyTank': u'ТТ',
    'AT-SPG': u'ПТ',
    'SPG': u'САУ',
}


def _get_openwg():
    global _OPENWG
    if _OPENWG is not None:
        return _OPENWG
    try:
        import openwg_gameface as _openwg
        _OPENWG = _openwg
        return _OPENWG
    except ImportError:
        return None


def _screen_size():
    try:
        s = BigWorld.screenSize()
        if s and int(s[0]) > 0 and int(s[1]) > 0:
            return (int(s[0]), int(s[1]))
    except Exception:
        pass
    return (1920, 1080)


def _norm_to_px(nx, ny):
    w, h = _screen_size()
    px = (float(nx) + 1.0) * 0.5 * w
    py = (1.0 - float(ny)) * 0.5 * h
    return (px, py)


def _is_lmb_down():
    if _Keys is None:
        return True
    for name in ('KEY_LEFTMOUSE', 'KEY_LMOUSE', 'KEY_MOUSE0'):
        code = getattr(_Keys, name, None)
        if code is None:
            continue
        try:
            return bool(BigWorld.isKeyDown(int(code)))
        except Exception:
            continue
    return True


def _clamp_table(x, y):
    w, h = _screen_size()
    vw, vh = TABLE_STATE.get('view') or TABLE_SIZE
    vw = int(vw) if 400 <= int(vw) <= w else TABLE_SIZE[0]
    vh = int(vh) if 300 <= int(vh) <= h else TABLE_SIZE[1]
    max_x = max(0, w - vw)
    max_y = max(0, h - vh)
    return (max(0, min(int(x), max_x)), max(0, min(int(y), max_y)))


def _build_table_classes():
    global TABLE_CLS
    if TABLE_CLS is not None:
        return TABLE_CLS
    openwg = _get_openwg()
    if openwg is None:
        return None

    from gui.impl.pub import ViewImpl, WindowImpl
    from frameworks.wulf import (ViewSettings, ViewFlags, WindowFlags,
                                 WindowLayer, ViewModel)

    class MarkBattleTableViewModel(ViewModel):
        def __init__(self):
            super(MarkBattleTableViewModel, self).__init__(properties=3, commands=4)

        def _initialize(self, *args, **kwargs):
            super(MarkBattleTableViewModel, self)._initialize(*args, **kwargs)
            self._addStringProperty('vehiclesJson', u'[]')        # 0
            self._addStringProperty('metaJson', u'{}')            # 1
            self._addNumberProperty('revision', 0)                # 2

            self._cmdReady = self._addCommand('ready')
            self._cmdDragStart = self._addCommand('dragStart')
            self._cmdDragMove = self._addCommand('dragMove')
            self._cmdDragEnd = self._addCommand('dragEnd')

            self._cmdReady += self._onReady
            self._cmdDragStart += self._onDragStart
            self._cmdDragMove += self._onDragMove
            self._cmdDragEnd += self._onDragEnd

        def _onReady(self, args):
            if args.get('closeNow'):
                BigWorld.callback(0.0, close_table_window)
                return
            req_cds = args.get('requestCds')
            if req_cds:
                try:
                    cds = [int(x) for x in str(req_cds).split(',') if x.strip()]
                    if cds:
                        moe_info.enqueue_batch(cds, priority=True)
                except Exception:
                    pass
                return
            vw = int(float(args.get('viewW') or TABLE_SIZE[0]))
            vh = int(float(args.get('viewH') or TABLE_SIZE[1]))
            if vw >= 400 and vh >= 300:
                TABLE_STATE['view'] = (vw, vh)
            _apply_initial_table_pos()
            push_table_data()

        def _onDragStart(self, args):
            if TABLE_WINDOW is None:
                return
            wx = TABLE_STATE['x'] or 0
            wy = TABLE_STATE['y'] or 0
            try:
                nx, ny = GUI.mcursor().position
                cx, cy = _norm_to_px(nx, ny)
            except Exception:
                cx, cy = (wx, wy)
            TABLE_DRAG['active'] = True
            TABLE_DRAG['card0'] = (wx, wy)
            TABLE_DRAG['cursor0'] = (float(cx), float(cy))
            if not TABLE_DRAG['ticking']:
                TABLE_DRAG['ticking'] = True
                BigWorld.callback(0.0, _tick_table_drag)

        def _onDragMove(self, args):
            return

        def _onDragEnd(self, args):
            if not TABLE_DRAG['active']:
                return
            _apply_table_drag_step()
            TABLE_DRAG['active'] = False
            TABLE_DRAG['ticking'] = False
            if TABLE_STATE['x'] is not None and TABLE_STATE['y'] is not None:
                save_position_for(TABLE_POS_KEY, TABLE_STATE['x'], TABLE_STATE['y'])

    class MarkBattleTableView(ViewImpl):
        viewLayoutID = openwg.ModDynAccessor(RES_MAP_TABLE_ITEM_ID)

        def __init__(self):
            settings = ViewSettings(MarkBattleTableView.viewLayoutID(),
                                    flags=ViewFlags.VIEW,
                                    model=MarkBattleTableViewModel())
            super(MarkBattleTableView, self).__init__(settings)

        @property
        def viewModel(self):
            return super(MarkBattleTableView, self).getViewModel()

    class MarkBattleTableWindow(WindowImpl):
        def __init__(self):
            super(MarkBattleTableWindow, self).__init__(
                wndFlags=WindowFlags.WINDOW,
                layer=WindowLayer.TOP_WINDOW,
                content=MarkBattleTableView())

    TABLE_CLS = {
        'model': MarkBattleTableViewModel,
        'view': MarkBattleTableView,
        'window': MarkBattleTableWindow,
    }
    return TABLE_CLS


def _tick_table_drag(*_args):
    if not TABLE_DRAG['active'] or TABLE_WINDOW is None:
        TABLE_DRAG['ticking'] = False
        return
    if not _is_lmb_down():
        _apply_table_drag_step()
        TABLE_DRAG['active'] = False
        TABLE_DRAG['ticking'] = False
        if TABLE_STATE['x'] is not None and TABLE_STATE['y'] is not None:
            save_position_for(TABLE_POS_KEY, TABLE_STATE['x'], TABLE_STATE['y'])
        return
    _apply_table_drag_step()
    if TABLE_DRAG['active']:
        BigWorld.callback(0.0, _tick_table_drag)
    else:
        TABLE_DRAG['ticking'] = False


def _apply_table_drag_step():
    if TABLE_WINDOW is None:
        return
    wx = TABLE_STATE['x']
    wy = TABLE_STATE['y']
    if wx is None or wy is None or TABLE_DRAG['card0'] is None or TABLE_DRAG['cursor0'] is None:
        return
    try:
        nx, ny = GUI.mcursor().position
        cx, cy = _norm_to_px(nx, ny)
    except Exception:
        return
    tx = TABLE_DRAG['card0'][0] + (float(cx) - TABLE_DRAG['cursor0'][0])
    ty = TABLE_DRAG['card0'][1] + (float(cy) - TABLE_DRAG['cursor0'][1])
    nx_, ny_ = _clamp_table(tx, ty)
    if nx_ == wx and ny_ == wy:
        return
    try:
        if TABLE_WINDOW.move(int(nx_), int(ny_)):
            TABLE_STATE['x'] = nx_
            TABLE_STATE['y'] = ny_
    except Exception:
        pass


def _apply_initial_table_pos():
    if TABLE_WINDOW is None:
        return
    saved_x, saved_y = load_position_for(TABLE_POS_KEY)
    if saved_x is None or saved_y is None:
        w, h = _screen_size()
        vw, vh = TABLE_STATE.get('view') or TABLE_SIZE
        saved_x = max(20, (w - int(vw)) // 2)
        saved_y = max(54, ((h - int(vh)) // 2) - 38)
    cx, cy = _clamp_table(saved_x, saved_y)
    TABLE_STATE['x'] = cx
    TABLE_STATE['y'] = cy
    try:
        TABLE_WINDOW.move(int(cx), int(cy))
    except Exception:
        pass


def is_table_open():
    if TABLE_WINDOW is None:
        return False
    try:
        ws = getattr(TABLE_WINDOW, 'windowStatus', None)
        if ws is not None and int(ws) in (4, 5):
            return False
        return bool(getattr(TABLE_WINDOW, 'uniqueID', None))
    except Exception:
        return False


def get_table_uid():
    if TABLE_WINDOW is None:
        return None
    return getattr(TABLE_WINDOW, 'uniqueID', None)


def toggle_table_window():
    if is_table_open():
        close_table_window()
    else:
        open_table_window()


def open_table_window():
    global TABLE_WINDOW
    if is_table_open():
        push_table_data()
        return TABLE_WINDOW
    classes = _build_table_classes()
    if classes is None:
        _log(u'[TABLE] openwg_gameface unavailable')
        return None
    try:
        from gui.impl.gen_utils import INVALID_RES_ID
        layout_id = classes['view'].viewLayoutID()
        if layout_id == INVALID_RES_ID:
            _log(u'[TABLE] layout %r not registered yet (restart client once)'
                 % RES_MAP_TABLE_ITEM_ID)
            return None
    except Exception:
        pass
    try:
        TABLE_WINDOW = classes['window']()
        TABLE_WINDOW.load()
        _log(u'[TABLE] window opened: uid=%s' % getattr(TABLE_WINDOW, 'uniqueID', '?'))
        BigWorld.callback(0.1, _apply_initial_table_pos)
    except Exception:
        _log(u'[TABLE] open crashed:\n%s' % traceback.format_exc())
        TABLE_WINDOW = None
    return TABLE_WINDOW


def close_table_window():
    global TABLE_WINDOW
    if TABLE_WINDOW is None:
        return
    try:
        TABLE_WINDOW.hide(destroy=True)
        _log(u'[TABLE] window closed (hide destroy=True)')
    except Exception:
        try:
            TABLE_WINDOW.destroy()
        except Exception:
            pass
    TABLE_WINDOW = None


def _collect_all_vehicles(dossier_cache):
    """Собирает все танки V-XI уровней (в ангаре и не в ангаре)."""
    rows = []
    in_hangar_count = 0
    missing_cds_in_hangar = []
    missing_cds_other = []

    try:
        from skeletons.gui.shared import IItemsCache
        from helpers import dependency
        from gui.shared.utils.requesters import REQ_CRITERIA
        items_cache = dependency.instance(IItemsCache)
        criteria = (REQ_CRITERIA.VEHICLE.LEVELS(range(5, 12)) |
                    ~REQ_CRITERIA.SECRET |
                    ~REQ_CRITERIA.VEHICLE.IS_BOT |
                    ~REQ_CRITERIA.VEHICLE.EVENT_BATTLE |
                    ~REQ_CRITERIA.VEHICLE.MODE_HIDDEN)
        vehicles_dict = items_cache.items.getVehicles(criteria)
    except Exception as e:
        _log(u'[TABLE] getVehicles failed: %r' % e)
        vehicles_dict = {}

    for int_cd, veh in vehicles_dict.items():
        try:
            int_cd = int(int_cd)
            level = int(getattr(veh, 'level', 0) or 0)
            if level < 5:
                continue
            raw_name = str(getattr(veh, 'name', '') or '')
            if any(x in raw_name for x in ('_7x7', '_bootcamp', '_bob', '_artillery', '_fl', '_fun', '_comp7', '_mapbox')):
                continue

            # Извлекаем системный ключ иконки танка, например 'ussr:R73_KV4' -> 'R73_KV4'
            veh_key = raw_name.split(':', 1)[1] if ':' in raw_name else raw_name

            nation_name = str(getattr(veh, 'nationName', '') or '')
            if nation_name not in NATION_ORDER:
                continue

            vtype = str(getattr(veh, 'type', '') or '')
            type_code = CLASS_TO_CODE.get(vtype, u'HT')
            type_ru = CLASS_TO_RU.get(vtype, u'ТТ')

            in_hangar = bool(getattr(veh, 'isInInventory', False))
            if in_hangar:
                in_hangar_count += 1

            is_prem = bool(getattr(veh, 'isPremium', False) or
                           getattr(veh, 'isSpecial', False) or
                           getattr(veh, 'isCollectible', False))

            user_name = unicode(getattr(veh, 'shortUserName', None) or
                                getattr(veh, 'userName', u'') or u'')

            cached = dossier_cache.get(str(int_cd))
            if cached is None and in_hangar:
                try:
                    d_obj = items_cache.items.getVehicleDossier(int_cd)
                    if d_obj is not None:
                        cached = stats_mod.dossier_to_dict(d_obj)
                        if cached and not stats_mod.is_dossier_dict_empty(cached):
                            dossier_cache[str(int_cd)] = cached
                except Exception:
                    cached = None

            my_pct = float(cached.get('damageRating', 0.0)) if cached else 0.0
            marks = int(cached.get('marksOnGun', 0)) if cached else 0

            th = moe_info.get_thresholds(int_cd)
            m65 = int(th.get(65, 0)) if th else 0
            m85 = int(th.get(85, 0)) if th else 0
            m95 = int(th.get(95, 0)) if th else 0

            if m65 <= 0:
                if in_hangar:
                    missing_cds_in_hangar.append(int_cd)
                else:
                    missing_cds_other.append(int_cd)

            rows.append({
                'cd': int_cd,
                'vk': veh_key,
                'n': nation_name,
                'name': user_name,
                'lvl': level,
                'lvlR': stats_mod.roman_level(level),
                'tc': type_code,
                'tr': type_ru,
                'ih': 1 if in_hangar else 0,
                'pr': 1 if is_prem else 0,
                'pct': round(my_pct, 2),
                'mk': marks,
                'm1': m65,
                'm2': m85,
                'm3': m95,
            })
        except Exception:
            continue

    rows.sort(key=lambda r: (-r['pct'], -r['mk'], -r['lvl'], r['name']))

    if missing_cds_in_hangar:
        moe_info.enqueue_batch(missing_cds_in_hangar[:60], priority=True)
    elif missing_cds_other:
        moe_info.enqueue_batch(missing_cds_other[:40], priority=False)

    w, h = _screen_size()
    meta = {
        'totalVehicles': len(rows),
        'inHangarCount': in_hangar_count,
        'updatedAt': moe_info.get_updated_time_str(),
        'server': u'RU-BY',
        'screenW': w,
        'screenH': h,
    }
    return rows, meta


_revision_counter = 0


def push_table_data():
    global _revision_counter
    if not is_table_open():
        return False
    try:
        from . import app as _app
        dossier_cache = getattr(_app, '_dossier_cache', {})
        rows, meta = _collect_all_vehicles(dossier_cache)
        content = TABLE_WINDOW.content
        model = content.getViewModel() if content is not None else None
        if model is None:
            return False
        _revision_counter += 1
        model._setString(0, unicode(json.dumps(rows, ensure_ascii=False)))
        model._setString(1, unicode(json.dumps(meta, ensure_ascii=False)))
        model._setNumber(2, _revision_counter)
        return True
    except Exception:
        _log(u'[TABLE] push_table_data failed:\n%s' % traceback.format_exc())
        return False