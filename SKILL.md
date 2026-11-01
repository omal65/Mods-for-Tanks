---
name: lesta-mt-gameface-dev
description: Разработка, отладка, портирование и сборка модов (.mtmod) для игры «Мир танков» (Lesta Games, ветка mt-ru) на стеке Python 2.7.18, Wulf и Coherent Gameface (net.openwg.gameface 1.2.2). Используй этот навык, когда пользователь просит создать или доработать боевой, ангарный или гибридный мод для «Мира танков» (Леста), настроить ViewModel/WindowImpl/ViewImpl, ModDynAccessor, ModInjectModel/gf_mod_inject, реализовать перетаскивание (drag), структурный watchdog видимости, мост Python-JS, верстку для Coherent Gameface или скрипт сборки build.py.
---
# Моддинг «Мир танков» (Lesta) на Python 2.7 + Wulf / Coherent Gameface

Руководство и набор проверенных паттернов для создания ангарных, боевых и гибридных модов под клиент «Мир танков» (Lesta Games, НЕ путать с World of Tanks от Wargaming).

## Базовый стек и ресурсы

  - **Целевой клиент:** «Мир танков» (Lesta Games), ветка `mt-ru`.
  - **Исходники клиента (распакованные ресурсы):** `https://github.com/wotstat/wot-src/tree/mt-ru/sources/` (и аналитика `https://github.com/wotstat`).
  - **Зависимость в клиенте:** пакет `net.openwg.gameface_1.2.2.mtmod` (`https://gitlab.com/openwg/wot.gameface/-/releases`) в `<game>/mods/<version>/`.
  - **Язык и компиляция:** строго **Python 2.7.18** (байткод `.pyc` совместим только с 2.7). Никаких f-строк, `async/await`, `yield from` или type hints.

## Протокол «Анти-галлюцинация и Нативный Wulf/Gameface 1.2.2» (Zero Hallucination)

1.  **Строгий запрет на угадывание API клиента:** если для задачи нужен конкретный контроллер, хук, `ViewModel`, константа или сервис из клиента Лесты (`sources/res/scripts/client/...`), которого нет в справочных файлах навыка и точная сигнатура которого не подтверждена, **категорически запрещено выдумывать имена методов, полей или аргументов**. Вместо догадок укажи пользователю точный путь в репозитории `wotstat/wot-src` (ветка `mt-ru`, например `sources/res/scripts/client/gui/...`) и попроси прислать нужный файл или фрагмент.
2.  **Не путать Lesta и WG в `openwg_gameface 1.2.2`:**
      - В **Lesta (`mt-ru`)** регистрация ресурсов идёт **ТОЛЬКО** через `mods/configs/res_map/*.json` (слияние в `res_mods/<version>/gui/unbound/gen/res_map.json` с однократным рестартом клиента) и функции `ModDynAccessor(modID)`, `on_ready(callback)`, `res_id_by_key(key)`, `res_ids_by_mask(mask)`.
      - Механизм `gui/gen_resources/*.json` и `R.mods.*` относится **только к клиенту WG (2.4.1+)** — никогда не предлагай его для «Мир танков» от Лесты!
3.  **Только современный стек Wulf + Gameface (`openwg_gameface 1.2.2`):** не используй устаревшие костыли Scaleform/Flash (`.swf`, `as_...S`), если задача решается нативными компонентами Wulf (`ViewImpl`, `WindowImpl`, `ViewModel`, `ViewSettings`), `ModDynAccessor` (для своего окна) или `gf_mod_inject` / `ModInjectModel` + `libs/model.js` (`ModelObserver`), `libs/views.js` (`showTooltip`, `showPopover`), `libs/sound.js` (`playSound`), `libs/common.js`, `libs/media.js` (`MediaContext`).

## Главные архитектурные правила (Checklist)

