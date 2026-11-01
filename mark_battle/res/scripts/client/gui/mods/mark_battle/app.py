# -*- coding: utf-8 -*-
#
# MarkBattle v1.0 - события боя + события ангара -> статистика -> окно + таблица.
#
from __future__ import print_function

import json
import os
import traceback

import BigWorld

from . import _log
from . import moe_info
from . import stats as stats_mod
from . import table_view
from . import view as view_mod

MOD_VERSION = '1.0.0'

CONF_DIR = 'mods/configs/mark_battle'
DOSSIER_CACHE_FILE = CONF_DIR + '/dossier_cache.json'

_started = False
_battle_active = False
_hangar_ready = False
_current_int_cd = 0
_last_damage = 0
_last_assist = 0
_dossier_cache = {}
_eff_ctrl = None
_bs_provider = None

CREATE_RETRY_MAX = 8
CREATE_RETRY_DELAY = 2.0

# Watchdog
_SF_WHITELIST = frozenset([
    u'lobby', u'waiting', u'login', u'lobbyVehicleMarkerView',
    u'GUIFlash', u'ModsListApiButton', u'GunMarksLebwaLobby',
    u'ProtankiFastdemountLobbyUI', u'xfw_injector',
    u'ReducedArmorMainUI', u'MasteryXPMOEUI', u'lobbyMenu',
    u'ModsListApiPopover', u'ModsSettingsApiWindow',
    u'BattlePassCarouselFilterPopover', u'exchangeXPWindow',
    u'exchangeWindow', u'notificationsList', u'SessionStatsPopover',
    u'SoundsComponentView', u'battleResults',
])

# --- Watchdog: числовые константы Wulf 1.2.2 (проверено на клиенте 1.46) ---
#
# Если после обновления Лесты watchdog перестал замечать модалки/уведомления
# или, наоборот, начал ложно прятать панель под немодальными окнами —
# ПЕРВЫМ ДЕЛОМ перепроверить именно эти константы по исходникам:
#   frameworks/wulf/__init__.py            (WindowLayer, WindowFlags)
#   frameworks/wulf/windows_system/window.py (windowFlags, layer)
# в репозитории wotstat/wot-src (ветка mt-ru) для актуальной версии.
#
# _WULF_LAYERS_SKIP     — слои, на которых окна не считаются блокерами
#                         (напр. фон ангара и загрузочные оверлеи).
# _WULF_LAYER_WINDOW    — слой обычных окон; на нём блокерами считаются
#                         только модальные окна (см. _WULF_MODALITY_MASK).
# _WULF_MODALITY_MASK   — битовая маска WindowFlags, определяющая «модальность»
#                         окна (сейчас 0x3000).
# _WULF_IGNORE_TYPES    — типы (windowFlags & 0xFF), которые НЕ должны
#                         скрывать панель (tooltip, уведомления и т.п.).
_WULF_LAYERS_SKIP = frozenset([4, 14])
_WULF_CLASS_SKIP = frozenset([u'MarkBattleView',
                              u'MarkBattleTableView',
                              u'SilverHudView',
                              u'TankCardView',
                              u'SilverBattleView'])
_WULF_LAYER_WINDOW = 7
_WULF_MODALITY_MASK = 12288
_WULF_IGNORE_TYPES = frozenset([8, 33, 49, 65, 81, 98, 114])

_own_uid = None
_recreate_budget = 12
_sf_blockers = set()
_wulf_blockers = set()
_sf_view_ids = {}
_last_vis_key = None
_window_pending_pos = None


def init(version):
    global MOD_VERSION
    MOD_VERSION = version
    _log(u'module init requested, version=%s' % version)
    try:
        from . import ensure_res_map_configs
        written, info = ensure_res_map_configs()
        _log(u'res_map configs ensured (written=%d): %s' % (written, info))
    except Exception as e:
        _log(u'ensure_res_map_configs crashed: %r' % e)
    try:
        from gui.shared import g_eventBus, events, EVENT_BUS_SCOPE
        g_eventBus.addListener(events.AppLifeCycleEvent.INITIALIZED,
                               _on_app_initialized,
                               scope=EVENT_BUS_SCOPE.GLOBAL)
    except Exception as e:
        _log(u'eventBus subscribe failed: %r' % e)
    BigWorld.callback(8.0, _ensure_started)


