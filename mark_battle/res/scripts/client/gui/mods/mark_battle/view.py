# -*- coding: utf-8 -*-
#
# MarkBattle v1.2 - окно на Gameface (wulf + net.openwg.gameface).
#
# Двойное назначение: бой + ангар. Клик в ангаре открывает таблицу отметок.
#
from __future__ import print_function

import traceback

import BigWorld
import GUI

from . import (_log, load_position_for, save_position_for,
               RES_MAP_ITEM_ID)


_Keys = None
try:
    import Keys as _Keys
except ImportError:
    try:
        from gui import Keys as _KeysGui
        _Keys = _KeysGui
    except ImportError:
        _Keys = None


VIEW_CLS = None
WINDOW = None
READY_HANDLER = None
WINDOW_LOST_HANDLER = None

PANEL_STATE = {
    'x': None, 'y': None, 'client': None, 'view': None,
}
DRAG = {
    'active': False, 'card0': None, 'cursor0': None, 'ticking': False,
    'moved': False,
}

CLICK_MAX_DIST_PX = 6.0
DEFAULT_MARGIN = 40
MOVE_RETRY_MAX = 20
MOVE_RETRY_DELAY = 0.25

_MODE = 'battle'
IS_VISIBLE = False
_LAST_SYNCED_VISIBLE = None
_LAST_TOGGLE_TIME = 0.0

_OPENWG = None
LAST_CREATE_ERROR = u''


def _log_keys_status():
    if _Keys is None:
        _log(u'Keys module NOT found - LMB release detection disabled')
    else:
        attrs = []
        for name in ('KEY_LEFTMOUSE', 'KEY_LMOUSE', 'KEY_MOUSE0'):
            v = getattr(_Keys, name, None)
            if v is not None:
                attrs.append('%s=%s' % (name, v))
        _log(u'Keys module loaded: %s'
             % (', '.join(attrs) or '(no LMB constants found)'))


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


def _screen_size():
    try:
        s = BigWorld.screenSize()
        if s and int(s[0]) > 0 and int(s[1]) > 0:
            return (int(s[0]), int(s[1]))
    except Exception:
        pass
    client = PANEL_STATE.get('client')
    if client and client[0] > 0:
        return (int(client[0]), int(client[1]))
    return (1920, 1080)


def _get_openwg():
    global _OPENWG
    if _OPENWG is not None:
        return _OPENWG
    try:
        import openwg_gameface as _openwg
    except ImportError as e:
        _log(u'openwg_gameface not importable yet: %r' % e)
        return None
    _OPENWG = _openwg
    _log(u'openwg_gameface imported (IS_LESTA=%s)'
         % getattr(_OPENWG, 'IS_LESTA', '?'))
    return _OPENWG


def _request_table_toggle(source=u'click'):
    global _LAST_TOGGLE_TIME
    if _MODE != 'hangar':
        return
    now = BigWorld.time()
    if now - _LAST_TOGGLE_TIME < 0.30:
        return
    _LAST_TOGGLE_TIME = now
    try:
        from . import table_view
        _log(u'[TABLE] toggle requested (%s)' % source)
        table_view.toggle_table_window()
    except Exception:
        _log(u'toggle_table_window failed:\n%s' % traceback.format_exc())


def _finish_drag_or_click():
    was_moved = bool(DRAG.get('moved', False))
    _apply_drag_step()
    was_moved = was_moved or bool(DRAG.get('moved', False))
    DRAG['active'] = False
    DRAG['ticking'] = False
    DRAG['moved'] = False
    if was_moved:
        push_panel_position()
        persist_position()
    elif _MODE == 'hangar':
        _request_table_toggle(u'dragEnd-noMove')