### 1. Структура проекта и сборка (`.mtmod`)

  - **Модульная архитектура:** разделяй независимые боевые задачи (например, перетаскиваемую панель перезарядки `reload_timer` и центрированный кастомный прицел `green_sight`) на отдельные независимые пакеты `.mtmod`, чтобы не смешивать окна с разным позиционированием и избегать конфликтов.
  - **Полный комплект сборки:** при создании нового мода всегда предоставляй полный набор файлов: `meta.xml`, `build.py`, `build.bat`, точку входа `mod_<name>.py`, пакет `<name>/__init__.py`, `app.py`, `view.py` и ассеты `res/gui/gameface/mods/<name>/`.
  - Правки вносятся в исходники. При сборке `res/gui/gameface` синхронизируется в `mods/gui/gameface`, а `mods/configs/res_map/<mod_id>.json` упаковывается внутрь `.mtmod` и дублируется при `init()` на диск через `ensure_res_map_configs()`.
  - Внутри Python-пакета обязательно наличие файла строго с именем `__init__.py` (не `_init__.py`).
  - Расширение `.svg` (наряду с `.pyc`, `.html`, `.css`, `.js`, `.json`, `.png`, `.xml`, `.swf`) обязательно входит в белый список `INCLUDE_EXT` в `build.py`, а исходники `.py` исключаются (`EXCLUDE_EXT`).
  - Архив `.mtmod` пакуется методом `zipfile.ZIP_STORED` (без сжатия).
  - Для регистрации UI в `mods/configs/res_map/<mod_id>.json` указывается `itemID` (например, `user.<mod>.panel`), путь `coui://gui/gameface/mods/<mod>/index.html` и `"impl": "gameface"`. При первом создании `res_map/<mod_id>.json` на диске требуется однократный перезапуск клиента игры, чтобы `openwg_gameface` собрал общий `res_map.json` при старте.

### 2. Wulf ViewModel, Инжекция и мост Python <-> JS

  - **Только целочисленные свойства в NumberProperty:** `_addNumberProperty` и `_setNumber` в Wulf принимают только `int`. Передача `float` вызывает `TypeError` при бинде и ломает создание окна. Дробные значения (проценты, дельты, время, прогресс зарядки) умножай на 100 на стороне Python (`int(round(val * 100.0))`) и дели на 100 в JS.
  - **Счётчики в конструкторе ViewModel:** `super(MyViewModel, self).__init__(properties=N, commands=M)` — количество `properties` и `commands` считается раздельно, индексы в `_setNumber(idx, val)` строго соответствуют порядку объявления свойств. При использовании `gf_mod_inject(self, 'Alias', ...)` резервируй `+1` в `properties` родительской модели под дочернюю `ModInjectModel`.
  - **Надёжное обновление UI в JS:** при изменении свойств модели через `_setNumber`/`_setBool` по индексам из Python движок Wulf в бою не всегда стреляет JS-событием `viewEnv.onDataChanged`. Обязательно дублируй подписку `window.engine.on('viewEnv.onDataChanged', applyModel)` регулярным опросом `setInterval(applyModel, 25..250)` и `setInterval(applyVisible, 100)`.
  - **Явный `resizeViewRem(cw, ch)` в `sendReady()`:** в JS при инициализации компактного перетаскиваемого окна обязательно вызывай `window.viewEnv.resizeViewRem(cw, ch)` с точными размерами карточки (например, `220, 160`). Без `resizeViewRem` нативный контейнер Wulf-окна сохраняет дефолтную высоту во весь экран, из-за чего `WINDOW.move(x, y)` блокирует вертикальное перемещение окна по оси Y.
  - **Защита `_clamp(x, y)` в `view.py`:** всегда проверяй размеры `PANEL_STATE['view']` (`vw = int(view[0]) if (view and 0 < int(view[0]) <= 400) else 220`), чтобы случайная передача полноэкранных размеров не обнулила `max_y = h - vh` и не заблокировала перетаскивание по вертикали.
  - **Измерение карточки при старте (`measureCard`):** никогда не вешай `display: none` (`class="is-hidden"`) на `<body>` в исходном `index.html` до завершения `boot()`, иначе `getBoundingClientRect()` вернёт `0x0` и `resizeViewRem` не сработает. Скрывай `body.is-hidden` только из JS в `applyVisible()` после первого успешного измерения размеров карточки.
  - **Обход потерь команд через `ready`:** в Coherent Gameface кастомные команды `_addCommand` иногда не доходят из JS в Python. Команды `ready`, `dragStart`, `dragMove`, `dragEnd` работают стабильно. Критичные действия (например, сброс сессии) передавай через вызов `window.model.ready({ resetNow: 1, ... })` с обработкой флага в начале `_onReady`.
  - **Никаких проверок `typeof window.model.cmd === 'function'` в JS:** команды модели в Coherent не являются стандартными JS-функциями, такая проверка вернёт `false` и заблокирует вызов.