def _log_version(msg):
    _log(u'v%s: %s' % (MOD_VERSION, msg))


def _ensure_started():
    if not _started:
        _log_version(u'fallback start (INITIALIZED event missed?)')
        _start()


def _on_app_initialized(event):
    _start()


def _start():
    global _started
    if _started:
        return
    _started = True
    try:
        view_mod.set_ready_handler(on_js_ready)
        view_mod.set_window_lost_handler(_recreate_window)
        moe_info.init_cache()
        moe_info.set_ready_callback(_on_moe_ready)
        _load_dossier_cache()
        _subscribe_hangar_vehicle()
        _subscribe_items_cache()
        _subscribe_player_events()
        _subscribe_battle_session()
        _hook_hangar()
        _hook_loader_manager()
        _hook_container_tracking()
        _hook_wulf_showing()
    except Exception:
        _log(u'_start CRASHED:\n%s' % traceback.format_exc())
        return
    _log_version(u'started (battle + hangar + table)')


def _load_dossier_cache():
    global _dossier_cache
    try:
        if os.path.isfile(DOSSIER_CACHE_FILE):
            with open(DOSSIER_CACHE_FILE, 'r') as f:
                _dossier_cache = json.load(f)
            _log(u'dossier cache loaded: %d entries' % len(_dossier_cache))
    except Exception as e:
        _log(u'_load_dossier_cache failed: %r' % e)
        _dossier_cache = {}


def _save_dossier_cache():
    try:
        if not os.path.exists(CONF_DIR):
            os.makedirs(CONF_DIR)
        with open(DOSSIER_CACHE_FILE, 'w') as f:
            json.dump(_dossier_cache, f)
    except Exception as e:
        _log(u'_save_dossier_cache failed: %r' % e)


def _read_dossier(int_cd):
    if int_cd <= 0:
        return None
    try:
        from skeletons.gui.shared import IItemsCache
        from helpers import dependency
        items_cache = dependency.instance(IItemsCache)
        dossier = items_cache.items.getVehicleDossier(int_cd)
        if dossier is None:
            return None
        return stats_mod.dossier_to_dict(dossier)
    except Exception as e:
        _log(u'_read_dossier(%s) failed: %r' % (int_cd, e))
        return None


def _cache_dossier(int_cd, source=u'?'):
    old_entry = _dossier_cache.get(str(int_cd), {})
    old_percent = float(old_entry.get('damageRating', 0.0))
    old_delta = float(old_entry.get('lastDelta', 0.0))

    d = _read_dossier(int_cd)
    if d is None:
        return
    if stats_mod.is_dossier_dict_empty(d):
        return

    new_percent = float(d.get('damageRating', 0.0))
    if old_percent > 0 and new_percent > 0 and abs(new_percent - old_percent) > 0.001:
        d['lastDelta'] = round(new_percent - old_percent, 2)
    else:
        d['lastDelta'] = old_delta

    _dossier_cache[str(int_cd)] = d
    _save_dossier_cache()


def _subscribe_hangar_vehicle():
    try:
        from CurrentVehicle import g_currentVehicle
        try:
            g_currentVehicle.onChanged -= _on_hangar_vehicle_changed
        except Exception:
            pass
        g_currentVehicle.onChanged += _on_hangar_vehicle_changed
        BigWorld.callback(1.0, _on_hangar_vehicle_changed)
    except Exception as e:
        _log(u'hangar vehicle subscribe failed: %r' % e)


