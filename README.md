# Yandex Music Downloader

Инструмент для скачивания лайкнутых треков из Яндекс Музыки через YouTube.

Работает в два этапа:
1. **Парсер** (`parser/`) — открывает браузер, заходит на страницу плейлиста и собирает список треков в JSON/CSV.
2. **Загрузчик** (`script/`) — берёт треки из базы данных, ищет каждый на YouTube через `yt-dlp` и сохраняет аудио в MP3.

---

## Требования

- Python 3.10+
- Google Chrome (для парсера)
- `ffmpeg` (опционально, но нужен для конвертации в MP3)

---

## Установка

### 1. Зависимости парсера

```bash
pip install -r parser/requirements.txt
```

Устанавливает: `selenium`, `webdriver-manager` (ChromeDriver скачивается автоматически).

### 2. Зависимости загрузчика

```bash
pip install yt-dlp rich mutagen --break-system-packages
```

### 3. ffmpeg (рекомендуется)

```bash
sudo apt-get install -y ffmpeg
```

Без `ffmpeg` треки сохраняются в формате `.webm` вместо `.mp3`.

---

## Быстрый старт

Полный цикл одной командой:

```bash
python3 run.py "https://music.yandex.ru/playlists/lk.xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

Скрипт последовательно:
1. Откроет браузер и соберёт треки из плейлиста → `parser/liked_tracks.json`
2. Импортирует их в базу данных → `script/tracks.db`
3. Скачает всё через YouTube → `script/downloads/`

> Если потребуется авторизация, войдите в открытое окно Chrome вручную — скрипт подождёт до 90 секунд.

---

## Использование run.py

```bash
# Полный цикл (парсинг + импорт + скачка)
python3 run.py "https://music.yandex.ru/users/login/playlists/3"

# Скачать только первые 20 треков за один запуск
python3 run.py "https://music.yandex.ru/..." --limit 20

# Пропустить парсинг — использовать готовый parser/liked_tracks.json
python3 run.py --no-parse

# Только распарсить и импортировать, без скачки
python3 run.py "https://music.yandex.ru/..." --no-download
```

---

## Парсер (parser/main.py)

Парсер поддерживает:
- плейлисты «Мне нравится» (`/playlists/lk.xxxx`)
- обычные плейлисты (`/users/login/playlists/3`)
- альбомы (`/album/12345`)

```bash
python3 parser/main.py "https://music.yandex.ru/playlists/lk.xxxx"
```

Результат сохраняется в:
- `parser/liked_tracks.json` — основной файл для загрузчика
- `parser/liked_tracks.csv` — для просмотра в Excel/Google Sheets

### Формат JSON

```json
[
  {
    "index": 1,
    "title": "Kanye West Diss",
    "artist": "Хаски",
    "duration": "3:12",
    "duration_sec": 192,
    "cover_url": "https://avatars.yandex.net/get-music-content/.../200x200"
  }
]
```

### Настройки парсера

В файле `parser/main.py` можно изменить:

| Переменная      | По умолчанию | Описание |
|-----------------|-------------|----------|
| `PLAYLIST_URL`  | —           | URL по умолчанию (если не передан аргумент) |
| `SCROLL_PAUSE`  | `1.5`       | Пауза между шагами скролла (сек) |
| `SCROLL_RETRIES`| `6`         | Шагов без новых треков до остановки |
| `LOGIN_TIMEOUT` | `90`        | Время ожидания авторизации (сек) |
| `HEADLESS`      | `False`     | `True` — запуск без окна браузера |

---

## Загрузчик (script/download_track.py)

### `import <file>`

Импортирует треки из JSON в базу данных. Дубликаты пропускаются.

```bash
python3 script/download_track.py import parser/liked_tracks.json
```

---

### `list [--status STATUS]`

Показывает очередь в виде таблицы с цветовой индикацией статусов.

```bash
python3 script/download_track.py list                   # все треки
python3 script/download_track.py list --status pending  # ожидают загрузки
python3 script/download_track.py list --status done     # загружены
python3 script/download_track.py list --status failed   # с ошибками
```

---

### `download [--limit N]`

Скачивает все треки со статусом `pending`. Между запросами — случайная пауза 2–5 секунд.

```bash
python3 script/download_track.py download             # скачать всё
python3 script/download_track.py download --limit 50  # только 50 треков
```

Треки длиннее 15 минут автоматически пропускаются (помечаются `failed`).

---

### `add <artist> <title>`

Добавляет один трек вручную.

```bash
python3 script/download_track.py add "Хаски" "Kanye West Diss"
python3 script/download_track.py add "Radiohead" "Creep"
```

---

### `retry`

Сбрасывает все треки с ошибками обратно в очередь.

```bash
python3 script/download_track.py retry
python3 script/download_track.py download
```

---

## Структура проекта

```
.
├── run.py                     # единый запуск: парсинг → импорт → скачка
│
├── parser/
│   ├── main.py                # парсер Яндекс Музыки (Selenium)
│   ├── requirements.txt       # selenium, webdriver-manager
│   ├── liked_tracks.json      # результат парсинга (генерируется)
│   └── liked_tracks.csv       # то же в CSV (генерируется)
│
└── script/
    ├── download_track.py      # загрузчик с SQLite-очередью
    ├── tracks.db              # база данных (генерируется)
    └── downloads/             # скачанные MP3 (генерируется)
```

---

## Известные ограничения

- Поиск берёт первый результат с YouTube — иногда попадается не тот трек
- Нет параллельной загрузки — треки скачиваются по одному
- Нет автоматического повтора при обрыве сети — запустите `retry` вручную
- Треки длиннее 15 минут пропускаются автоматически