### 3. Жизненный цикл и данные (Бой vs Ангар)

  - **Боевое окно:** создавай сразу при входе в бой после `g_playerEvents.onAvatarBecomePlayer` (при необходимости в скрытом состоянии `visible=False`) и уничтожай при `onAvatarBecomeNonPlayer` (или при гибели танка `not player.isVehicleAlive`).
  - **`intCD` в бою:** `g_currentVehicle` в бою пуст, а `playerVehicleID` и `typeDescriptor` появляются с задержкой. Используй опрос (`BigWorld.callback(0.5, _int_cd_poll)`) через `BigWorld.entity(player.playerVehicleID).typeDescriptor.type.compactDescr`.
  - **Досье танка:** `IItemsCache.items.getVehicleDossier(int_cd)` в бою возвращает пустой объект. Читай досье в ангаре (при смене танка и по `IItemsCache.onSyncCompleted`), кэшируй в JSON, а в бою читай из кэша. Никогда не читай досье сразу в `onAvatarBecomeNonPlayer`.
  - **Урон и фраги в бою:** в `personalEfficiencyCtrl` приходят абсолютные значения (`PERSONAL_EFFICIENCY_TYPE.DAMAGE`, `DESTRUCTION`), а в конце боя клиент присылает `0`. Обязательна защита `if d > _last_damage:`. Дополнительно сверяй фраги через `sessionProvider.getArenaDP().getVehicleStats().frags`.
  - **Послебоевая статистика и недоигранные бои:**
      - Для получения полного результата боя в ангаре используй штатный `player.battleResultsCache.get(arenaUniqueID, callback)` + `IBattleResultsService.postResult(fullForm, needToShowUI=False)`.
      - При первом вызове `svc.getResultsVO(arena)` после фонового `postResult(..., needToShowUI=False)` клиент может выбросить `TypeError` в телеметрии `logClientPB20UXStats` уже после сохранения VO в кэш композитора. Оборачивай вызов в хелпер `_get_vo_safe(svc, arena)` с повторным вызовом в `except` — второй вызов мгновенно отдаёт готовый VO из кэша без ошибок.
      - Для получения квитанции боя N прямо во время боя N+1 (при досрочном выходе) используй `ServiceChannel` (`BattleResultsFormatter`: `credits + teamSubsBonusCredits - creditsToDraw`). При подписке на `g_messengerEvents.serviceChannel.onServerMessageReceived` обработчик обязан принимать `(*args, **kwargs)`, так как событие передаёт 3 аргумента `(clientID, formatted, settings)`.
      - Для проверки, доигран ли бой до конца при выходе, проверяй `period == 3` ИЛИ факт того, что квитанция `ServiceChannel` для текущей арены уже пришла до `onAvatarBecomeNonPlayer` (так как в момент `onAvatarBecomeNonPlayer` объект `player.arena` может быть уже разрушен и `period` вернёт `0`).