def _on_hangar_vehicle_changed(*args, **kwargs):
    global _current_int_cd
    try:
        from CurrentVehicle import g_currentVehicle
        if not g_currentVehicle.isPresent():
            return
        item = g_currentVehicle.item
        if item is None:
            return
        int_cd = int(getattr(item, 'intCD', 0) or 0)
        if int_cd <= 0:
            return
        if _battle_active:
            return
        _current_int_cd = int_cd
        _cache_dossier(int_cd, u'hangar')
        moe_info.ensure_requested(int_cd)
        if _hangar_ready:
            _push_stats(force=True)
    except Exception:
        _log(u'_on_hangar_vehicle_changed CRASHED:\n%s'
             % traceback.format_exc())


def _on_moe_ready(int_cd, data):
    if _current_int_cd == int_cd or _battle_active:
        _push_stats(force=True)
    if table_view.is_table_open():
        table_view.push_table_data()


def _subscribe_player_events():
    try:
        from PlayerEvents import g_playerEvents
        try:
            g_playerEvents.onAvatarBecomePlayer -= _on_avatar_become_player
            g_playerEvents.onAvatarBecomeNonPlayer -= _on_avatar_become_non_player
        except Exception:
            pass
        g_playerEvents.onAvatarBecomePlayer += _on_avatar_become_player
        g_playerEvents.onAvatarBecomeNonPlayer += _on_avatar_become_non_player
    except Exception as e:
        _log(u'playerEvents subscribe failed: %r' % e)


def _subscribe_items_cache():
    try:
        from skeletons.gui.shared import IItemsCache
        from helpers import dependency
        items_cache = dependency.instance(IItemsCache)
        try:
            items_cache.onSyncCompleted -= _on_items_cache_sync
        except Exception:
            pass
        items_cache.onSyncCompleted += _on_items_cache_sync
    except Exception as e:
        _log(u'itemsCache subscribe failed: %r' % e)
        BigWorld.callback(2.0, _subscribe_items_cache)


def _on_items_cache_sync(*args, **kwargs):
    global _current_int_cd
    if _current_int_cd > 0:
        _cache_dossier(_current_int_cd, u'after-sync')
        moe_info.ensure_requested(_current_int_cd)
    try:
        from CurrentVehicle import g_currentVehicle
        if g_currentVehicle.isPresent() and g_currentVehicle.item is not None:
            int_cd = int(getattr(g_currentVehicle.item, 'intCD', 0) or 0)
            if int_cd > 0 and int_cd != _current_int_cd and not _battle_active:
                _current_int_cd = int_cd
                _cache_dossier(int_cd, u'after-sync-hangar')
                moe_info.ensure_requested(int_cd)
    except Exception:
        pass
    if _hangar_ready and not _battle_active:
        _push_stats(force=True)
        if table_view.is_table_open():
            table_view.push_table_data()


def _subscribe_battle_session():
    try:
        from helpers import dependency
        from skeletons.gui.battle_session import IBattleSessionProvider
        try:
            sp = dependency.instance(IBattleSessionProvider)
        except Exception:
            sp = None
        if sp is None:
            BigWorld.callback(2.0, _subscribe_battle_session)
            return
        global _bs_provider
        _bs_provider = sp
        try:
            sp.onBattleSessionStart -= _on_battle_session_start
            sp.onBattleSessionStop -= _on_battle_session_stop
        except Exception:
            pass
        sp.onBattleSessionStart += _on_battle_session_start
        sp.onBattleSessionStop += _on_battle_session_stop
    except Exception as e:
        _log(u'battle session subscribe failed: %r' % e)
        BigWorld.callback(2.0, _subscribe_battle_session)


def _on_battle_session_start(*args, **kwargs):
    global _eff_ctrl, _battle_active, _last_damage, _last_assist
    _battle_active = True
    _last_damage = 0
    _last_assist = 0
    try:
        sp = _bs_provider
        if sp is None:
            from helpers import dependency
            from skeletons.gui.battle_session import IBattleSessionProvider
            sp = dependency.instance(IBattleSessionProvider)
        ctrl = sp.shared.personalEfficiencyCtrl if sp is not None else None
        if ctrl is None:
            return
        try:
            ctrl.onTotalEfficiencyUpdated -= _on_total_efficiency
        except Exception:
            pass
        ctrl.onTotalEfficiencyUpdated += _on_total_efficiency
        _eff_ctrl = ctrl
    except Exception as e:
        _log(u'battle session start failed: %r' % e)