def _build_classes():
    global VIEW_CLS
    if VIEW_CLS is not None:
        return VIEW_CLS
    openwg = _get_openwg()
    if openwg is None:
        return None

    from gui.impl.pub import ViewImpl, WindowImpl
    from frameworks.wulf import (ViewSettings, ViewFlags, WindowFlags,
                                 WindowLayer, ViewModel)

    class MarkBattleViewModel(ViewModel):
        def __init__(self):
            super(MarkBattleViewModel, self).__init__(properties=13, commands=4)

        def _initialize(self, *args, **kwargs):
            super(MarkBattleViewModel, self)._initialize(*args, **kwargs)
            self._addStringProperty('title', u'MARK BATTLE')      # 0
            self._addNumberProperty('posX', 0)                    # 1
            self._addNumberProperty('posY', 0)                    # 2
            self._addNumberProperty('hasPos', 0)                  # 3
            self._addBoolProperty('visible', bool(IS_VISIBLE))    # 4
            self._addNumberProperty('percentX100', 0)             # 5
            self._addNumberProperty('deltaX100', 0)               # 6
            self._addNumberProperty('marksOnGun', 0)              # 7
            self._addNumberProperty('currentAvg', 0)              # 8
            self._addNumberProperty('nextMarkPercent', 0)         # 9
            self._addNumberProperty('nextMarkValue', 0)           # 10
            self._addBoolProperty('hasNextMark', False)           # 11
            self._addBoolProperty('hasVehicle', False)            # 12

            self._cmdReady = self._addCommand('ready')
            self._cmdDragStart = self._addCommand('dragStart')
            self._cmdDragMove = self._addCommand('dragMove')
            self._cmdDragEnd = self._addCommand('dragEnd')

            self._cmdReady += self._onReady
            self._cmdDragStart += self._onDragStart
            self._cmdDragMove += self._onDragMove
            self._cmdDragEnd += self._onDragEnd

        def _onReady(self, args):
            if args.get('toggleTable'):
                _request_table_toggle(u'js-ready-cmd')
                return
            client_w = _to_number(args.get('clientW'))
            client_h = _to_number(args.get('clientH'))
            card_w = _to_number(args.get('viewW'))
            card_h = _to_number(args.get('viewH'))
            PANEL_STATE['client'] = (client_w, client_h)
            PANEL_STATE['view'] = (card_w, card_h)
            screen = _screen_size()
            _log(u'js ready: client=%sx%s card=%sx%s screen=%sx%s'
                 % (client_w, client_h, card_w, card_h,
                    screen[0], screen[1]))
            if READY_HANDLER is not None:
                try:
                    READY_HANDLER(client_w, client_h, card_w, card_h)
                except Exception as e:
                    _log(u'ready handler failed: %r' % e)

        def _onDragStart(self, args):
            if WINDOW is None:
                return
            wx = PANEL_STATE['x'] or 0
            wy = PANEL_STATE['y'] or 0
            try:
                nx, ny = GUI.mcursor().position
                cx, cy = _norm_to_px(nx, ny)
            except Exception:
                cx, cy = (wx + _to_float(args.get('lx'), 0.0),
                          wy + _to_float(args.get('ly'), 0.0))
            DRAG['active'] = True
            DRAG['moved'] = False
            DRAG['card0'] = (wx, wy)
            DRAG['cursor0'] = (float(cx), float(cy))
            if not DRAG['ticking']:
                DRAG['ticking'] = True
                BigWorld.callback(0.0, _tick_drag)

        def _onDragMove(self, args):
            return

        def _onDragEnd(self, args):
            if not DRAG['active']:
                return
            _finish_drag_or_click()

    class MarkBattleView(ViewImpl):
        viewLayoutID = openwg.ModDynAccessor(RES_MAP_ITEM_ID)

        def __init__(self):
            settings = ViewSettings(MarkBattleView.viewLayoutID(),
                                    flags=ViewFlags.VIEW,
                                    model=MarkBattleViewModel())
            super(MarkBattleView, self).__init__(settings)

        @property
        def viewModel(self):
            return super(MarkBattleView, self).getViewModel()

    class MarkBattleWindow(WindowImpl):
        def __init__(self):
            super(MarkBattleWindow, self).__init__(
                wndFlags=WindowFlags.WINDOW,
                layer=WindowLayer.WINDOW,
                content=MarkBattleView())

    VIEW_CLS = {
        'model': MarkBattleViewModel,
        'view': MarkBattleView,
        'window': MarkBattleWindow,
    }
    _log(u'view classes built (resID key=%s)' % RES_MAP_ITEM_ID)
    return VIEW_CLS