### 4. Механика перезарядки, прицела и сведения (Battle HUD / ReloadTimer / GreenSight)

  - **Источники состояния перезарядки (`sessionProvider.shared.ammo`):**
      - Проверяй `gun_settings.hasAutoReload()` (метод или свойство): для механизмов дозарядки читай `ammo.getAutoReloadingState()`, для обычных и барабанных орудий — `ammo.getGunReloadingState()`.
      - Если в клиенте Лесты для циклического орудия `state.getTimeLeft()` возвращает `0` при `isReloading() == True`, вычисляй остаток времени самостоятельно от момента старта КД: `base_time - (BigWorld.time() - start_at)`, используя `state.getBaseValue()` или `ammo.getShellChangeTime()`.
      - Количество снарядов в барабане/кассете читай через `ammo.getCurrentShells()` -> `(bay_total, in_clip)`, а размер барабана и КД внутри барабана — из `player.vehicleTypeDescriptor.gun.clip` -> `(clip_size, intra_clip_time)`. Не используй `getShellsQuantityLeft()` для отображения кассеты (он возвращает весь боекомплект танка).
  - **Двуствольные орудия (Dual Gun):**
      - Перехватывай `PlayerAvatar.updateDualGunState(self, vehicleID, activeGun, gunStates, cooldownTimes, shotCount)`.
      - В `gunStates` состояния стволов (`DUAL_GUN.GUN_STATE`): `0 = EMPTY`, `1 = RELOADING`, `2 = READY`. Передавай заряженность стволов битмаской (`mask |= 1` для левого, `mask |= 2` для правого) и индекс активного ствола `dualActive` (`0` или `1`).
      - В `cooldownTimes` массив `Cooldowns(id, leftTime, baseTime)` содержит 4 таймера: `0 = LEFT_GUN`, `1 = RIGHT_GUN`, `2 = SWITCH` (переключение стволов), `3 = DEBUFF` (штраф после дуплета).
      - **Подготовка залпа (дуплета):** отслеживай флаг `bool(getattr(player, 'inCharge', False))`. Как только `inCharge` переходит в `True`, засекай время старта `BigWorld.time()`, а длительность подготовки залпа бери из `player.vehicleTypeDescriptor.gun.dualGun.chargeTime` (дефолт `1.5` сек). Для плавной анимации сведения снарядов и роста дуг дуплета используй частоту тика `TICK_DELAY = 0.03` сек (~33 FPS).
      - **Визуализация двустволки в UI:**
          1. В обычном режиме (`!dualCharging`) два снаряда разнесены шире обычного барабана (`22rem`), а вокруг активного ствола (`j === dualActive`) отображается полупрозрачный светящийся ореол `( )` (`dual_reticle.svg`).
          2. При зажатии залпа (`dualCharging == True`) ореол одиночного ствола немедленно скрывается (снятием класса `is-dual-active` в JS), снаряды быстро смыкаются к центру (`marginRight = '2.0rem'` у левого, `'0rem'` у правого), а снизу из-под осей обоих снарядов снизу вверх растёт чаша из двух полудуг (`dual_salvo_arc.svg`) путём изменения `height` контейнера-маски (`overflow: hidden; background-position: center bottom; background-size: 60rem 50rem`) от `0rem` до `50rem` пропорционально прогрессу зарядки `0.0 .. 1.0`.
  - **Архитектура кастомного прицела (Гибрид Wulf/Gameface для прицельных дуг + Нативный C++ для круга сведения):**
      - **Почему круг сведения должен оставаться нативным C++ (`GUI.CrosshairFlash` + `GUI.GunMarkerDataProvider`):** в движке игры `_DefaultGunMarkerController.update` вызывается физикой/сервером дискретно (~10 Гц, `relaxTime = 0.1` с), а плавное 144+ FPS интерполирование матрицы и масштаба круга сведения с учётом FOV камеры (`BigWorld.projection().fov`) выполняется внутри C++ связки `GUI.GunMarkerDataProvider` -> `GUI.CrosshairFlash` (`gm_components.py`). Кроме того, при масштабировании SVG-круга в Gameface изменяется толщина обводки. Поэтому попытка перерисовать плавающий круг сведения в Python+Gameface приводит к рывкам и потере толщины линии при сужении.
      - **Правильный паттерн кастомного прицела (`green_sight`):**
          1. **Нативный C++ круг сведения и светофор бронепробития** оставляем работать штатно через хук на `plugins._makeSettingsVO(settingsCore)` (`gui/Scaleform/daapi/view/battle/shared/crosshair/plugins.py`): для `view_id in (1, 2)` (`ARCADE=1`, `SNIPER=2`) оставляем `mixingAlpha = 1.0`, `gunTagAlpha = 1.0`, `centerAlphaValue = 1.0` (**не перезаписывая** пользовательские `mixingType` и `gunTagType`!), а все стандартные дуги, сетку, цифры таймера, кассету и индикатор зума гасим в ноль (`netAlphaValue = 0.0`, `reloaderAlphaValue = 0.0`, `conditionAlphaValue = 0.0`, `reloaderTimerAlphaValue = 0.0`, `cassetteAlphaValue = 0.0`, `zoomIndicatorAlphaValue = 0.0`).
          2. **Кастомное перекрестие и боковые дуги (перезарядка слева, ХП танка справа)** рисуем в отдельном компактном Wulf/Gameface окне (например, `340x110rem`), которое центрируется по экранным координатам камеры `offset = sessionProvider.shared.crosshair.getOffset()` -> `center_x = int(round(0.5 * sw * (1.0 + offset[0])))`, `center_y = int(round(0.5 * sh * (1.0 - offset[1])))` через `WINDOW.move(center_x - W // 2, center_y - H // 2)` и скрывается в арт-режиме/посмертии (`view_id not in (1, 2)`).
          3. **Строгая концентрическая геометрия дуг и сегментов:** чтобы внутренние пунктирные сегменты (`.seg`) были идеально параллельны внешней SVG-дуге (`<path d="M... A R_out,R_out ..."/>`), и внешняя дуга в SVG, и центры всех сегментов в CSS обязаны рассчитываться тригонометрически от **одного и того же центра `(cx, cy)`** (`x = cx ± R_in * cos(a)`, `y = cy + R_in * sin(a)`, `transform: rotate(±a deg)`).