def _on_battle_session_stop(*args, **kwargs):
    global _eff_ctrl
    if _eff_ctrl is not None:
        try:
            _eff_ctrl.onTotalEfficiencyUpdated -= _on_total_efficiency
        except Exception:
            pass
        _eff_ctrl = None


def _on_total_efficiency(diff):
    global _last_damage, _last_assist
    if not _battle_active:
        return
    try:
        from gui.battle_control.battle_constants import PERSONAL_EFFICIENCY_TYPE
    except ImportError:
        return
    try:
        changed = False
        if PERSONAL_EFFICIENCY_TYPE.DAMAGE in diff:
            d = int(diff[PERSONAL_EFFICIENCY_TYPE.DAMAGE] or 0)
            if d > _last_damage:
                _last_damage = d
                changed = True
        if PERSONAL_EFFICIENCY_TYPE.ASSIST_DAMAGE in diff:
            a = int(diff[PERSONAL_EFFICIENCY_TYPE.ASSIST_DAMAGE] or 0)
            if a > _last_assist:
                _last_assist = a
                changed = True
        if changed:
            _push_stats()
    except Exception as e:
        _log(u'_on_total_efficiency failed: %r' % e)


def _is_battle_hud_ready():
    """Возвращает True, когда экран загрузки карты уже закрылся:
    1) период арены перешёл в PREBATTLE (2) или BATTLE (3);
    2) 3D-сущность танка игрока появилась в мире и флаг arenaLoaded (если есть) активен."""
    try:
        player = BigWorld.player()
        if player is None:
            return False
        arena = getattr(player, 'arena', None)
        if arena is None:
            return False
        period = int(getattr(arena, 'period', 0) or 0)
        if period not in (2, 3):
            return False
        veh_id = int(getattr(player, 'playerVehicleID', 0) or 0)
        if veh_id <= 0:
            return False
        entity = BigWorld.entity(veh_id)
        if entity is None:
            return False
        # Если в PlayerAvatar есть флаг __isOnArena / arenaLoaded — проверяем и его
        if hasattr(player, 'onArenaLoaded'):
            is_on_arena = getattr(player, '_PlayerAvatar__isOnArena', None)
            if is_on_arena is False:
                return False
        return True
    except Exception:
        return False


def _battle_hud_poll():
    """Следит за состоянием боя: скрывает панель на экране загрузки карты
    и в послебоевой фазе (period == 4), показывает на отсчёте и в бою."""
    if not _battle_active:
        return
    ready = _is_battle_hud_ready()
    if ready != view_mod.IS_VISIBLE:
        view_mod.set_visible(ready)
        if ready:
            _push_stats(force=True)
    BigWorld.callback(0.25, _battle_hud_poll)


def _on_avatar_become_player(*args, **kwargs):
    global _battle_active, _hangar_ready
    global _current_int_cd, _last_damage, _last_assist, _last_vis_key
    _battle_active = True
    _hangar_ready = False
    _last_damage = 0
    _last_assist = 0
    _current_int_cd = 0
    table_view.close_table_window()
    view_mod.set_mode('battle')
    _sf_blockers.clear()
    _wulf_blockers.clear()
    _last_vis_key = None
    view_mod.prepare_battle()
    BigWorld.callback(0.5, lambda: _try_create_window(0))
    BigWorld.callback(0.5, _int_cd_poll)
    BigWorld.callback(0.3, _battle_hud_poll)


def _on_avatar_become_non_player(*args, **kwargs):
    global _battle_active
    _battle_active = False
    try:
        view_mod.destroy_window()
    except Exception:
        _log(u'_on_avatar_become_non_player destroy CRASHED:\n%s'
             % traceback.format_exc())


