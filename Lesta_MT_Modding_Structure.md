# ReloadTimer — структура проекта

## Корень проекта (то, что ты собираешь в .mtmod)

reload_timer/
│
├── build.py                                    # Сборщик .mtmod (Python 2.7)
├── build.bat                                   # Обёртка для запуска на Windows
├── meta.xml                                    # Метаданные мода (id, version, name)
│
├── mods/                                       # Игровая часть — Python-код
│   └── <game_version>/                         # Например, 1.45.0.0
│       └── scripts/
│           └── client/
│               └── gui/
│                   └── mods/
│                       └── mod_reload_timer/   # Пакет мода
│                           ├── __init__.py     # Утилиты, логирование, конфиг, res_map
│                           ├── mod_reload_timer.py  # Точка входа (init)
│                           ├── app.py          # Жизненный цикл боя + тик
│                           ├── reload_data.py  # Чтение данных перезарядки из клиента
│                           └── view.py         # ViewModel, окно wulf, драг, позиция
│
└── res/                                        # UI-часть — Gameface (HTML/CSS/JS/SVG)
    └── gui/
        └── gameface/
            └── mods/
                └── reload_timer/
                    ├── index.html                # Разметка панели
                    ├── index.css                 # Стили
                    ├── index.js                  # Логика отрисовки
                    ├── shell_loaded.svg          # Иконка заряженного снаряда
                    └── shell_empty.svg           # Иконка пустого снаряда


## Развёртывание в игре (куда ставится .mtmod)

<game_root>/
│
├── mods/
│   └── <game_version>/                         # Например, 1.45.0.0
│       ├── mod_reload_timer.mtmod              # Собранный архив
│       │
│       └── scripts/                            # После распаковки .mtmod
│           └── client/
│               └── gui/
│                   └── mods/
│                       └── mod_reload_timer/
│                           ├── __init__.pyc
│                           ├── mod_reload_timer.pyc
│                           ├── app.pyc
│                           ├── reload_data.pyc
│                           └── view.pyc
│
├── res_mods/
│   └── <game_version>/
│       ├── mods/
│       │   └── configs/
│       │       └── res_map/
│       │           └── reload_timer.json       # Регистрация Layout в res_map
│       │
│       └── gui/
│           └── gameface/
│               └── mods/
│                   └── reload_timer/           # UI-часть
│                       ├── index.html
│                       ├── index.css
│                       ├── index.js
│                       ├── shell_loaded.svg
│                       └── shell_empty.svg
│
└── mods/
    └── configs/
        └── reload_timer/                       # Рантайм-конфиг мода
            ├── config.json                     # Позиция окна (x, y)
            ├── base_time.json                  # Кэш эффективной перезарядки
            └── reload_timer.log                # Лог мода


## Развёртывание репозитория (dev-структура)

Файлы лежат в корне репо и раскладываются сборщиком:

reload_timer/                          # ← корень репозитория
│
├── build.py                           # читает res/ + mods/ → build/ → .mtmod
├── build.bat
├── meta.xml
│
├── res/                               # Исходники для Gameface (НЕ путать с res_mods/)
│   └── gui/gameface/mods/reload_timer/
│       ├── index.html
│       ├── index.css
│       ├── index.js
│       ├── shell_loaded.svg
│       └── shell_empty.svg
│
└── mods/                              # Исходники Python-пакета
    └── <game_version>/                # В репо обычно без версии, версия
        └── scripts/client/gui/mods/   #  подставляется при сборке
            └── mod_reload_timer/
                ├── __init__.py
                ├── mod_reload_timer.py
                ├── app.py
                ├── reload_data.py
                └── view.py


## Что делает каждая часть

### Python (mods/scripts/client/gui/mods/mod_reload_timer/)

| Файл | Ответственность |
|---|---|
| `__init__.py` | Лог, чтение/запись JSON-конфигов, `ensure_res_map_configs()`, `RES_MAP_ITEM_ID` |
| `mod_reload_timer.py` | Точка входа. Лоадер клиента вызывает `init(version)` |
| `app.py` | Подписка на `onAvatarBecomePlayer/NonPlayer`, жизненный цикл боя, тик 100 мс |
| `reload_data.py` | Читает `AmmoController`, `_dual_state` (хук `updateDualGunState`), собирает `state` dict |
| `view.py` | Создаёт `ReloadTimerWindow` через wulf/Gameface, ViewModel на 14 свойств, драг, позиция |

### Gameface UI (res/gui/gameface/mods/reload_timer/)

| Файл | Ответственность |
|---|---|
| `index.html` | Панель: top / mid / shells / bot |
| `index.css` | Стили: размеры, цвета, отступы, силуэты |
| `index.js` | Опрос `window.model`, форматирование чисел, rebuildShells |
| `shell_loaded.svg` | Заряженный снаряд (заливка) |
| `shell_empty.svg` | Пустой снаряд (контур) |

### Конфиги

| Файл | Назначение |
|---|---|
| `res_map/reload_timer.json` | Регистрирует `coui://gui/gameface/mods/reload_timer/index.html` как Layout с itemID `user.reloadtimer.panel`. **Без него окно не создастся.** |
| `configs/reload_timer/config.json` | `{"x": 994, "y": 474}` — сохранённая позиция окна |
| `configs/reload_timer/base_time.json` | `{"base_time": 6.35}` — эффективная перезарядка (для предбоевого показа) |
| `configs/reload_timer/reload_timer.log` | Отладочный лог, ротация при 512 КБ |

### Сборка

`build.py`:
1. Копирует `res/gui/gameface/` → `mods/gui/gameface/` (чтобы UI попал в `res_mods`, а не в `res`)
2. Собирает `build/` = `mods/` + `res/` + `meta.xml`
3. Подставляет `{{VERSION}}` в `meta.xml` и `mod_reload_timer.py`
4. Компилирует `.py` → `.pyc`, убирает исходники `.py`
5. Пакует `build/` в `reload_timer_<version>.mtmod` (ZIP без сжатия)


## Идентификаторы (важно не перепутать)

| Что | Значение | Где используется |
|---|---|---|
| MOD_ID (лоадер) | `user.reloadtimer` | `meta.xml`, `__init__.py` |
| RES_MAP itemID | `user.reloadtimer.panel` | `__init__.py`, `view.py` |
| Python-пакет | `mod_reload_timer` | `ENTRY_FILE` в `build.py` |
| Папка UI | `reload_timer` | пути в res_map и Gameface |
| Префикс лога | `RELOAD_TIMER` | `_log()` в `__init__.py` |


.mtmod — это обычный ZIP-архив (без сжатия) с такой внутренней структурой:

mod_reload_timer_v1.0.9.mtmod
├── meta.xml
├── mods/<game_version>/scripts/client/gui/mods/mod_reload_timer/*.pyc
└── mods/<game_version>/gui/gameface/mods/reload_timer/*.{html,css,js,svg}

res/ из репо не попадает в .mtmod — на этапе stage_sources() она уезжает в mods/gui/gameface/, чтобы клиент распаковал её в res_mods, а не в res. Прямая запись в res/ запрещена — игра перезапишет.