### 5. Видимость ангарного окна и Hit-Test (Структурный Watchdog)

  - **Скрытие окна в ангаре — только `WINDOW.hide(destroy=True)`:** скрытие через CSS (`display: none` / `visible=0`) или `hide()` без параметров оставляет нативный hit-test прямоугольник окна в движке — клики по кнопкам игры под панелью блокируются.
  - **Структурный Watchdog:** отслеживай окна на блокирующих слоях `BLOCK_LAYERS = [5, 6, 7, 8, 10, 11]` за вычетом `IGNORE_TYPES = [8, 33, 49, 65, 81, 98, 114]`. На слое `WINDOW (7)` считай блокерами **только модальные окна** (`WINDOW_MODALITY_MASK = 12288`), чтобы немодальные панели разных модов не прятали друг друга.
  - **Возврат из боя в ангар:** очищай `_sf_blockers.clear()` и `_wulf_blockers.clear()`, а также проверяй `READY_SEEN`.

### 6. Перетаскивание (Drag) и размеры экрана

  - **Размер экрана:** `viewEnv.getClientSizePx()` в бою возвращает логические координаты вместо физических. Используй `BigWorld.screenSize()` на стороне Python.
  - **Драг через `GUI.mcursor()`:** DOM-события `mousemove`/`mouseup` теряются при выходе курсора за рамки компактного окна. Запускай драг по `dragStart` из JS, а движение и отпускание ЛКМ опрашивай в Python через `GUI.mcursor().position` и `BigWorld.isKeyDown(Keys.KEY_LEFTMOUSE)`.