def _int_cd_poll():
    global _current_int_cd
    if not _battle_active or _current_int_cd > 0:
        return
    int_cd = _read_current_int_cd()
    if int_cd > 0:
        _current_int_cd = int_cd
        if str(int_cd) not in _dossier_cache:
            _cache_dossier(int_cd, u'battle-fallback')
        moe_info.ensure_requested(int_cd)
        _push_stats(force=True)
    else:
        BigWorld.callback(0.5, _int_cd_poll)


def _hook_hangar():
    try:
        from gui.Scaleform.daapi.view.lobby.hangar.Hangar import Hangar
        if getattr(Hangar, '_markbattle_hooked', False):
            return
        old_populate = Hangar._populate

        def _new_populate(self, *args, **kwargs):
            result = old_populate(self, *args, **kwargs)
            BigWorld.callback(1.0, _on_hangar_entered)
            return result

        Hangar._populate = _new_populate
        Hangar._markbattle_hooked = True
    except Exception as e:
        _log(u'hangar hook failed: %r' % e)


def _on_hangar_entered():
    global _hangar_ready, _battle_active, _recreate_budget
    global _current_int_cd, _last_damage, _last_assist
    global _own_uid, _last_vis_key
    _hangar_ready = True
    _battle_active = False
    _recreate_budget = 12
    _last_damage = 0
    _last_assist = 0
    if _sf_blockers:
        _sf_blockers.clear()
    if _wulf_blockers:
        _wulf_blockers.clear()
    _last_vis_key = None
    _subscribe_hangar_vehicle()
    try:
        view_mod.set_mode('hangar')
    except Exception:
        pass
    try:
        from CurrentVehicle import g_currentVehicle
        if g_currentVehicle.isPresent() and g_currentVehicle.item is not None:
            _current_int_cd = int(getattr(g_currentVehicle.item, 'intCD', 0) or 0)
    except Exception:
        pass
    try:
        if not view_mod.is_window_alive():
            _try_create_window(0)
        else:
            _own_uid = getattr(view_mod.WINDOW, 'uniqueID', None)
            view_mod.push_panel_position()
        _push_stats(force=True)
        _recompute_panel_visibility()
    except Exception:
        _log(u'on_hangar_entered CRASHED:\n%s' % traceback.format_exc())


def _read_current_int_cd():
    try:
        player = BigWorld.player()
        if player is None:
            return 0
        veh_id = int(getattr(player, 'playerVehicleID', 0) or 0)
        if veh_id:
            entity = BigWorld.entity(veh_id)
            if entity is not None:
                vd = getattr(entity, 'typeDescriptor', None)
                if vd is not None:
                    t = getattr(vd, 'type', None)
                    if t is not None:
                        cd = getattr(t, 'compactDescr', 0)
                        if cd:
                            return int(cd)
        try:
            vDesc = getattr(player, 'vehicleTypeDescriptor', None)
            if vDesc is not None:
                t = getattr(vDesc, 'type', None)
                if t is not None:
                    cd = getattr(t, 'compactDescr', 0)
                    if cd:
                        return int(cd)
        except Exception:
            pass
    except Exception:
        pass
    return 0


def _read_vehicle_info():
    info = {'intCD': _current_int_cd, 'name': u'',
            'tags': frozenset(), 'level': 0}
    if _current_int_cd <= 0:
        return info
    try:
        from items import vehicles
        descr = vehicles.getItemByCompactDescr(_current_int_cd)
        if descr is not None:
            try:
                info['name'] = descr.userString or u''
            except Exception:
                pass
            try:
                info['tags'] = frozenset(descr.type.tags or [])
            except Exception:
                info['tags'] = frozenset()
            try:
                info['level'] = int(descr.level or 0)
            except Exception:
                info['level'] = 0
    except Exception:
        pass
    return info