def _to_number(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def _to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _norm_to_px(nx, ny):
    w, h = _screen_size()
    px = (float(nx) + 1.0) * 0.5 * w
    py = (1.0 - float(ny)) * 0.5 * h
    return (px, py)


def _clamp(x, y):
    w, h = _screen_size()
    view = PANEL_STATE.get('view')
    vw = int(view[0]) if (view and 0 < int(view[0]) <= 400) else 200
    vh = int(view[1]) if (view and 0 < int(view[1]) <= 400) else 122
    max_x = max(0, w - vw)
    max_y = max(0, h - vh)
    x = max(0, min(int(x), max_x))
    y = max(0, min(int(y), max_y))
    return (x, y)


def _tick_drag(*_args):
    if not DRAG['active'] or WINDOW is None or not IS_VISIBLE:
        DRAG['ticking'] = False
        return
    if not _is_lmb_down():
        _finish_drag_or_click()
        return
    _apply_drag_step()
    if DRAG['active']:
        BigWorld.callback(0.0, _tick_drag)
    else:
        DRAG['ticking'] = False


def _apply_drag_step(*_args):
    if WINDOW is None:
        return
    wx = PANEL_STATE['x']
    wy = PANEL_STATE['y']
    if wx is None or wy is None:
        return
    if DRAG['card0'] is None or DRAG['cursor0'] is None:
        return
    try:
        nx, ny = GUI.mcursor().position
        cx, cy = _norm_to_px(nx, ny)
    except Exception:
        return
    dx = float(cx) - DRAG['cursor0'][0]
    dy = float(cy) - DRAG['cursor0'][1]
    if not DRAG.get('moved', False):
        if abs(dx) < CLICK_MAX_DIST_PX and abs(dy) < CLICK_MAX_DIST_PX:
            return
        DRAG['moved'] = True
    tx = DRAG['card0'][0] + dx
    ty = DRAG['card0'][1] + dy
    nx_, ny_ = _clamp(tx, ty)
    if nx_ == wx and ny_ == wy:
        return
    try:
        ok = WINDOW.move(int(nx_), int(ny_))
    except Exception as e:
        _log(u'drag window.move failed: %r' % e)
        return
    if ok:
        PANEL_STATE['x'] = nx_
        PANEL_STATE['y'] = ny_


def create_window(version, attempt=0):
    global WINDOW, LAST_CREATE_ERROR
    classes = _build_classes()
    if classes is None:
        LAST_CREATE_ERROR = u'openwg_gameface is unavailable'
        if attempt == 0:
            _log(u'cannot create window: %s' % LAST_CREATE_ERROR)
        return None
    try:
        from gui.impl.gen_utils import INVALID_RES_ID
    except ImportError:
        INVALID_RES_ID = None
    if INVALID_RES_ID is not None:
        layout_id = classes['view'].viewLayoutID()
        if layout_id == INVALID_RES_ID:
            LAST_CREATE_ERROR = u'res_map key %r not registered' % RES_MAP_ITEM_ID
            if attempt == 0:
                _log(u'res_map key %r NOT registered yet' % RES_MAP_ITEM_ID)
            return None
        if attempt == 0:
            _log(u'layoutID resolved: %s' % layout_id)
    LAST_CREATE_ERROR = u''

    if WINDOW is not None:
        alive = False
        try:
            ws = getattr(WINDOW, 'windowStatus', None)
            if ws is not None and int(ws) < 4:
                uid = getattr(WINDOW, 'uniqueID', None)
                if uid:
                    alive = True
        except Exception:
            alive = False
        if alive:
            _apply_visible_flag()
            return WINDOW
        _log(u'stale window detected (status=%s) - recreating'
             % getattr(WINDOW, 'windowStatus', '?'))
        WINDOW = None

    if attempt == 0:
        _log_keys_status()
    reset_visible_sync()
    cx, cy = load_position_for(_MODE)
    WINDOW = classes['window']()
    WINDOW.load()
    _log(u'window created (mode=%s, visible=%s): uid=%s, saved x=%s y=%s'
         % (_MODE, IS_VISIBLE, getattr(WINDOW, 'uniqueID', '?'), cx, cy))
    if cx is not None and cy is not None:
        PANEL_STATE['x'] = int(cx)
        PANEL_STATE['y'] = int(cy)
        try:
            from . import app as _app
            _app.defer_pending_position((int(cx), int(cy)))
        except Exception:
            _retry_position((int(cx), int(cy)), 0)
    else:
        PANEL_STATE['x'] = None
        PANEL_STATE['y'] = None
    _apply_visible_flag()
    if not IS_VISIBLE and _MODE == 'hangar':
        _hide_panel()
    return WINDOW


def destroy_window():
    global WINDOW
    if WINDOW is None:
        return
    try:
        WINDOW.destroy()
        _log(u'window destroyed')
    except Exception as e:
        _log(u'window destroy failed: %r' % e)
    WINDOW = None


def get_model():
    if WINDOW is None:
        return None
    try:
        content = WINDOW.content
        if content is not None:
            return content.getViewModel()
    except Exception as e:
        _log(u'get_model failed: %r' % e)
    return None


def _move_window_to_card(x, y):
    if WINDOW is None:
        return False
    cx, cy = _clamp(x, y)
    try:
        ok = WINDOW.move(int(cx), int(cy))
    except Exception as e:
        _log(u'window.move failed: %r' % e)
        return False
    if ok:
        PANEL_STATE['x'] = cx
        PANEL_STATE['y'] = cy
    return bool(ok)


def push_panel_position():
    if PANEL_STATE['x'] is None or PANEL_STATE['y'] is None:
        return False
    model = get_model()
    if model is None:
        return False
    try:
        model._setNumber(1, int(PANEL_STATE['x']))
        model._setNumber(2, int(PANEL_STATE['y']))
        model._setNumber(3, 1)
        return True
    except Exception as e:
        _log(u'push_panel_position failed: %r' % e)
        return False


def persist_position():
    x = PANEL_STATE.get('x')
    y = PANEL_STATE.get('y')
    if x is None or y is None:
        return
    try:
        save_position_for(_MODE, int(x), int(y))
        _log(u'position saved (%s): x=%s y=%s' % (_MODE, x, y))
    except Exception as e:
        _log(u'persist_position failed: %r' % e)


def apply_window_position(x, y):
    if WINDOW is None:
        return False
    if _move_window_to_card(x, y):
        push_panel_position()
        return True
    _retry_position((int(x), int(y)), 0)
    return False


def _retry_position(target, attempt):
    if WINDOW is None:
        return
    if not IS_VISIBLE and _MODE == 'hangar':
        PANEL_STATE['x'] = int(target[0])
        PANEL_STATE['y'] = int(target[1])
        return
    if _move_window_to_card(target[0], target[1]):
        push_panel_position()
        _log(u'window positioned: x=%s y=%s' % target)
        return
    if attempt < MOVE_RETRY_MAX:
        BigWorld.callback(MOVE_RETRY_DELAY,
                          lambda: _retry_position(target, attempt + 1))
    else:
        _log(u'window position DEFERRED after %d attempts (target=%s)'
             % (attempt, target))
        try:
            from . import app as _app
            _app.defer_pending_position(target)
        except Exception as e:
            _log(u'defer pending position failed: %r' % e)


def apply_default_position(client_w, client_h):
    w, h = _screen_size()
    view = PANEL_STATE.get('view') or (200, 122)
    if _MODE == 'battle':
        x = max(DEFAULT_MARGIN, int(w) - int(view[0]) - DEFAULT_MARGIN)
        y = max(DEFAULT_MARGIN, int(h) - int(view[1]) - DEFAULT_MARGIN)
    else:
        x = max(DEFAULT_MARGIN, int(w) - int(view[0]) - DEFAULT_MARGIN)
        y = DEFAULT_MARGIN + 80
    PANEL_STATE['x'], PANEL_STATE['y'] = _clamp(x, y)
    _log(u'default position (%s): screen=%sx%s -> x=%s y=%s'
         % (_MODE, w, h, PANEL_STATE['x'], PANEL_STATE['y']))
    if not _move_window_to_card(x, y):
        _retry_position((x, y), 0)
    push_panel_position()
    persist_position()


def update_stats_model(snapshot):
    model = get_model()
    if model is None:
        return False
    try:
        pct = int(round(float(snapshot.get('percent', 0.0)) * 100))
        dlt = int(round(float(snapshot.get('delta', 0.0)) * 100))
        avg = int(snapshot.get('currentAvg', 0))
        nxt = int(snapshot.get('nextMarkValue', 0))
        has = bool(snapshot.get('hasNextMark', False))
        model._setNumber(5, pct)
        model._setNumber(6, dlt)
        model._setNumber(7, int(snapshot.get('marksOnGun', 0)))
        model._setNumber(8, avg)
        model._setNumber(9, int(snapshot.get('nextMarkPercent', 0)))
        model._setNumber(10, nxt)
        model._setBool(11, has)
        model._setBool(12, bool(snapshot.get('hasVehicle', False)))
        return True
    except Exception as e:
        _log(u'update_stats_model failed: %r' % e)
        return False


def reset_visible_sync():
    global _LAST_SYNCED_VISIBLE
    _LAST_SYNCED_VISIBLE = None


def _apply_visible_flag():
    global _LAST_SYNCED_VISIBLE
    model = get_model()
    if model is None:
        return
    try:
        state = bool(IS_VISIBLE)
        if _LAST_SYNCED_VISIBLE != state:
            model._setBool(4, state)
            _LAST_SYNCED_VISIBLE = state
    except Exception as e:
        _log(u'set visible flag failed: %r' % e)


def _hide_panel():
    global WINDOW
    if WINDOW is None:
        return
    _apply_visible_flag()
    if _MODE == 'battle':
        return
    try:
        WINDOW.hide(destroy=True)
        _log(u'panel hidden: window destroyed (hide destroy=True)')
    except Exception as e:
        _log(u'panel hide(destroy=True) failed: %r' % e)
    WINDOW = None


def _show_panel():
    if WINDOW is None:
        _recreate_soon(u'show: window missing')
        return
    x = PANEL_STATE['x']
    y = PANEL_STATE['y']
    if x is None or y is None:
        _apply_visible_flag()
        return
    moved = False
    try:
        moved = _move_window_to_card(x, y)
    except Exception as e:
        _log(u'show: move crashed: %r' % e)
    push_panel_position()
    _apply_visible_flag()
    _log(u'panel shown: css visible=1, window at %s,%s (move %s)'
         % (x, y, u'ok' if moved else u'failed'))


def prepare_battle():
    global IS_VISIBLE
    IS_VISIBLE = False
    reset_visible_sync()


def set_mode(mode):
    global _MODE
    if mode not in ('battle', 'hangar'):
        return
    if _MODE == mode:
        return
    old_x = PANEL_STATE.get('x')
    old_y = PANEL_STATE.get('y')
    if old_x is not None and old_y is not None:
        try:
            save_position_for(_MODE, old_x, old_y)
        except Exception:
            pass
    _MODE = mode
    try:
        loaded = load_position_for(mode)
    except Exception:
        _log(u'set_mode: load_position_for(%s) CRASHED:\n%s'
             % (mode, traceback.format_exc()))
        loaded = None
    if not loaded or len(loaded) != 2:
        nx, ny = (None, None)
    else:
        nx, ny = loaded
    PANEL_STATE['x'] = nx
    PANEL_STATE['y'] = ny
    _log(u'set_mode: %s -> pos=(%s, %s)' % (mode, nx, ny))


def set_visible(visible):
    global IS_VISIBLE
    new_state = bool(visible)
    if WINDOW is None:
        changed = (new_state != IS_VISIBLE)
        IS_VISIBLE = new_state
        if new_state and changed:
            _recreate_soon(u'show: window missing')
        return
    if new_state == IS_VISIBLE:
        _apply_visible_flag()
        return
    IS_VISIBLE = new_state
    if IS_VISIBLE:
        _show_panel()
    else:
        _hide_panel()


def _recreate_soon(reason):
    handler = WINDOW_LOST_HANDLER
    if handler is not None:
        BigWorld.callback(0.0, handler)
    else:
        _log(u'%s - no WINDOW_LOST_HANDLER' % reason)


def is_window_uid(uid):
    return WINDOW is not None and getattr(WINDOW, 'uniqueID', None) == uid


def is_window_alive():
    if WINDOW is None:
        return False
    try:
        uid = WINDOW.uniqueID
        if not uid:
            return False
        status = WINDOW.windowStatus
        if status is None:
            return True
        return int(status) not in (4, 5)
    except Exception:
        return False


def mark_window_destroyed(uid=None):
    global WINDOW
    if WINDOW is None:
        return
    if uid is None or getattr(WINDOW, 'uniqueID', None) == uid:
        WINDOW = None


def set_ready_handler(handler):
    global READY_HANDLER
    READY_HANDLER = handler


def set_window_lost_handler(handler):
    global WINDOW_LOST_HANDLER
    WINDOW_LOST_HANDLER = handler