### 7. Особенности вёрстки и CSS в Coherent Gameface

  - **Запрет `!important` в CSS:** парсер Coherent Gameface НЕ поддерживает `!important` во многих свойствах (например, `margin-right: 0 !important`) и полностью отбрасывает всё правило. Управляй приоритетом через специфичность селекторов или напрямую через `element.style.marginRight = '0rem'` из JS.
  - **Центровка абсолютных оверлеев (дуги, прицелы, индикаторы):** избегай `left: 50%; margin-left: -Nrem` внутри flex-контейнеров с анимированными дочерними элементами (Coherent ошибается при пересчёте и даёт перекос влево). Используй обёртку во всю ширину родителя (`position: absolute; left: 0; width: 100%; display: flex; justify-content: center; pointer-events: none;`) — тогда оверлей и flex-элементы центрируются единым алгоритмом без смещений.
  - **SVG — только внешними файлами:** Coherent не рендерит inline `<svg><path/></svg>` и Data-URI SVG. Подключай `.svg` файлы только через CSS `background-image: url("./icon.svg")`, а для карточек со скруглёнными углами и градиентом используй фоновый `bg.svg` вместо CSS-градиентов с `border-radius`.
  - **Всепогодный контраст боевых элементов (снаряды, иконки):** для идеальной читаемости и на фоне белого неба/снега, и на фоне тёмного леса/воды используй в SVG двойной контур: плотную тёмную подложку (`fill="#090c10" fill-opacity="0.78"` + внешняя обводка `stroke="#000000"`) и яркий внутренний контур (`#e6c875` / `#eef4fa`). Для прицельных ореолов и дуг вместо резкой чёрной обводки используй многослойные полупрозрачные `<path>` разной толщины и прозрачности (`stroke-opacity="0.24"`, `"0.55"`, `"0.92"`), создающие эффект мягкого свечения (glow) без использования неподдерживаемого `filter: drop-shadow`.
  - **Запрет `height: auto` для SVG-контейнеров:** блок схлопывается в `0`. Задавай явные размеры в `rem`.
  - Для прогресс-баров и растущих дуг с обрезкой (`overflow: hidden`) задавай `background-size` в абсолютных `rem` полного изображения (например, `60rem 50rem` с `background-position: center bottom`), а не `100%`, иначе при изменении `width`/`height` маски картинка сожмётся вместо плавного проявления.

### 8. Чистота логирования

  - Логируй инициализацию, разрешение `layoutID`, создание окна (`uid`), итог боя и все исключения (`traceback.format_exc()`). В JS для вывода отладки в `python.log` используй `console.warn(...)` / `console.error(...)`.
  - Не логируй спам на каждый кадр или тик таймера.

## 9. Полевой чек-лист после патча клиента (Lesta)

Этот раздел — концентрированный опыт реального аудита мода `mark_battle` на клиенте 1.46.0.8558. Дополняет разделы 1–8. Порядок проверки — от «точно сломается» к «может сломаться».

### 9.1. Двукратный перезапуск после обновления `.mtmod` — не баг, а требование

`openwg_gameface` сливает `mods/configs/res_map/*.json` в общий `res_map.json` **один раз при старте клиента**, и это происходит **раньше**, чем `init()` мода успевает записать свои файлы `res_map`. Следствие:

- Первый запуск после установки/обновления мода: `layoutID` для **новых** `itemID` не резолвится (`INVALID_RES_ID`), окна не создаются.
- В `mark_battle.log` это выглядит так:
  ```text
  res_map configs ensured (written=3): ... (present=True) x3
  [TABLE] layout 'user.markbattle.table' not registered yet (restart client once)
  ```
- Второй запуск: `written=0`, все окна открываются.

**Обязательный паттерн логирования** (уже применён в `app.py`):
```python
written, info = ensure_res_map_configs()
_log(u'res_map configs ensured (written=%d): %s' % (written, info))
if written > 0:
    _log(u'*** NEXT CLIENT RESTART REQUIRED: res_map was updated, '
         u'Gameface will merge it only on next start ***')
```

Если у вас в логе `written>0`, а пользователь жалуется «таблица/окно не открывается» — **не ищите баг в коде**. Отправляйте на второй запуск.

**Дополнительно**: при каждом обновлении `.mtmod` (даже минорном) проверять, что `itemID` для **всех** окон присутствуют в merged-файле:
- Путь merged-файла: `<game>/res_mods/<version>/gui/unbound/gen/res_map.json`.
- Поиск по тексту: `<ваш_mod_id>` — должны быть видны все записи из вашего `res_map/<mod_id>.json`.

### 9.2. `onAvatarBecomeNonPlayer` обязан **уничтожать** боевое окно, а не просто обнулять указатель

Раздел 3 предписывает «уничтожай при `onAvatarBecomeNonPlayer`», но не уточняет, чем это грозит. Классическая ошибка:
```python
def _on_avatar_become_non_player(self):
    global WINDOW
    WINDOW = None          # НЕ УНИЧТОЖАЕТ нативное окно Wulf
```

