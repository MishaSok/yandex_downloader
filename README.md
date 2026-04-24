# Yandex Downloader

CLI-инструмент для загрузки треков с YouTube по очереди из базы данных. Импортирует лайкнутые треки из Яндекс.Музыки, ищет каждый на YouTube через `yt-dlp` и сохраняет аудио в MP3.

## Установка зависимостей

```bash
pip3 install yt-dlp rich --break-system-packages
sudo apt-get install -y ffmpeg        # опционально, для конвертации в MP3
```

Без `ffmpeg` треки сохраняются в формате `.webm` (Opus).

## Быстрый старт

```bash
# 1. Импортировать треки из Яндекс.Музыки
python3 download_track.py import liked_tracks.json

# 2. Посмотреть очередь
python3 download_track.py list

# 3. Скачать всё
python3 download_track.py download
```

Файлы сохраняются в папку `./downloads/`.

## Команды

### `import <file>`

Импортирует треки из JSON-файла экспорта Яндекс.Музыки в базу данных.

```bash
python3 download_track.py import liked_tracks.json
```

Уже существующие треки пропускаются (дубликаты не добавляются).

---

### `add <artist> <title>`

Добавляет один трек в очередь вручную.

```bash
python3 download_track.py add "Хаски" "Kanye West Diss"
python3 download_track.py add "Radiohead" "Creep"
```

---

### `list [--status STATUS]`

Показывает очередь в виде таблицы. Статусы подсвечиваются цветом:
- **жёлтый** — ожидает загрузки (`pending`)
- **зелёный** — загружен (`done`)
- **красный** — ошибка (`failed`)

```bash
python3 download_track.py list                  # все треки
python3 download_track.py list --status pending # только ожидающие
python3 download_track.py list --status failed  # только с ошибками
```

---

### `download [--limit N]`

Загружает все треки со статусом `pending`. Между запросами делает случайную паузу 2–5 секунд, чтобы не получить бан от YouTube.

```bash
python3 download_track.py download              # скачать всё
python3 download_track.py download --limit 10   # только первые 10
```

В процессе отображается прогресс-бар и результат каждого трека (`✓` / `✗`).

---

### `retry`

Сбрасывает все треки со статусом `failed` обратно в `pending`, после чего можно запустить `download` повторно.

```bash
python3 download_track.py retry
python3 download_track.py download
```

## Формат liked_tracks.json

Файл должен быть массивом объектов:

```json
[
  {
    "artist": "Хаски",
    "title": "Kanye West Diss",
    "duration": "3:12",
    "duration_sec": 192,
    "index": 1
  }
]
```

Обязательные поля: `artist`, `title`. Остальные — опциональны.

## Структура проекта

```
.
├── download_track.py   # весь код
├── tracks.db           # SQLite-база (создаётся автоматически)
└── downloads/          # загруженные файлы (создаётся автоматически)
```

## Известные ограничения

- Поиск берёт первый результат с YouTube — иногда попадается не тот трек
- Один трек за раз, нет параллельной загрузки
- Нет автоматического повтора при ошибке сети — нужно запускать `retry` вручную
