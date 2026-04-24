# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Two-component tool for downloading your Yandex Music liked tracks via YouTube:

1. **`parser/`** — Selenium-based scraper that exports the "Мне нравится" playlist from Yandex Music to JSON/CSV.
2. **`script/`** — CLI downloader that searches YouTube (via `yt-dlp`) for each track and downloads the audio as MP3.

## Directory structure

```
parser/
  main.py            Yandex Music playlist scraper (Selenium + Chrome)
  requirements.txt   selenium, webdriver-manager
  liked_tracks.csv   output (generated)
  liked_tracks.json  output (generated)

script/
  download_track.py  YouTube downloader with SQLite queue
  tracks.db          SQLite queue (generated)
  downloads/         Downloaded MP3 files (generated)
```

## Единый запуск (рекомендуется)

```bash
# Полный цикл: парсинг → импорт → скачка
python3 run.py "https://music.yandex.ru/playlists/lk.xxxx"

# Скачать только первые 10 треков
python3 run.py "https://music.yandex.ru/playlists/lk.xxxx" --limit 10

# Пропустить парсинг, использовать готовый parser/liked_tracks.json
python3 run.py --no-parse

# Только распарсить и импортировать, без скачки
python3 run.py "https://music.yandex.ru/playlists/lk.xxxx" --no-download
```

## Отдельный запуск парсера

```bash
pip install -r parser/requirements.txt
python3 parser/main.py "https://music.yandex.ru/playlists/lk.xxxx"
# Outputs: parser/liked_tracks.json, parser/liked_tracks.csv
```

## Отдельный запуск загрузчика

```bash
# Import tracks from parser output
python3 script/download_track.py import parser/liked_tracks.json

# Show queue
python3 script/download_track.py list

# Download all pending tracks
python3 script/download_track.py download

# Add a single track manually
python3 script/download_track.py add "Хаски" "kanye west diss"

# Retry failed tracks
python3 script/download_track.py retry
```

Downloaded files land in `script/downloads/`.

## Script dependencies

- `yt-dlp` — `pip3 install yt-dlp --break-system-packages`
- `rich` — `pip3 install rich --break-system-packages`
- `mutagen` — `pip3 install mutagen --break-system-packages`
- `ffmpeg` — `sudo apt-get install -y ffmpeg` (optional; required for MP3 output)

## Script architecture (`script/download_track.py`)

- `main()` — argparse entry point, dispatches to subcommands
- `cmd_import / cmd_add / cmd_list / cmd_download / cmd_retry` — one function per subcommand
- `download_one(query, output_dir, artist, title)` — calls yt-dlp, renames file, embeds ID3 tags
- `get_conn()` — opens/migrates the SQLite database
- YouTube search uses `yt-dlp`'s built-in `ytsearch1:` prefix — no separate search API needed

## Known limitations

- No retry on network error mid-download (mark failed + run `retry`)
- No rate limiting beyond random 2–5 s sleep between tracks