**Последствия**:
- Нативное окно `WindowImpl` остаётся загруженным в клиенте, но Python теряет на него ссылку.
- В бою `_hide_panel()` для `_MODE == 'battle'` часто делают `no-op` (чтобы не убивать окно посреди боя) — значит, «спрятать» боевое окно в момент `onAvatarBecomeNonPlayer` **вообще некому**.
- Итог: после выхода из боя в правом нижнем углу (типичная дефолтная позиция боевой панели) остаётся **невидимый (CSS), но кликабельный** прямоугольник ~200×122. Если на экране послебоевой статистики там окажется кнопка «В ангар» — она не нажмётся. SKILL.md, раздел 5: «скрытие через CSS оставляет нативный hit-test прямоугольник».

**Правильный паттерн**:
```python
def _on_avatar_become_non_player(self):
    global _battle_active
    _battle_active = False
    try:
        view_mod.destroy_window()      # WINDOW.destroy() + WINDOW = None
    except Exception:
        _log(u'_on_avatar_become_non_player destroy CRASHED:\n%s'
             % traceback.format_exc())
```

**Как проверить, что фикс применился**: в `mark_battle.log` в момент выхода из боя должна появиться строка `window destroyed`. Если её нет — окно не уничтожено.

### 9.3. Watchdog-хуки приватных методов должны **логировать отказ**, а не молча деградировать

Раздел 5 описывает watchdog на приватные методы (`Hangar._populate`, `LoaderManager.loadView`, `ViewContainer.addView/_removeView`, `Window._cShowingStatusChanged`). Все они ставятся через `try/except: pass` — при переименовании в патче молча деградируют: мод работает, но перестаёт быть «вежливым» (панель перекрывает модалки других модов, не прячется под SF-окна).

**Правило**: каждый `_hook_*` в `except`-блоке обязан **писать в лог**, какой именно watchdog отвалился. Пример:
```python
def _hook_wulf_showing():
    try:
        from frameworks.wulf.windows_system.window import Window
    except Exception:
        try:
            from frameworks.wulf.window import Window
        except Exception as e:
            _log(u'WATCHDOG: Window import failed (both paths), '
                 u'Wulf blocker detection OFF: %r' % e)
            return
    # ...

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
    # ...

def _hook_container_tracking():
    try:
        from gui.Scaleform.framework.managers.containers import ViewContainer
    except Exception as e:
        _log(u'WATCHDOG: ViewContainer import failed, container tracking OFF: %r' % e)
        return
    # ...
```

**Диагностика**: при следующем патче Лесты первым делом `grep WATCHDOG mods/configs/<mod>/<mod>.log`. Если есть `WATCHDOG: …` — идите в `wotstat/wot-src` (ветка `mt-ru`) и смотрите актуальное имя метода/класса.

### 9.4. Магические константы Wulf — расшифровывать комментарием в коде

Числа `_WULF_LAYERS_SKIP`, `_WULF_LAYER_WINDOW`, `_WULF_MODALITY_MASK`, `_WULF_IGNORE_TYPES` в watchdog'е не имеют семантических имён в API. При патче их нужно перепроверять по исходникам. **Обязательный комментарий**:
```python
# --- Watchdog: числовые константы Wulf 1.2.2 (проверено на клиенте 1.46) ---
#
# Если после обновления Лесты watchdog перестал замечать модалки/уведомления
# или, наоборот, начал ложно прятать панель под немодальными окнами —
# ПЕРВЫМ ДЕЛОМ перепроверить именно эти константы по исходникам:
#   frameworks/wulf/__init__.py            (WindowLayer, WindowFlags)
#   frameworks/wulf/windows_system/window.py (windowFlags, layer)
# в репозитории wotstat/wot-src (ветка mt-ru) для актуальной версии.
#
# _WULF_LAYERS_SKIP     — слои, на которых окна не считаются блокерами.
# _WULF_LAYER_WINDOW    — слой обычных окон; на нём блокерами считаются
#                         только модальные окна (см. _WULF_MODALITY_MASK).
# _WULF_MODALITY_MASK   — битовая маска WindowFlags «модальность» (сейчас 0x3000).
# _WULF_IGNORE_TYPES    — типы (windowFlags & 0xFF), которые НЕ должны
#                         скрывать панель (tooltip, уведомления и т.п.).
_WULF_LAYERS_SKIP = frozenset([4, 14])
_WULF_LAYER_WINDOW = 7
_WULF_MODALITY_MASK = 12288
_WULF_IGNORE_TYPES = frozenset([8, 33, 49, 65, 81, 98, 114])
```