def _push_stats(force=False):
    if not (_battle_active or _hangar_ready) and not force:
        return
    try:
        veh = _read_vehicle_info()
        cached = _dossier_cache.get(str(_current_int_cd))
        thresholds = moe_info.get_thresholds(_current_int_cd)
        snap = stats_mod.build_snapshot(
            cached, veh, _last_damage, _last_assist, thresholds)
        view_mod.update_stats_model(snap)
    except Exception:
        _log(u'_push_stats CRASHED:\n%s' % traceback.format_exc())


def _try_create_window(attempt):
    global _own_uid
    if not (_battle_active or _hangar_ready):
        return
    try:
        window = view_mod.create_window(MOD_VERSION, attempt)
    except Exception:
        _log(u'create_window CRASHED:\n%s' % traceback.format_exc())
        return
    if window is not None:
        _own_uid = getattr(window, 'uniqueID', None)
        _push_stats(force=True)
        return
    if attempt < CREATE_RETRY_MAX:
        BigWorld.callback(CREATE_RETRY_DELAY,
                          lambda: _try_create_window(attempt + 1))


def _recreate_window():
    global _own_uid, _recreate_budget
    if not (_battle_active or _hangar_ready):
        return
    if _recreate_budget <= 0:
        return
    _recreate_budget -= 1
    try:
        window = view_mod.create_window(MOD_VERSION, 1)
        if window is not None:
            _own_uid = getattr(window, 'uniqueID', None)
    except Exception:
        return
    _push_stats(force=True)
    _recompute_panel_visibility()


def _hook_loader_manager():
    try:
        from gui.Scaleform.framework.managers import loaders as _loaders_mod
    except Exception as e:
        _log(u'WATCHDOG: LoaderManager import failed, SF view tracking OFF: %r' % e)
        return
    cls = getattr(_loaders_mod, 'LoaderManager', None)
    if cls is None:
        _log(u'WATCHDOG: LoaderManager class not found, SF view tracking OFF')
        return
    if getattr(cls, '_markbattle_lm_hooked', False):
        return
    orig_loadView = cls.loadView

    def _new_loadView(self, loadParams, *args, **kwargs):
        try:
            key = getattr(loadParams, 'viewKey', None)
            alias = getattr(key, 'alias', None) if key is not None else None
            _on_view_load(alias)
        except Exception:
            pass
        return orig_loadView(self, loadParams, *args, **kwargs)

    cls.loadView = _new_loadView
    cls._markbattle_lm_hooked = True


def _on_view_load(alias):
    if not isinstance(alias, (str, unicode)):
        return
    alias = unicode(alias)
    if alias == u'hangar':
        if _sf_blockers:
            _sf_blockers.clear()
        _recompute_panel_visibility()
        return
    if alias in _SF_WHITELIST:
        return
    if alias not in _sf_blockers:
        _sf_blockers.add(alias)
        _recompute_panel_visibility()


def _hook_container_tracking():
    try:
        from gui.Scaleform.framework.managers.containers import ViewContainer
    except Exception as e:
        _log(u'WATCHDOG: ViewContainer import failed, container tracking OFF: %r' % e)
        return
    if getattr(ViewContainer, '_markbattle_ct_hooked', False):
        return
    orig_addView = ViewContainer.addView
    orig_removeView = ViewContainer._removeView

    def _new_addView(self, pyView):
        result = orig_addView(self, pyView)
        try:
            if result:
                _on_sf_added(pyView)
        except Exception:
            pass
        return result

    def _new_removeView(self, pyView):
        try:
            _on_sf_removed(pyView)
        except Exception:
            pass
        return orig_removeView(self, pyView)

    ViewContainer.addView = _new_addView
    ViewContainer._removeView = _new_removeView
    ViewContainer._markbattle_ct_hooked = True


