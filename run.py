#!/usr/bin/env python3
"""
Единый запуск: парсинг Яндекс Музыки → импорт в БД → скачка треков.

Использование:
    python3 run.py <url-плейлиста>
    python3 run.py  # использует URL из parser/main.py (PLAYLIST_URL)

Флаги:
    --limit N     скачать только N треков за один запуск
    --no-parse    пропустить парсинг (использовать существующий parser/liked_tracks.json)
    --no-download пропустить скачку (только распарсить и импортировать)
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PARSER_SCRIPT = ROOT / "parser" / "main.py"
DOWNLOADER_SCRIPT = ROOT / "script" / "download_track.py"
PARSER_OUTPUT = ROOT / "parser" / "liked_tracks.json"


def run(cmd: list) -> None:
    result = subprocess.run([sys.executable, *cmd])
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Парсинг + скачка треков с Яндекс Музыки")
    parser.add_argument("url", nargs="?", help="Ссылка на плейлист Яндекс Музыки")
    parser.add_argument("--limit", type=int, help="Максимальное число треков для скачки")
    parser.add_argument("--no-parse", action="store_true", help="Пропустить парсинг")
    parser.add_argument("--no-download", action="store_true", help="Пропустить скачку")
    args = parser.parse_args()

    if not args.no_parse:
        print("=" * 60)
        print("  Шаг 1/3: парсинг плейлиста")
        print("=" * 60)
        cmd = [str(PARSER_SCRIPT)]
        if args.url:
            cmd.append(args.url)
        run(cmd)

    print("=" * 60)
    print("  Шаг 2/3: импорт треков в базу данных")
    print("=" * 60)
    run([str(DOWNLOADER_SCRIPT), "import", str(PARSER_OUTPUT)])

    if not args.no_download:
        print("=" * 60)
        print("  Шаг 3/3: скачка треков")
        print("=" * 60)
        dl_cmd = [str(DOWNLOADER_SCRIPT), "download"]
        if args.limit:
            dl_cmd += ["--limit", str(args.limit)]
        run(dl_cmd)


if __name__ == "__main__":
    main()