### 9.5. Ротация лога должна быть в **отдельном** `try` от записи

Раздел 8 требует логировать всё. Частая ловушка: ротация и запись в одном `try`:
```python
try:
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX:
        os.remove(LOG_FILE)          # упадёт, если файл залочен (антивирус, редактор)
    with codecs.open(LOG_FILE, 'a', 'utf-8') as f:
        f.write(...)                 # и эта строка не выполнится
except Exception:
    pass
```
Лог «замолкает» ровно тогда, когда вы его читаете. **Правильно** — три независимых `try`:
```python
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
```

### 9.6. Боевая панель: CSS-скрытие оставляет hit-test (известный компромисс)

В бою `_hide_panel()` часто делают `no-op` (чтобы не пересоздавать окно посреди боя). Между `period == 4` (послебоевая фаза) и фактическим `onAvatarBecomeNonPlayer` проходит 10–15 секунд, в течение которых окно существует, но скрыто CSS. Если пользователь пожалуется «не нажимается кнопка на экране результатов боя»:
1. Смотреть `mark_battle.log` — есть ли `window destroyed` сразу при выходе из боя.
2. Временно лечится `WINDOW.move(-2000, -2000)` в `set_visible(False)` для `_MODE == 'battle'` + возврат позиции в `_show_panel`.
3. Не рекомендуемое, но рабочее: `WINDOW.destroy()` при `period == 4`. Может конфликтовать с `_recreate_window`/`_recreate_budget`, если бой перезапускается (редкие сценарии).

### 9.7. `_on_avatar_become_player` в бою: `viewEnv.getClientSizePx()` возвращает **логические** координаты

Паттерн подтверждён на 1.46: `client=1920x1080` в бою при `BigWorld.screenSize() = 2560x1440` и 100% UI-scale. `_screen_size()` должен брать `BigWorld.screenSize()` (раздел 6). Дополнительный симптом — `card=200x122` (правильно), значит `measureCard`/`resizeViewRem` работают независимо от этой разницы.

### 9.8. Проверка кэша досье после боя

После боя в `dossier_cache.json` должна измениться запись текущего танка: `battlesCount +1`, `damageRating` на новое значение, `lastDelta` = разница. Если `battlesCount` не растёт — `_cache_dossier` не сработал: скорее всего `onAvatarBecomeNonPlayer` вызвал `_cache_dossier` слишком поздно (объект `dossier` уже недоступен) или `IItemsCache` не успел синхронизироваться. Кэш должен писаться в момент `onAvatarBecomePlayer` следующего боя или по `_on_items_cache_sync` в ангаре — **не** в `onAvatarBecomeNonPlayer`.

### 9.9. Порядок диагностики при жалобе «мод не работает после патча»

1. `mods/configs/<mod>/<mod>.log`: есть ли `written=N>0`? → **второй запуск** (см. 9.1).
2. Там же: `INVALID_RES_ID`? → **`res_map` не смёржен** (см. 9.1, пункт проверки merged-файла).
3. Там же: `WATCHDOG: …`? → **приватный API изменился** (см. 9.3), сверить с `wot-src`.
4. Там же: `Traceback`/`CRASHED`? → **ошибка в коде** мода, смотреть стек.
5. `python.log` в корне игры: `[MARK_BATTLE]` и любые `Traceback` — общий контекст.
6. Если ничего из 1–5 — идти в живой бой/ангар и смотреть, что **не** работает: таблица (окно не создаётся?), панель в бою (не создаётся/не видна?), кэш (не обновляется?), watchdog (панель не прячется под модалками других модов?).