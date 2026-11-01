# Разработка боевых модов на Gameface для «Мира танков»

Практическое руководство. Версия 2 (обновлена по итогам разработки MarkBattle и SilverBattle на клиенте MT 1.45).

---

## Что нового в версии 2

- **Команды модели (`_addCommand`) ненадёжны в Coherent Gameface.** Иногда вызов из JS не доходит до Python. Обходное решение — пускать критичные команды через `ready` с флагом.
- **Досье в бою — только из кэша.** Подтверждено на живых боях.
- **Урон обнуляется в конце боя.** Защита `if d > _last_damage` обязательна.
- **Порогов отметок 9, а не 4.** Нужна интерполяция, а не линейный коэффициент.
- **`moe_info._pending` требует timeout.** Иначе запрос зависает навсегда.
- **Вертикальный градиент прозрачности в SVG работает.** Как у Near You.
- **`BattleResultsService.getResultsVO` — универсальный источник данных после боя.**
- **Имя `.mtmod` без префикса автора работает.** Проверено на `silver_battle.mtmod`.
- **Разделение логов на критичные и шумные.**

Ресурсы игры Мир Танков:
https://github.com/wotstat/wot-src/tree/mt-ru/sources

Online analytics и ресурсы для Мира Танков
https://github.com/wotstat
https://github.com/wotstat/wot-src/tree/mt-ru/sources

---

## Оглавление

