#!/usr/bin/env python3
"""
Track downloader with SQLite queue.

Commands:
  import <file.json>          Import tracks from Yandex liked_tracks.json
  add <artist> <title>        Add a single track to the queue
  list [--status STATUS]      Show queue (default: all)
  download [--limit N]        Download all pending tracks
  retry                       Retry all failed tracks
"""

import argparse
import json
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from mutagen import File as MutagenFile

from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeElapsedColumn, MofNCompleteColumn,
)
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()

STATUS_STYLE = {
    "pending": "yellow",
    "done":    "green",
    "failed":  "red bold",
}

_DIR = Path(__file__).parent
DB_PATH = _DIR / "tracks.db"
DOWNLOADS_DIR = _DIR / "downloads"
MAX_DURATION_SEC = 15 * 60


class TooLongError(Exception):
    pass


# ── Database ──────────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            artist         TEXT    NOT NULL,
            title          TEXT    NOT NULL,
            duration       TEXT,
            duration_sec   INTEGER,
            yandex_index   INTEGER,
            cover_url      TEXT,
            status         TEXT    NOT NULL DEFAULT 'pending',
            file_path      TEXT,
            error          TEXT,
            added_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            downloaded_at  TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_artist_title
        ON tracks (artist, title)
    """)
    conn.commit()
    return conn


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def build_yt_dlp_cmd(query: str, output_dir: Path) -> list[str]:
    search = f"ytsearch1:{query}"
    common = [
        "--no-playlist",
        "--print", "%(duration)s",        # printed before download starts
        "--print", "after_move:filepath",
    ]
    if find_ffmpeg():
        return [
            "yt-dlp",
            "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0",
            "--output", str(output_dir / "%(title)s.%(ext)s"),
            *common, search,
        ]
    else:
        return [
            "yt-dlp",
            "--format", "bestaudio",
            "--output", str(output_dir / "%(title)s.%(ext)s"),
            *common, search,
        ]


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()


def fmt_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def embed_metadata(filepath: Path, artist: str, title: str) -> None:
    try:
        audio = MutagenFile(str(filepath), easy=True)
        if audio is None:
            return
        if audio.tags is None:
            audio.add_tags()
        audio["artist"] = [artist]
        audio["title"] = [title]
        audio.save()
    except Exception:
        pass


def download_one(query: str, output_dir: Path, artist: str, title: str) -> str:
    """Returns file path on success, raises RuntimeError or TooLongError."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_yt_dlp_cmd(query, output_dir)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # First --print fires before the download: duration in seconds
    dur_line = proc.stdout.readline().strip()
    try:
        dur_sec = int(dur_line)
    except ValueError:
        dur_sec = 0

    if dur_sec > MAX_DURATION_SEC:
        proc.kill()
        proc.wait()
        raise TooLongError(f"too long ({fmt_duration(dur_sec)})")

    stdout_rest, stderr = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.strip().splitlines()[-1] if stderr.strip() else "yt-dlp error")

    filepath_line = stdout_rest.strip().splitlines()[-1] if stdout_rest.strip() else ""
    if not filepath_line:
        raise RuntimeError("yt-dlp produced no output")

    downloaded = Path(filepath_line)
    target_name = sanitize_filename(f"{artist} - {title}") + downloaded.suffix
    target = downloaded.parent / target_name
    if downloaded != target:
        downloaded.rename(target)
    embed_metadata(target, artist, title)
    return str(target)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_import(args: argparse.Namespace) -> None:
    path = Path(args.file)
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {path}")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    conn = get_conn()
    added = skipped = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Importing...", total=len(data))
        for item in data:
            try:
                conn.execute("""
                    INSERT INTO tracks (artist, title, duration, duration_sec, yandex_index, cover_url)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (item["artist"], item["title"], item.get("duration"), item.get("duration_sec"), item.get("index"), item.get("cover_url")))
                added += 1
            except sqlite3.IntegrityError:
                skipped += 1
            progress.advance(task)

    conn.commit()
    conn.close()
    console.print(f"[green]✓[/green] Imported [bold]{added}[/bold] tracks" +
                  (f", [dim]{skipped} skipped[/dim]" if skipped else ""))


def cmd_add(args: argparse.Namespace) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO tracks (artist, title) VALUES (?, ?)",
            (args.artist, args.title),
        )
        conn.commit()
        console.print(f"[green]✓[/green] Added: [bold]{args.artist}[/bold] — {args.title}")
    except sqlite3.IntegrityError:
        console.print(f"[yellow]![/yellow] Already in queue: [bold]{args.artist}[/bold] — {args.title}")
    conn.close()


def cmd_list(args: argparse.Namespace) -> None:
    conn = get_conn()
    if args.status:
        rows = conn.execute(
            "SELECT id, artist, title, status, duration FROM tracks WHERE status = ? ORDER BY yandex_index, id",
            (args.status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, artist, title, status, duration FROM tracks ORDER BY yandex_index, id"
        ).fetchall()

    if not rows:
        console.print("[dim]Queue is empty.[/dim]")
        conn.close()
        return

    counts = conn.execute(
        "SELECT status, COUNT(*) as n FROM tracks GROUP BY status"
    ).fetchall()
    conn.close()

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold dim")
    table.add_column("#", style="dim", justify="right", width=5)
    table.add_column("Status", width=9)
    table.add_column("Artist", style="bold")
    table.add_column("Title")
    table.add_column("Duration", justify="right", style="dim")

    for row in rows:
        style = STATUS_STYLE.get(row["status"], "")
        table.add_row(
            str(row["id"]),
            Text(row["status"], style=style),
            row["artist"],
            row["title"],
            row["duration"] or "",
        )

    console.print(table)

    parts = []
    for c in counts:
        style = STATUS_STYLE.get(c["status"], "")
        parts.append(f"[{style}]{c['status']}: {c['n']}[/{style}]")
    console.print("  " + "  ·  ".join(parts))


def cmd_download(args: argparse.Namespace) -> None:
    if not find_ffmpeg():
        console.print("[yellow]Warning:[/yellow] ffmpeg not found — saving as .webm instead of .mp3\n")

    conn = get_conn()
    query = "SELECT id, artist, title FROM tracks WHERE status = 'pending' ORDER BY yandex_index, id"
    if args.limit:
        query += f" LIMIT {args.limit}"
    rows = conn.execute(query).fetchall()

    if not rows:
        console.print("[dim]No pending tracks.[/dim]")
        conn.close()
        return

    total = len(rows)
    console.print(Panel(f"[bold]Downloading [green]{total}[/green] track{'s' if total != 1 else ''}[/bold]", expand=False))

    done = failed = skipped = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("·"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        overall = progress.add_task("[dim]overall[/dim]", total=total)
        current = progress.add_task("", total=None)

        for i, row in enumerate(rows, 1):
            artist, title = row["artist"], row["title"]
            search_query = f"{artist} - {title}"
            label = f"[bold]{artist}[/bold] — {title}"
            progress.update(current, description=f"↓  {label}")

            try:
                filepath = download_one(search_query, DOWNLOADS_DIR, artist, title)
                conn.execute(
                    "UPDATE tracks SET status='done', file_path=?, error=NULL, downloaded_at=? WHERE id=?",
                    (filepath, datetime.now().isoformat(), row["id"]),
                )
                conn.commit()
                console.print(f"  [green]✓[/green] {label}  [dim]{Path(filepath).name}[/dim]")
                done += 1
            except TooLongError as e:
                error_msg = str(e)
                conn.execute(
                    "UPDATE tracks SET status='failed', error=? WHERE id=?",
                    (error_msg, row["id"]),
                )
                conn.commit()
                console.print(f"  [yellow]⊘[/yellow] {label}  [yellow dim]{error_msg}[/yellow dim]")
                skipped += 1
            except Exception as e:
                error_msg = str(e)
                conn.execute(
                    "UPDATE tracks SET status='failed', error=? WHERE id=?",
                    (error_msg, row["id"]),
                )
                conn.commit()
                console.print(f"  [red]✗[/red] {label}  [red dim]{error_msg}[/red dim]")
                failed += 1

            progress.advance(overall)
            progress.update(current, description="")

            if i < total:
                time.sleep(random.uniform(2, 5))

    conn.close()

    parts = []
    if done:
        parts.append(f"[green]{done} downloaded[/green]")
    if skipped:
        parts.append(f"[yellow]{skipped} skipped (too long)[/yellow]")
    if failed:
        parts.append(f"[red]{failed} failed[/red]")
    console.print("\n  " + "  ·  ".join(parts))


def cmd_retry(args: argparse.Namespace) -> None:
    conn = get_conn()
    conn.execute("UPDATE tracks SET status='pending', error=NULL WHERE status='failed'")
    n = conn.total_changes
    conn.commit()
    conn.close()
    if n:
        console.print(f"[green]✓[/green] Reset [bold]{n}[/bold] failed tracks to pending. Run [bold]download[/bold] to retry.")
    else:
        console.print("[dim]No failed tracks to retry.[/dim]")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube track downloader with SQLite queue.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="Import tracks from JSON file")
    p_import.add_argument("file", help="Path to liked_tracks.json")

    p_add = sub.add_parser("add", help="Add a single track")
    p_add.add_argument("artist")
    p_add.add_argument("title")

    p_list = sub.add_parser("list", help="Show queue")
    p_list.add_argument("--status", choices=["pending", "done", "failed"], help="Filter by status")

    p_dl = sub.add_parser("download", help="Download pending tracks")
    p_dl.add_argument("--limit", type=int, help="Max number of tracks to download")

    sub.add_parser("retry", help="Reset failed tracks to pending")

    args = parser.parse_args()
    {
        "import": cmd_import,
        "add":    cmd_add,
        "list":   cmd_list,
        "download": cmd_download,
        "retry":  cmd_retry,
    }[args.command](args)


if __name__ == "__main__":
    main()
