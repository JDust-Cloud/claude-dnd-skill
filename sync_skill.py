#!/usr/bin/env python3
"""sync_skill.py — mirror <repo>/skills/dnd to the installed Claude Code skill copy.

The installed copy at ~/.claude/skills/dnd is what games actually run.
Hand-editing it directly is banned — this is the only path it is ever
refreshed from.

Files present in the repo but missing/stale in the installed copy are
copied over (compared by content hash, not mtime — git checkouts don't
preserve mtimes reliably). Files present in the installed copy but gone
from the repo are deleted, EXCEPT:

  - __pycache__ directories anywhere (never copied, never deleted, never
    even inspected)
  - display/app.pid, display/app.log, display/.scheme — runtime state
    owned by the live display server, not source-controlled
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import sys

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = REPO_ROOT / "skills" / "dnd"
DEST = pathlib.Path.home() / ".claude" / "skills" / "dnd"

PRESERVE = {
    pathlib.Path("display/app.pid"),
    pathlib.Path("display/app.log"),
    pathlib.Path("display/.scheme"),
}


_SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache"}


def _iter_files(root: pathlib.Path):
    if not root.is_dir():
        return
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if _SKIP_DIR_NAMES & set(p.parts):
            continue
        yield p


def _hash(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mirror skills/dnd into the installed Claude Code skill copy."
    )
    parser.add_argument("--dry-run", action="store_true",
                         help="Print planned actions without changing anything.")
    args = parser.parse_args()

    if not SOURCE.is_dir():
        print(f"error: source not found: {SOURCE}", file=sys.stderr)
        return 1

    if not DEST.is_dir() and not args.dry_run:
        DEST.mkdir(parents=True)
        print(f"created {DEST}")

    source_files = {p.relative_to(SOURCE) for p in _iter_files(SOURCE)} - PRESERVE
    dest_files = {p.relative_to(DEST) for p in _iter_files(DEST)}

    to_copy = []
    for rel in sorted(source_files):
        dst_path = DEST / rel
        if not dst_path.exists() or _hash(SOURCE / rel) != _hash(dst_path):
            to_copy.append(rel)

    to_delete = sorted((dest_files - source_files) - PRESERVE)

    tag = "[dry-run] " if args.dry_run else ""
    for rel in to_copy:
        print(f"{tag}copy   {rel}")
        if not args.dry_run:
            dst_path = DEST / rel
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / rel, dst_path)

    for rel in to_delete:
        print(f"{tag}delete {rel}")
        if not args.dry_run:
            (DEST / rel).unlink()

    preserved_status = [f"{rel.as_posix()} ({'present' if (DEST / rel).exists() else 'absent'})"
                         for rel in sorted(PRESERVE)]

    print()
    print(f"{'[DRY RUN] ' if args.dry_run else ''}"
          f"{len(to_copy)} copied, {len(to_delete)} deleted, "
          f"runtime files preserved: {', '.join(preserved_status)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