1. [Введение](#1-введение)
2. [Отличия боевого мода от ангарного](#2-отличия-боевого-мода-от-ангарного)
3. [Предварительные требования](#3-предварительные-требования)
4. [Структура проекта](#4-структура-проекта)
5. [Жизненный цикл боя](#5-жизненный-цикл-боя)
6. [Источники данных в бою](#6-источники-данных-в-бою)
7. [Окно в боевом интерфейсе](#7-окно-в-боевом-интерфейсе)
8. [Команды и надёжность моста Python↔JS](#8-команды-и-надёжность-моста-pythonjs)
9. [Драг в бою](#9-драг-в-бою)
10. [UI для боя](#10-ui-для-боя)
11. [Логирование: что оставлять, что убирать](#11-логирование-что-оставлять-что-убирать)
12. [Сборка и установка](#12-сборка-и-установка)
13. [Типичные ошибки](#13-типичные-ошибки)
14. [Приложение: полезные API](#14-приложение-полезные-api)

---

## 1. Введение

**Боевой мод** — активируется при загрузке боя и уничтожается при возврате в ангар. Обычно показывает оверлей поверх боевого интерфейса.

**Чем отличается от ангарного:**

| Ангарный | Боевой |
|---|---|
| `g_currentVehicle`, `IItemsCache` работают | Игрок = `BigWorld.player()`, танк = `BigWorld.entity(playerVehicleID)` |
| Загружается один раз | Пересоздаётся на каждый бой |
| Окно живёт постоянно | Уничтожается при выходе из боя |
| Старт — `Hangar._populate` | Старт — `onAvatarBecomePlayer` |
| Спокойный фон ангара | Шумный бой — UI должен быть ненавязчивым |

**Ключевое правило:** окно создаётся **после** `onAvatarBecomePlayer` и уничтожается при `onAvatarBecomeNonPlayer`. Иначе wulf-окно перехватит клики в ангаре.

---

## 2. Отличия боевого мода от ангарного

### 2.1. intCD в бою запаздывает

В ангаре `g_currentVehicle.item.intCD`. В бою этот синглтон пуст.

Сразу после `onAvatarBecomePlayer` **ни `playerVehicleID`, ни дескриптор ещё не готовы**. Нужен опрос раз в 0.5 сек.

### 2.2. Досье в бою не читается

`IItemsCache.items.getVehicleDossier(int_cd)` в бою отдаёт **пустой объект**. Синк досье происходит только в ангаре.

**Решение:** читать в ангаре, кэшировать в JSON, в бою брать из кэша.

### 2.3. Размер экрана

`viewEnv.getClientSizePx()` в бою возвращает **логическую** площадь интерфейса (1920×1080 вместо 2560×1440). Использовать **только** `BigWorld.screenSize()` на Python-стороне.

### 2.4. DOM-события мыши за границей окна

При драге, когда курсор выходит за 200×140, `mousemove`/`mouseup` не доставляются. Решение — `GUI.mcursor()` + проверка `BigWorld.isKeyDown(KEY_LEFTMOUSE)`.

### 2.5. Команды модели могут не доходить

**Главное открытие последних сессий.** Команды, зарегистрированные через `_addCommand('xxx')`, **иногда не вызываются** из JS — особенно если имя команды короткое (`resetSession`) или конфликтует с чем-то в клиенте. Диагностика: в Python `_onResetSession` не логирует вызов, хотя в JS `window.model.resetSession({})` выполняется без ошибки.

**Обходное решение:** для критичных действий использовать `ready` с флагом. См. раздел 8.

---

## 3. Предварительные требования

### 3.1. `net.openwg.gameface`

Мод-пак `net.openwg.gameface_1.1.6.mtmod` в `<game>/mods/<версия>/`. Без него боевое окно не зарегистрируется.

### 3.2. Python 2.7.18

Строго 2.7.18 — байткод клиента совместим только с этой версией.

### 3.3. Декомпилированные исходники

- `izeberg/wot-src` — код клиента.
- `wotstat/wotstat-data-provider` — примеры боевых провайдеров.

### 3.4. IDE

VSCode или PyCharm. Синтаксис — совместим с Python 2.7 (никаких f-строк, `yield from`, `async`).

---

## 4. Структура проекта

```
mark_battle/
├── build.py
├── build.bat
├── meta.xml
├── mods/configs/res_map/
│   └── mark_battle.json
└── res/
    ├── scripts/client/gui/mods/
    │   ├── mod_mark_battle.py
    │   └── mark_battle/
    │       ├── __init__.py          # ВАЖНО: имя файла — строго __init__.py
    │       ├── app.py
    │       ├── view.py
    │       ├── stats.py
    │       └── moe_info.py
    └── gui/gameface/mods/mark_battle/
        ├── index.html
        ├── index.css
        ├── index.js
        ├── star_empty.svg
        ├── star_filled.svg
        ├── tank_empty.svg
        ├── tank_filled_green.svg
        ├── tank_filled_red.svg
        └── tank_filled_gray.svg
```

**Правила:**
- Править только файлы в `res/`. Копия в `mods/gui` — генерируемая.
- `__init__.py` нельзя переименовывать в `_init__.py` — иначе Python не распознает пакет, и получите `ImportError: No module named silver_battle`.
- `.svg` обязательно должен быть в `INCLUDE_EXT` в `build.py`.
- Имя `.mtmod` может быть без префикса автора (`silver_battle.mtmod`) — проверено, работает.

---

## 5. Жизненный цикл боя

### 5.1. События

| Событие | Когда | Что делать |
|---|---|---|
| `g_playerEvents.onAvatarBecomePlayer` | Игрок вошёл в бой | Создать окно, подписаться на `personalEfficiencyCtrl` |
| `g_playerEvents.onAvatarBecomeNonPlayer` | Игрок вышел из боя | Уничтожить окно, отписаться |
| `IBattleSessionProvider.onBattleSessionStart` | Начало сессии | Подписка на данные урона |
| `IBattleSessionProvider.onBattleSessionStop` | Конец сессии | Отписка |

### 5.2. Подписка

```python
def _subscribe_player_events():
    from PlayerEvents import g_playerEvents
    try:
        g_playerEvents.onAvatarBecomePlayer -= _on_avatar_become_player
        g_playerEvents.onAvatarBecomeNonPlayer -= _on_avatar_become_non_player
    except Exception:
        pass
    g_playerEvents.onAvatarBecomePlayer += _on_avatar_become_player
    g_playerEvents.onAvatarBecomeNonPlayer += _on_avatar_become_non_player
```

### 5.3. Обработчики

```python
def _on_avatar_become_non_player(*args, **kwargs):
    global _battle_active, _hangar_ready, _last_vis_key
    _battle_active = False
    _hangar_ready = False
    # Гибридный мод (работает и в бою, и в ангаре): чистим блокеры
    # watchdog'а. При выходе из боя клиент рвёт battle-space целиком,
    # _removeView для боевых SF-вьюх не вызывается — блокеры залипают,
    # и при возврате в ангар панель не показывается.
    if _sf_blockers:
        _sf_blockers.clear()
    if _wulf_blockers:
        _wulf_blockers.clear()
    _last_vis_key = None
    # Помечаем окно мёртвым, НЕ вызываем destroy вручную: space сейчас
    # сменится, окно умрёт само. Иначе рискуем словить краш прокси.
    view_mod.mark_window_destroyed()
    # НЕ читать досье здесь — клиент ещё не синкнул данные..
```

Окно **обязательно** уничтожать при выходе в ангар — иначе перехватит клики в ангаре.

---

## 6. Источники данных в бою

### 6.1. intCD текущего танка

```python
def _read_current_int_cd():
    try:
        player = BigWorld.player()
        if player is None:
            return 0
        # Путь 1: через entity (самый надёжный)
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
        # Путь 2: fallback через player.vehicleTypeDescriptor
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
    except Exception as e:
        _log(u'_read_current_int_cd failed: %r' % e)
    return 0


def _int_cd_poll():
    global _current_int_cd
    if not _battle_active or _current_int_cd > 0:
        return
    int_cd = _read_current_int_cd()
    if int_cd > 0:
        _current_int_cd = int_cd
        _push_stats(force=True)
    else:
        BigWorld.callback(0.5, _int_cd_poll)
```

### 6.2. Урон и помощь

```python
from gui.battle_control.battle_constants import PERSONAL_EFFICIENCY_TYPE

def _on_total_efficiency(diff):
    global _last_damage, _last_assist
    if not _battle_active:
        return
    try:
        changed = False
        if PERSONAL_EFFICIENCY_TYPE.DAMAGE in diff:
            d = int(diff[PERSONAL_EFFICIENCY_TYPE.DAMAGE] or 0)
            if d > _last_damage:      # ← строго >, не !=
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
```

**Критично:**
- Значения в `diff` — **абсолютные**, не приращения.
- В конце боя клиент присылает `dmg=0`. Защита `if d > _last_damage` игнорирует сброс.

### 6.3. Досье — кэш в ангаре

```python
def _subscribe_hangar_vehicle():
    from CurrentVehicle import g_currentVehicle
    try:
        g_currentVehicle.onChanged -= _on_hangar_vehicle_changed
    except Exception:
        pass
    g_currentVehicle.onChanged += _on_hangar_vehicle_changed
    BigWorld.callback(1.0, _on_hangar_vehicle_changed)


def _on_hangar_vehicle_changed(*args, **kwargs):
    from CurrentVehicle import g_currentVehicle
    if not g_currentVehicle.isPresent():
        return
    item = g_currentVehicle.item
    if item is None:
        return
    int_cd = int(getattr(item, 'intCD', 0) or 0)
    if int_cd > 0:
        _cache_dossier(int_cd, u'hangar')
        moe_info.ensure_requested(int_cd)


def _cache_dossier(int_cd, source=u'?'):
    old_entry = _dossier_cache.get(str(int_cd), {})
    old_percent = float(old_entry.get('damageRating', 0.0))
    old_delta = float(old_entry.get('lastDelta', 0.0))

    from skeletons.gui.shared import IItemsCache
    from helpers import dependency
    items_cache = dependency.instance(IItemsCache)
    dossier = items_cache.items.getVehicleDossier(int_cd)
    if dossier is None:
        return

    rating_raw = dossier.getRecordValue('achievements', 'damageRating') or 0
    moving_avg = dossier.getRecordValue('achievements', 'movingAvgDamage') or 0
    marks = dossier.getRecordValue('achievements', 'marksOnGun') or 0
    battles = dossier.getRandomStats().getBattlesCount()

    new_percent = rating_raw / 100.0
    new_entry = {
        'damageRating': round(new_percent, 2),
        'movingAvgDamage': int(moving_avg),
        'marksOnGun': int(marks),
        'battlesCount': int(battles),
    }
    if old_percent > 0 and new_percent > 0 and abs(new_percent - old_percent) > 0.001:
        new_entry['lastDelta'] = round(new_percent - old_percent, 2)
    else:
        new_entry['lastDelta'] = old_delta

    _dossier_cache[str(int_cd)] = new_entry
    _save_dossier_cache()
```

**Обновление кэша после боя — только через `IItemsCache.onSyncCompleted`:**

```python
def _subscribe_items_cache():
    from skeletons.gui.shared import IItemsCache
    from helpers import dependency
    items_cache = dependency.instance(IItemsCache)
    items_cache.onSyncCompleted -= _on_items_cache_sync
    items_cache.onSyncCompleted += _on_items_cache_sync


def _on_items_cache_sync(*args, **kwargs):
    if _current_int_cd > 0:
        _cache_dossier(_current_int_cd, u'after-sync')
        moe_info.ensure_requested(_current_int_cd)
    try:
        from CurrentVehicle import g_currentVehicle
        if g_currentVehicle.isPresent() and g_currentVehicle.item is not None:
            int_cd = int(g_currentVehicle.item.intCD or 0)
            if int_cd > 0 and int_cd != _current_int_cd:
                _cache_dossier(int_cd, u'after-sync-hangar')
                moe_info.ensure_requested(int_cd)
    except Exception:
        pass
```

**Не читать досье сразу после `onAvatarBecomeNonPlayer`** — данные ещё не синкнуты, получите нули и испортите кэш.

### 6.4. Серверные пороги отметок

**9 точек, а не 4.** `[0%, 20%, 40%, 55%, 65%, 75%, 85%, 95%, 100%]`.

```python
# moe_info.py
import BigWorld
from . import _log

CACHE_TIME = 60.0 * 10
REQUEST_MIN_DELAY = 1.0
PENDING_TIMEOUT = 10.0      # ← обязательно!

_cache = {}                 # intCD -> {'time': float, 'data': {pct: value}}
_pending = {}               # intCD -> время запроса
_last_request_time = 0.0
_on_ready_callback = None


def ensure_requested(int_cd, force=False):
    global _last_request_time
    if int_cd <= 0:
        return
    now = BigWorld.time()
    entry = _cache.get(int_cd)
    if entry is not None and not force:
        if now - entry.get('time', 0) < CACHE_TIME:
            return
    # Сброс зависших запросов по таймауту — иначе они блокируют всё.
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
    from AccountCommands import CMD_GET_VEHICLE_DAMAGE_DISTRIBUTION
    player = BigWorld.player()
    if player is None:
        _pending.pop(int_cd, None)
        return
    try:
        player._doCmdInt(
            CMD_GET_VEHICLE_DAMAGE_DISTRIBUTION, int_cd,
            lambda requestID, responseID, errorStr, ext=None:
                _on_response(int_cd, errorStr, ext))
    except Exception as e:
        _log(u'[MOE] _doCmdInt failed: %r' % e)
        _pending.pop(int_cd, None)


def _on_response(int_cd, error_str, ext):
    _pending.pop(int_cd, None)
    if error_str or not ext:
        return
    raw = ext.get('damageBetterThanNPercent')
    if not raw:
        return
    percents = [0, 20, 40, 55, 65, 75, 85, 95, 100]
    result = {}
    for i, pct in enumerate(percents):
        if i < len(raw):
            try:
                v = int(raw[i])
                if v > 0:
                    result[pct] = v
            except Exception:
                pass
    _cache[int_cd] = {'time': BigWorld.time(), 'data': result}
    if _on_ready_callback is not None:
        try:
            _on_ready_callback(int_cd, result)
        except Exception:
            pass


def get_thresholds(int_cd):
    if int_cd <= 0:
        return None
    entry = _cache.get(int_cd)
    return entry.get('data') if entry else None


def set_ready_callback(cb):
    global _on_ready_callback
    _on_ready_callback = cb
```

### 6.5. Интерполяция по порогам (не линейный K)

Прямая линия `K = avg / rating` ошибается в середине боя. Правильно — кусочно-линейная интерполяция по 9 точкам.

```python
PERCENT_POINTS = (0, 20, 40, 55, 65, 75, 85, 95, 100)
EMA_K = 2.0 / 101.0


def interpolate_percent(value, thresholds):
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


def compute_display(cached_percent, cached_avg, cached_delta,
                    current_total, thresholds=None):
    """(percent, delta, forecast_avg)."""
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
```

### 6.6. Хук BattleResultsService.getResultsVO

Универсальный источник данных **после боя** (серебро, урон, фраги, точные значения досье).

```python
_hook_installed = False

def _install_battleresults_hook():
    global _hook_installed
    if _hook_installed:
        return
    from gui.battle_results.service import BattleResultsService
    orig = BattleResultsService.getResultsVO

    def _hooked(self, arenaUniqueID):
        result_vo = orig(self, arenaUniqueID)
        try:
            _on_battle_results(arenaUniqueID, result_vo)
        except Exception:
            _log(u'getResultsVO hook CRASHED:\n%s' % traceback.format_exc())
        return result_vo

    BattleResultsService.getResultsVO = _hooked
    _hook_installed = True


def _on_battle_results(arena_id, result_vo):
    if result_vo is None or 'personal' not in result_vo:
        return
    personal = result_vo['personal']
    # Пример: серебро из строки «Итого:»
    credits_data = personal.get('creditsData', [])
    for row in credits_data[0] if credits_data else []:
        lbl = (row.get('labelStripped') or u'').strip()
        if lbl == u'Итого:':
            silver = _extract_number(row.get('col3') or u'')
            # ... обработка
            break
```

**Антиповтор:** вести список `processed_arenas`, чтобы результат одного боя не засчитался дважды. **Список не очищать при reset сессии** — иначе клиент перезапросит результат последнего боя и засчитает его снова.

---

## 7. Окно в боевом интерфейсе

### 7.1. ViewModel

```python
class MarkBattleViewModel(ViewModel):
    def __init__(self):
        super(MarkBattleViewModel, self).__init__(properties=13, commands=4)

    def _initialize(self, *args, **kwargs):
        super(MarkBattleViewModel, self)._initialize(*args, **kwargs)
        self._addStringProperty('title', u'MARK BATTLE')      # 0
        self._addNumberProperty('posX', 0)                    # 1
        self._addNumberProperty('posY', 0)                    # 2
        self._addNumberProperty('hasPos', 0)                  # 3
        self._addBoolProperty('visible', True)                # 4
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
```

**Правила:**
- `_addNumberProperty` — **целочисленное**. Дробные (проценты, дельты) умножать на 100, в JS делить обратно.
- Команды (`_addCommand`) в сумме `properties` **не считаются** — они отдельный счётчик `commands`.
- Если нужно отдать несколько ViewModel-полей — заполнять через `_setNumber(idx, value)` по индексу в порядке объявления.

### 7.2. View и Window

```python
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
```

### 7.3. Создание окна

```python
def create_window(version, attempt=0):
    global WINDOW, LAST_CREATE_ERROR
    classes = _build_classes()
    if classes is None:
        return None
    from gui.impl.gen_utils import INVALID_RES_ID
    layout_id = classes['view'].viewLayoutID()
    if layout_id == INVALID_RES_ID:
        LAST_CREATE_ERROR = u'res_map key not registered'
        return None
    if WINDOW is not None:
        return WINDOW
    cfg = load_window_config()
    WINDOW = classes['window']()
    WINDOW.load()
    if cfg.get('x') is not None:
        PANEL_STATE['x'] = int(cfg['x'])
        PANEL_STATE['y'] = int(cfg['y'])
        _retry_position((int(cfg['x']), int(cfg['y'])), 0)
    return WINDOW
```

Ретраи до 6 попыток с интервалом 1.5 сек — на случай, если `res_map` ещё не готов.

**Страж загрузки GF-страницы.** Боевой мод создаёт окно после `onAvatarBecomePlayer` — если это произошло слишком близко к выходу из боя (например, игрок быстро вышел), GF-страница может не успеть загрузиться. Признак: `window created: uid=...` есть, `js ready` — нет. В **боевом** моде это не смертельно, но если мод гибридный (работает и в ангаре) — обязательно.

Причина: `BigWorld.callback(BOOT_TIMEOUT, _check_page_boot, uid)` **не переживает смену space**. Если окно создано в бою прямо перед переходом в ангар — callback убит, boot-страж не сработает, окно живое, страница не загружена.

Минимальный шаблон стража (для гибридных модов):

```python
READY_SEEN = False
BOOT_TIMEOUT = 5.0
BOOT_RETRIES = 2

# в _onReady модели: READY_SEEN = True
# в create_window:  READY_SEEN = False
#                   BigWorld.callback(BOOT_TIMEOUT, _check_page_boot, uid,
#                                     boot_retries)

def _check_page_boot(uid, retries_used):
    global BOOT_FAILURE_AT
    if WINDOW is None or getattr(WINDOW, 'uniqueID', None) != uid:
        return
    if READY_SEEN:
        return
    _log(u'page boot TIMEOUT #%d: js ready не пришёл за %.1fs uid=%s'
         % (retries_used + 1, BOOT_TIMEOUT, uid))
    if retries_used >= BOOT_RETRIES:
        BOOT_FAILURE_AT = BigWorld.time()
        destroy_window()
        return
    destroy_window()
    create_window(LAST_VERSION, RESET_HANDLER, attempt=1,
                  boot_retries=retries_used + 1)
```
И проверка при входе в ангар (для гибридных модов, где ангарная часть вызывает _on_hangar_entered):

```python
if not view_mod.is_window_alive():
    _try_create_window(0)
elif not view_mod.is_page_ready():
    # окно живо, но страница не загружена (boot-страж убит сменой space)
    view_mod.destroy_window()
    _try_create_window(0)				  
```
---

## 8. Команды и надёжность моста Python↔JS

### 8.1. Проблема

Команды, зарегистрированные через `_addCommand('xxx')`, **иногда не доходят до Python**. Проверено в SilverBattle: команда `resetSession` не срабатывала, `sbResetSession` — тоже. В логе Python — тишина, в JS — ни ошибки, ни предупреждения. При этом `ready` (первая команда, вызываемая при boot) — **всегда работает**.

### 8.2. Решение: критичные команды через `ready`

Идея: `ready` уже вызывается при boot. Используем его как канал для передачи экстренных команд с флагом.

**Python — в `_onReady`:**

```python
def _onReady(self, args):
    # Проверка на «аварийный» вызов
    try:
        if args and args.get('resetNow'):
            if RESET_HANDLER is not None:
                RESET_HANDLER()
            return
    except Exception:
        _log(u'ERROR: reset via ready crashed:\n%s' % traceback.format_exc())
        return

    # Обычный boot
    client_w = _to_number(args.get('clientW'))
    # ...
```

**JS — при сбросе:**

```javascript
window.model.ready({
    resetNow: 1,
    clientW: 0, clientH: 0,
    viewW: 0, viewH: 0,
    mode: 'reset'
});
```

**Это работает.** В SilverBattle кнопка reset перестала терять команду именно после такого обходного пути.

### 8.3. Про `typeof` и проверки

Не делайте так:

```javascript
if (typeof window.model.sbResetSession !== 'function') { return; }
```

В Coherent Gameface команды модели — **не обычные JS-функции**. `typeof` может вернуть не `'function'`, хотя вызов работает. Проверку убрать.

### 8.4. Порядок применения

Если команда работает напрямую — используйте её. Если нет — переносите на `ready`.

Команды, которые **точно работают** (проверено):
- `ready`
- `dragStart`
- `dragEnd`
- `dragMove` (в режиме, когда Python только читает `mcursor`, JS-координаты можно игнорировать)

Команды, которые **могут не сработать**:
- Пользовательские с короткими именами.
- Команды, добавленные в модель **после** того, как окно уже загружено (в некоторых билдах клиента).

---

## 9. Драг в бою

Драг через `GUI.mcursor()`, не через DOM. Полный цикл — в разделе 9.1.

### 9.1. Python — цикл опроса

```python
import GUI
import Keys

DRAG = {'active': False, 'card0': None, 'cursor0': None, 'ticking': False}


def _is_lmb_down():
    for name in ('KEY_LEFTMOUSE', 'KEY_MOUSE0'):
        code = getattr(Keys, name, None)
        if code is not None:
            try:
                return bool(BigWorld.isKeyDown(int(code)))
            except Exception:
                continue
    return True


def _tick_drag(*_args):
    if not DRAG['active'] or WINDOW is None or not IS_VISIBLE:
        DRAG['ticking'] = False
        return
    if not _is_lmb_down():
        _apply_drag_step()
        DRAG['active'] = False
        DRAG['ticking'] = False
        push_panel_position()
        persist_position()
        return
    _apply_drag_step()
    if DRAG['active']:
        BigWorld.callback(0.0, _tick_drag)
    else:
        DRAG['ticking'] = False


def _norm_to_px(nx, ny):
    w, h = _screen_size()
    px = (float(nx) + 1.0) * 0.5 * w
    py = (1.0 - float(ny)) * 0.5 * h
    return (px, py)


def _screen_size():
    try:
        s = BigWorld.screenSize()
        if s and int(s[0]) > 0 and int(s[1]) > 0:
            return (int(s[0]), int(s[1]))
    except Exception:
        pass
    return (1920, 1080)


def _apply_drag_step(*_args):
    if WINDOW is None:
        return
    wx = PANEL_STATE['x']
    wy = PANEL_STATE['y']
    if wx is None or wy is None:
        return
    try:
        nx, ny = GUI.mcursor().position
        cx, cy = _norm_to_px(nx, ny)
    except Exception:
        return
    tx = DRAG['card0'][0] + (float(cx) - DRAG['cursor0'][0])
    ty = DRAG['card0'][1] + (float(cy) - DRAG['cursor0'][1])
    nx_, ny_ = _clamp(tx, ty)
    if nx_ == wx and ny_ == wy:
        return
    if WINDOW.move(int(nx_), int(ny_)):
        PANEL_STATE['x'] = nx_
        PANEL_STATE['y'] = ny_
```

### 9.2. Дублирование drag end

**Проблема:** `_tick_drag` завершает драг при отпускании ЛКМ, а потом из JS приходит `dragEnd`, и обработчик вызывается ещё раз. В логе — две строки `position saved`, два `drag end`.

**Решение:** защита `if not DRAG['active']: return` в `_onDragEnd`.

```python
def _onDragEnd(self, args):
    if not DRAG['active']:      # уже завершён в _tick_drag
        return
    _apply_drag_step()
    DRAG['active'] = False
    DRAG['ticking'] = False
    push_panel_position()
    persist_position()
```

### 9.3. JS

```javascript
function startDrag(e) {
    if (e.button !== undefined && e.button !== 0) { return; }
    if (isEventFromButton(e)) { return; }   // клик по кнопке — не драг
    card.classList.add('is-dragging');
    sendCmd('dragStart', { lx: e.clientX, ly: e.clientY });
    if (e.preventDefault) { e.preventDefault(); }
}

function endDrag(e) {
    if (isEventFromButton(e)) { return; }
    card.classList.remove('is-dragging');
    sendCmd('dragEnd', { lx: e.clientX, ly: e.clientY });
}

function isEventFromButton(e) {
    var t = e.target;
    while (t && t !== card) {
        if (t.tagName && t.tagName.toLowerCase() === 'button') { return true; }
        t = t.parentNode || null;
    }
    return false;
}

card.addEventListener('mousedown', startDrag);
document.addEventListener('mouseup', endDrag);
```

---

## 10. UI для боя

### 10.1. Принципы

1. **Прозрачный фон.** В бою видна карта — панель едва заметна.
2. **Тени для читаемости.** `text-shadow` и `drop-shadow` обязательны.
3. **Компактность.** Ничего лишнего.
4. **Контраст.** Белый текст, цветные акценты.

### 10.2. SVG — только внешние файлы

**Coherent не парсит inline `<svg><path/></svg>`.** Только `.svg` через `background-image`.

### 10.3. Вертикальный градиент прозрачности

Как у Near You: силуэт растворяется книзу. Делается **внутри SVG** через `<linearGradient>`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="-130 100 745 355">
  <defs>
    <linearGradient id="fadeFill" gradientUnits="userSpaceOnUse"
                    x1="0" y1="114" x2="0" y2="440">
      <stop offset="0" stop-color="#6ebe54" stop-opacity="0.9"/>
      <stop offset="1" stop-color="#6ebe54" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="fadeStroke" gradientUnits="userSpaceOnUse"
                    x1="0" y1="114" x2="0" y2="440">
      <stop offset="0" stop-color="#f0ecdf" stop-opacity="1"/>
      <stop offset="1" stop-color="#f0ecdf" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <path fill="url(#fadeFill)" fill-rule="evenodd"
        stroke="url(#fadeStroke)" stroke-width="2.5" stroke-linejoin="round"
        d="..."/>
</svg>
```

**Y-координаты** — верхняя и нижняя точка пути. `y1` = верх (плотно), `y2` = низ (прозрачно). Сдвиг `y2` вверх делает растворение более резким.

### 10.4. Заливка силуэта по проценту

Два слоя — пустой и залитый, обрезка по ширине:

```css
.silhouette-wrap {
    position: relative;
    width: 100%;
    height: 95rem;      /* явно, auto не работает */
}

.silhouette-empty {
    position: absolute; width: 100%; height: 100%;
    background: url("./tank_empty.svg") no-repeat left top;
    background-size: 100% 100%;
}

.silhouette-fill {
    position: absolute; top: 0; left: 0;
    height: 100%; width: 0%;
    overflow: hidden;
    background: url("./tank_filled_green.svg") no-repeat left top;
    background-size: 200rem 95rem;    /* абсолют, не 100%! */
    transition: width 0.25s linear;
}
```

**Правило:** `background-size` — абсолютный размер **родителя**. Если написать `100% auto`, при `width: 50%` фон сожмётся в 2 раза.

### 10.5. Звёзды

Два SVG: `star_empty.svg`, `star_filled.svg`. Толщина обводки — одинаковая, иначе визуально разные размеры.

```css
.star {
    width: 14rem; height: 14rem;
    background: url("./star_empty.svg") no-repeat center/contain;
}
.star--earned { background-image: url("./star_filled.svg"); }
```

### 10.6. Что не работает в Coherent

- **Inline SVG** — рисует пустоту.
- **`height: auto`** для SVG или родителя — схлопывается в 0.
- **Data-URI SVG** в CSS — не отображается.
- **`filter: drop-shadow`** на SVG — не применяется.
- **`setPointerCapture`** на `document.body` — не срабатывает.
- **`typeof window.model.command === 'function'`** — команды модели не функции.

---

## 11. Логирование: что оставлять, что убирать

### 11.1. Оставлять (важные события)

**`app.py`:**
- `dossier cached (hangar/after-sync): intCD=... rating=... delta=...` — редко, полезно.
- `[MOE] thresholds for intCD=...` — редко, полезно.
- `battle session stopped: final dmg=... assist=...` — 1 раз за бой.
- `battle counted: ...` — 1 раз за бой.
- `BattleResultsService.getResultsVO hooked` — 1 раз при старте.
- `giving up window creation after N attempts` — важно при ошибке.
- Все `%r' % e` в `except Exception`.

**`view.py`:**
- `openwg_gameface imported (IS_LESTA=...)` — 1 раз.
- `layoutID resolved: ...` — 1 раз, важно.
- `Keys module loaded: ...` — 1 раз.
- `window created: uid=...` — 1 раз.
- Все `%r` в `except`.

### 11.2. Убирать (шум)

**`app.py`:**
- `module init requested`
- `res_map configs ensured (written=...)`
- `vX: started`
- `subscribed: ...` (4 подписки)
- `avatar become player: battle started`
- `avatar become non-player: battle ended`
- `intCD resolved in battle: ...`
- `itemsCache sync: refreshing dossier`
- `battle session started`
- `efficiency updated: dmg=... assist=...` — **это спам на каждый выстрел**, убирать в первую очередь.

**`view.py`:**
- `js ready: client=...` (если нужно — оставить)
- `drag start: ...`
- `drag end: ...`
- `position saved: ...`
- `MODEL: pct=... delta=... avg=...` — спам, убирать в первую очередь.
- `reset command from JS`

### 11.3. Итог

После чистки **один бой = ~5 строк** лога вместо ~300. Лог становится читаемым.

---

## 12. Сборка и установка

### 12.1. `build.py`

```python
INCLUDE_EXT = frozenset(['.pyc', '.html', '.css', '.js', '.json',
                         '.png', '.svg', '.xml', '.swf'])
```

**Обязательно `.svg`** — иначе силуэт и звёзды не попадут в `.mtmod`.

### 12.2. `meta.xml`

```xml
<root>
    <id>zai.markbattle</id>
    <version>{{VERSION}}</version>
    <name>zai.markbattle</name>
    <description>In-battle gun marks tracker (Gameface)</description>
</root>
```

### 12.3. `res_map.json`

```json
[
  {
    "itemID": "user.markbattle.panel",
    "type": "Layout",
    "path": "coui://gui/gameface/mods/mark_battle/index.html",
    "parameters": {
      "extension": "",
      "entrance": "MarkBattlePanel",
      "impl": "gameface"
    }
  }
]
```

### 12.4. Сборка

```
build.bat 0.9.0
py -2.7 build.py -v 0.9.0
```

Результат — `<MOD_ID>_<VERSION>.mtmod` или `<MOD_ID>.mtmod`.

### 12.5. Установка

1. Скопировать `.mtmod` в `<game>/mods/<версия>/`.
2. **Удалить старые `.mtmod` этого мода** — конфликт версий.
3. **Первый запуск после установки**: `openwg_gameface` должен смержить `res_map`. Если ключ не зарегистрировался — перезапустить игру ещё раз (второй запуск подхватит готовый `res_map.json`).

### 12.6. Точки контроля при отладке

- `dossier cache loaded: N entries` — кэш подхвачен.
- `[MOE] thresholds for intCD=...` — пороги получены.
- `layoutID resolved: <число>` — ключ зарегистрирован.
- `window created: uid=...` — окно создано.
- `js ready: client=... card=...` — JS загрузился.

Если `INVALID_RES_ID` — `res_map` не смержен. Перезапускать игру.

---

## 13. Типичные ошибки

| Симптом | Причина | Решение |
|---|---|---|
| Окно появляется в ангаре | Не уничтожили в `onAvatarBecomeNonPlayer` | Убрать `create_window` из ангарных событий |
| Окно не появляется в бою | `res_map` не смержен | Перезапустить игру, проверить `layoutID resolved` |
| `INVALID_RES_ID` | Ключ не зарегистрирован | Проверить `INCLUDE_EXT` (`.svg`), перезапустить |
| `ImportError: No module named X` | Пакет не найден | Проверить `__init__.pyc` — не переименован ли в `_init__.pyc` |
| Команда из JS не доходит | Команды модели ненадёжны | Пустить через `ready` с флагом (см. раздел 8) |
| `typeof window.model.command !== 'function'` | Команды модели не JS-функции | Убрать проверку |
| intCD = 0 в бою | Читаем до `playerVehicleID` | Опрос в `_int_cd_poll` с задержкой 0.5 сек |
| Досье пустое в бою | `IItemsCache` не синкнут | Читать только в ангаре, кэшировать |
| Урон 0 при ненулевом в игре | Нет подписки на `personalEfficiencyCtrl` | Подписаться в `onBattleSessionStart` |
| Урон падает до 0 в конце боя | Клиент сбрасывает | Защита `if d > _last_damage` |
| Досье перезаписалось нулями | Читаем сразу после боя | Обновлять только на `onSyncCompleted` |
| `[MOE] thresholds` нет никогда | `_pending` завис | Добавить `PENDING_TIMEOUT` |
| Сброс сессии в боевом моде не работает | Команда reset не доходит | Через `ready({resetNow: 1})` |
| Силуэт не виден | Inline SVG не рендерится | Внешние `.svg` через `background-image` |
| Силуэт сжат | `background-size: 100%` на `width: 50%` | Абсолютный размер родителя |
| Текст не читается на светлом фоне | Нет тени | `text-shadow` обязательно |
| Драг «спотыкается» | DOM-события за границей окна | `GUI.mcursor()` + `BigWorld.isKeyDown` |
| Двойное `position saved` | `_tick_drag` + `_onDragEnd` дублируют | Защита `if not DRAG['active']: return` |
| Позиция неправильная | `viewEnv.getClientSizePx()` в бою врёт | `BigWorld.screenSize()` |
| Цифры не совпадают с Lebwa в бою | Разные формулы прогноза | В ангаре совпадаем, в бою — прогноз; расхождение ±0.1% нормально |
| `_mtmod` не грузится | Неверное имя файла или старый `.mtmod` не удалён | Переименовать/удалить; рестарт игры |
| Панель пропала после выхода из боя (гибридный мод) | Блокеры watchdog'а залипли: battle-space рвётся целиком, _removeView не вызывается | Чистить _sf_blockers и _wulf_blockers в onAvatarBecomeNonPlayer и на входе в ангар |
| Окно создано в бою, js ready не пришёл | Boot-страж BigWorld.callback убит сменой space | _on_hangar_entered: окно живое + READY_SEEN==False → destroy_window() + _try_create_window(0) |
| load_position_for/is_window_alive падает с NameError/AttributeError | Вспомогательная функция не определена в модуле | Проверить, что все вызываемые из app.py функции импортированы и определены в view.py/__init__.py |

---

## 14. Приложение: полезные API

### Python

**Жизненный цикл:**
- `g_playerEvents.onAvatarBecomePlayer` / `onAvatarBecomeNonPlayer`
- `IBattleSessionProvider.onBattleSessionStart` / `onBattleSessionStop`
- `IItemsCache.onSyncCompleted`
- `CurrentVehicle.g_currentVehicle.onChanged`

**Данные боя:**
- `BigWorld.player()`, `BigWorld.entity(veh_id)`
- `player.playerVehicleID`
- `entity.typeDescriptor.type.compactDescr` — intCD
- `IBattleSessionProvider.shared.personalEfficiencyCtrl`
- `PERSONAL_EFFICIENCY_TYPE.DAMAGE / ASSIST_DAMAGE / BLOCKED_DAMAGE / STUN`

**После боя:**
- `BattleResultsService.getResultsVO(self, arenaUniqueID)` — хук на результат
- `result_vo['personal']` → `creditsData`, `damageDealt`, `kills`, ...
- Серебро — строка `labelStripped == u'Итого:'`, `col3`

**Серверные данные:**
- `CMD_GET_VEHICLE_DAMAGE_DISTRIBUTION` — 9 порогов отметок
- `player._doCmdInt(cmd, intCD, callback)` — отправка

**Курсор/экран:**
- `GUI.mcursor().position` — нормализованный `[-1, 1]`
- `BigWorld.screenSize()` — физический размер
- `BigWorld.isKeyDown(code)`
- `Keys.KEY_LEFTMOUSE` = 256

**Окно:**
- `WINDOW.move(x, y)`, `WINDOW.destroy()`
- `WindowLayer.WINDOW` (7)

### JS

**Engine:**
- `window.engine.whenReady`
- `window.engine.on(event, fn)`
- `window.viewEnv.resizeViewRem(w, h)`
- `window.model.<prop>` — чтение свойства
- `window.model.<command>(args)` — вызов команды

**События:**
- `viewEnv.onDataChanged`
- `subViews.onAdded`
- `clientResized`

**Формат:**
- Целые с тонким пробелом: `1 234`
- Дельта со знаком: `+2,88%`
- Проценты с запятой: `72,67%`

---

## Итог

Боевой мод — это:

1. **Python** — ждёт `onAvatarBecomePlayer`, создаёт окно, читает боевые данные (урон, intCD, кэш досье), публикует в ViewModel. Уничтожает окно при выходе.
2. **JS** — читает ViewModel, обновляет DOM по ключу.
3. **UI** — прозрачный, компактный, тени. Силуэт через внешние SVG.
4. **Драг** — `GUI.mcursor()` + `BigWorld.isKeyDown`.
5. **Критичные команды** — через `ready` с флагом, если прямые команды не срабатывают.

Ключевые грабли (по опыту двух боевых модов):
- **intCD в бою запаздывает** → опрос.
- **Досье в бою не читается** → кэш.
- **Урон обнуляется в конце боя** → защита `>`.
- **Команды модели ненадёжны** → канал через `ready`.
- **Inline SVG не рендерится** → внешние файлы.
- **`height: auto` не работает** → явные размеры.
- **`viewEnv.getClientSizePx()` врёт** → `BigWorld.screenSize()`.
- **Окно перехватывает клики** → уничтожать при выходе.
- **`_pending` в `moe_info` без таймаута** → запросы зависают.
- **Порогов отметок 9** → интерполяция, а не K.
- **Блокеры залипают после боя** → чистить _sf_blockers/_wulf_blockers в onAvatarBecomeNonPlayer (гибридные моды).
- **Boot-страж BigWorld.callback убит сменой space** → в _on_hangar_entered проверять READY_SEEN и пересоздавать окно, если окно живо, но js ready не приходил.