def _on_sf_added(pyView):
    key = getattr(pyView, 'key', None)
    alias = getattr(key, 'alias', None) if key is not None else None
    if alias is None:
        return
    alias = unicode(alias)
    _sf_view_ids[id(pyView)] = alias
    if alias == u'hangar':
        if _sf_blockers:
            _sf_blockers.clear()
            _recompute_panel_visibility()
        return
    if alias in _SF_WHITELIST:
        return
    if alias not in _sf_blockers:
        _sf_blockers.add(alias)
        _recompute_panel_visibility()


def _on_sf_removed(pyView):
    alias = _sf_view_ids.pop(id(pyView), None)
    if alias is None or alias in _SF_WHITELIST:
        return
    if alias in _sf_blockers:
        _sf_blockers.discard(alias)
        _recompute_panel_visibility()


def _hook_wulf_showing():
    try:
        from frameworks.wulf.windows_system.window import Window
    except Exception:
        try:
            from frameworks.wulf.window import Window
        except Exception as e:
            _log(u'WATCHDOG: Window import failed, Wulf blocker detection OFF: %r' % e)
            return
    if getattr(Window, '_markbattle_wt_hooked', False):
        return
    orig = Window._cShowingStatusChanged

    def _new(self, old_status, new_status, *args, **kwargs):
        try:
            _on_wulf_showing(self, new_status)
        except Exception:
            pass
        return orig(self, old_status, new_status, *args, **kwargs)

    Window._cShowingStatusChanged = _new
    Window._markbattle_wt_hooked = True


def _on_wulf_showing(win, new_status):
    uid = getattr(win, 'uniqueID', None)
    if uid is None:
        return
    if uid == _own_uid:
        if new_status in (0, 1):
            _flush_pending_position()
        return
    if uid == table_view.get_table_uid():
        return
    content = getattr(win, 'content', None)
    cls = type(content).__name__ if content is not None else u'?'
    if cls in _WULF_CLASS_SKIP:
        return
    layer = getattr(win, 'layer', None)
    if layer in _WULF_LAYERS_SKIP:
        return
    flags = getattr(win, 'windowFlags', 0) or 0
    if (int(flags) & 255) in _WULF_IGNORE_TYPES:
        return
    if layer == _WULF_LAYER_WINDOW:
        is_modal = False
        try:
            checker = getattr(win, 'isModal', None)
            if callable(checker):
                is_modal = bool(checker())
            else:
                is_modal = bool(int(flags) & _WULF_MODALITY_MASK)
        except Exception:
            is_modal = True
        if not is_modal:
            return
    visible = new_status in (0, 1)
    if visible:
        if uid not in _wulf_blockers:
            _wulf_blockers.add(uid)
            _recompute_panel_visibility()
    else:
        if uid in _wulf_blockers:
            _wulf_blockers.discard(uid)
            _recompute_panel_visibility()


def _recompute_panel_visibility():
    global _last_vis_key
    if not _hangar_ready or _battle_active:
        return
    visible = (len(_sf_blockers) == 0) and (len(_wulf_blockers) == 0)
    key = (visible, tuple(sorted(_sf_blockers)), tuple(sorted(_wulf_blockers)))
    if key == _last_vis_key:
        return
    _last_vis_key = key
    if not visible and table_view.is_table_open():
        table_view.close_table_window()
    view_mod.set_visible(visible)


def _flush_pending_position():
    global _window_pending_pos
    if _window_pending_pos is None:
        return
    if _own_uid is None or view_mod.WINDOW is None:
        _window_pending_pos = None
        return
    if view_mod.is_window_uid(_own_uid):
        try:
            view_mod.apply_window_position(*_window_pending_pos)
        except Exception:
            pass
    _window_pending_pos = None


def defer_pending_position(target):
    global _window_pending_pos
    _window_pending_pos = (int(target[0]), int(target[1]))


def on_js_ready(client_w, client_h, card_w, card_h):
    view_mod.push_panel_position()
    if view_mod.PANEL_STATE['x'] is None:
        BigWorld.callback(0.5, lambda: view_mod.apply_default_position(
            client_w, client_h))
    BigWorld.callback(0.2, lambda: _push_stats(force=True))