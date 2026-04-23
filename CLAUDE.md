# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

CLI script that searches YouTube (via `yt-dlp`) for a track by artist + title and downloads the audio. If `ffmpeg` is present, converts to MP3; otherwise saves as-is (usually `.webm`/Opus).

## Running the script

```bash
# Two positional args: artist, title
python3 download_track.py "Хаски" "kanye west diss"

# Free-form query
python3 download_track.py --query "Хаски kanye west diss"

# Custom output directory
python3 download_track.py "Хаски" "kanye west diss" --out ~/Music
```

Downloaded files land in `./downloads/` by default.

## Dependencies

- `yt-dlp` — install: `pip3 install yt-dlp --break-system-packages`
- `rich` — install: `pip3 install rich --break-system-packages`
- `ffmpeg` — install: `sudo apt-get install -y ffmpeg` (optional but required for true MP3 output)

## Architecture

Single file `download_track.py`:

- `main()` — parses CLI args (argparse), routes to `download()`
- `build_query(artist, title)` — joins into `"artist - title"` string
- `download(query, output_dir)` — checks for ffmpeg, builds the `yt-dlp` command, runs it via `subprocess.run()`
- YouTube search uses `yt-dlp`'s built-in `ytsearch1:` prefix — no separate search API needed

## Known limitations

- One track per invocation; no batch/list-file mode yet
- No retry on failure — `sys.exit()` on non-zero yt-dlp exit code
- No rate limiting / sleep between requests (causes YouTube 429 at scale)
- No skip-if-already-downloaded logic
