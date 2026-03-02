# radio/scan_media.py
from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path
from typing import Iterable, Optional

from mutagen.mp3 import MP3

from .db import connect
from .helpers import MediaInfo, upsert_media, upsert_station, link_station_media
from .station_config import StationConfig, load_station_toml
from . import terminal as T


def parse_artist_title(filename: str) -> tuple[Optional[str], Optional[str]]:
    stem = Path(filename).stem.strip()
    if " - " in stem:
        a, t = stem.split(" - ", 1)
        return (a.strip() or None, t.strip() or None)
    return (None, stem or None)


def duration_s(path: Path) -> float:
    try:
        return float(MP3(path).info.length)
    except Exception:
        return 0.0


def iter_mp3(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for p in root.rglob("*.mp3"):
        if p.is_file():
            yield p


def _progress(label: str, n: int) -> None:
    """Overwrite the current line with a progress counter (TTY only)."""
    if T._IS_TTY:
        print(
            f"\r  {T.YELLOW}{label}:{T.RESET} {T.BOLD}{n}{T.RESET} files...",
            end="",
            flush=True,
        )


def _progress_done() -> None:
    """Move to a new line after in-place progress output."""
    if T._IS_TTY:
        print()


def scan_songs(con, music_root: str, *, station_ids: list = None, verbose: bool) -> int:
    """Scan the music root for MP3 files and upsert them into the media table as songs.

    If station_ids is provided, each song is also linked to those stations in station_media
    so they can be selected by the scheduler.
    """
    root = Path(music_root).expanduser().resolve()
    n = 0
    for p in iter_mp3(root):
        tag = p.parent.name
        artist, title = parse_artist_title(p.name)
        mtime = int(p.stat().st_mtime)
        dur = duration_s(p)

        media_id = upsert_media(
            con,
            MediaInfo(
                path=str(p),
                kind="song",
                artist=artist,
                title=title,
                tag=tag,
                duration_s=dur,
                mtime=mtime,
            ),
        )
        for sid in (station_ids or []):
            link_station_media(con, sid, media_id)
        n += 1
        if verbose:
            print(
                f"  {T.DIM}[song]{T.RESET} {T.CYAN}{tag:>10}{T.RESET}"
                f"  {p.name}  {T.DIM}({dur:.1f}s)  id={media_id}{T.RESET}"
            )
        else:
            _progress("Scanning songs", n)

    if not verbose:
        _progress_done()

    con.commit()
    return n


def scan_station_media_dir(con, station_id: int, directory: str, kind: str, *, verbose: bool) -> int:
    """Scan a directory for MP3s of the given kind and link them to the station."""
    if not directory:
        return 0

    d = Path(directory).expanduser().resolve()
    if not d.exists():
        return 0

    n = 0
    for p in iter_mp3(d):
        mtime = int(p.stat().st_mtime)
        dur = duration_s(p)
        media_id = upsert_media(
            con,
            MediaInfo(
                path=str(p),
                kind=kind,
                artist=None,
                title=p.stem,
                tag=None,
                duration_s=dur,
                mtime=mtime,
            ),
        )
        link_station_media(con, station_id, media_id)
        n += 1
        if verbose:
            print(
                f"  {T.DIM}[{kind:<10}]{T.RESET} {p.name}"
                f"  {T.DIM}({dur:.1f}s)  id={media_id}  linked\u2192station {station_id}{T.RESET}"
            )
        else:
            _progress(kind, n)

    if not verbose:
        _progress_done()

    con.commit()
    return n


def scan_schedule_overlays(
    con, station_id: int, cfg: StationConfig, *, verbose: bool
) -> dict[str, int]:
    """
    Scan all overlay directories referenced in the schedule.
    Returns a dict mapping overlays_dir -> count of files scanned.
    """
    results = {}
    seen_dirs: set[str] = set()

    for day, hour_map in cfg.schedule.items():
        for hour, entry in hour_map.items():
            if not entry.overlays_dir or entry.overlays_dir in seen_dirs:
                continue

            seen_dirs.add(entry.overlays_dir)
            schedule_key = f"{day}-{hour}"

            con.execute(
                """
                INSERT INTO station_overlays(
                    station_id, schedule_key, overlays_dir, overlays_probability
                )
                VALUES(?,?,?,?)
                ON CONFLICT(station_id, schedule_key) DO UPDATE SET
                    overlays_dir=excluded.overlays_dir,
                    overlays_probability=excluded.overlays_probability
                """,
                (station_id, schedule_key, entry.overlays_dir, entry.overlays_probability)
            )

            n = scan_station_media_dir(
                con, station_id, entry.overlays_dir, "overlay", verbose=verbose
            )
            results[entry.overlays_dir] = n

    return results


def load_station_cfgs(patterns: list[str]) -> list[StationConfig]:
    paths: list[str] = []
    for pat in patterns:
        expanded = glob.glob(pat)
        paths.extend(expanded if expanded else [pat])
    return [load_station_toml(p) for p in paths]


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan songs/idents/overlays/commercials into radio.db")
    ap.add_argument("--db", default="/home/radio/radio-code/radio.db")
    ap.add_argument("--music", required=True, help="Root containing tag subfolders (recursive)")
    ap.add_argument("--stations", nargs="+", required=True, help="Station TOML paths or globs")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    con = connect(str(Path(args.db).expanduser()))
    print(f"{T.BOLD}{T.BLUE}DB:{T.RESET} {args.db}")

    # Upsert stations first so we can link songs to them
    cfgs = load_station_cfgs(args.stations)
    station_ids = []
    for cfg in cfgs:
        sid = upsert_station(con, cfg)
        print(
            f"{T.GREEN}\u2713 Station:{T.RESET} {T.BOLD}{T.CYAN}{cfg.name}{T.RESET}"
            f" @ {T.MAGENTA}{cfg.freq:.1f}{T.RESET} FM"
            f"  {T.DIM}(id={sid}){T.RESET}"
        )
        station_ids.append(sid)

    print(f"\n{T.BOLD}{T.BLUE}Scanning songs under:{T.RESET} {args.music}")
    n_songs = scan_songs(con, args.music, station_ids=station_ids, verbose=args.verbose)
    print(f"  {T.GREEN}Songs: {T.BOLD}{n_songs}{T.RESET}")

    for cfg, sid in zip(cfgs, station_ids):
        print(f"\n{T.BOLD}{T.BLUE}Scanning station media:{T.RESET} {T.BOLD}{T.CYAN}{cfg.name}{T.RESET}")

        n_idents = scan_station_media_dir(con, sid, cfg.idents_dir, "ident", verbose=args.verbose)
        n_commercials = scan_station_media_dir(con, sid, cfg.commercials_dir, "commercial", verbose=args.verbose)
        n_toth = scan_station_media_dir(con, sid, cfg.top_of_the_hour, "top_of_hour", verbose=args.verbose)
        print(f"  {T.GREEN}idents: {T.BOLD}{n_idents}{T.RESET}")
        print(f"  {T.GREEN}commercials: {T.BOLD}{n_commercials}{T.RESET}")
        print(f"  {T.GREEN}top_of_the_hour: {T.BOLD}{n_toth}{T.RESET}")

        overlay_counts = scan_schedule_overlays(con, sid, cfg, verbose=args.verbose)
        if overlay_counts:
            print(f"  {T.GREEN}overlays:{T.RESET}")
            for dir_path, n in overlay_counts.items():
                print(f"    {T.DIM}{dir_path}:{T.RESET} {T.BOLD}{n}{T.RESET} files")

    con.commit()
    con.close()
    print(f"\n{T.BOLD}{T.BRIGHT_GREEN}\u2713 Done.{T.RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
