#!/usr/bin/env python3
r"""sync_skill.py — mirror <repo>/skills/dnd to the installed Claude Code skill copy.

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

Failure discipline (2026-07-12 hardening): a file that cannot be read,
copied, or deleted — e.g. a Windows reserved-name file like `nul` that a
shell accident left in the installed dir — NO LONGER aborts the mirror.
Each such file is retried through the Win32 `\\?\` long-path prefix
(which reaches reserved names), then recorded and skipped. The run ends
with a failure summary and exit code 1 so the failure is never silent.
"""
from __future__ import annotations

import argparse
import hashlib
import os
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


def _extended(path: pathlib.Path) -> str:
    r"""Absolute path with the Win32 `\\?\` prefix on Windows — the only way
    to address reserved device names (nul, con, aux, com1…) as files."""
    s = str(path if path.is_absolute() else path.resolve())
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + s
    return s


def _read_bytes(path: pathlib.Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        with open(_extended(path), "rb") as f:  # \\?\ fallback
            return f.read()


def _hash(path: pathlib.Path) -> str:
    return hashlib.sha256(_read_bytes(path)).hexdigest()


def _copy(src: pathlib.Path, dst: pathlib.Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dst)
    except OSError:
        shutil.copy2(_extended(src), _extended(dst))  # \\?\ fallback


def _delete(path: pathlib.Path) -> None:
    try:
        path.unlink()
    except OSError:
        os.unlink(_extended(path))  # \\?\ fallback


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Mirror skills/dnd into the installed Claude Code skill copy."
    )
    parser.add_argument("--dry-run", action="store_true",
                         help="Print planned actions without changing anything.")
    args = parser.parse_args(argv)

    if not SOURCE.is_dir():
        print(f"error: source not found: {SOURCE}", file=sys.stderr)
        return 1

    if not DEST.is_dir() and not args.dry_run:
        DEST.mkdir(parents=True)
        print(f"created {DEST}")

    source_files = {p.relative_to(SOURCE) for p in _iter_files(SOURCE)} - PRESERVE
    dest_files = {p.relative_to(DEST) for p in _iter_files(DEST)}

    failures: list[tuple[str, pathlib.Path, str]] = []

    to_copy = []
    for rel in sorted(source_files):
        dst_path = DEST / rel
        try:
            if not dst_path.exists() or _hash(SOURCE / rel) != _hash(dst_path):
                to_copy.append(rel)
        except OSError as e:
            failures.append(("compare", rel, str(e)))

    to_delete = sorted((dest_files - source_files) - PRESERVE)

    tag = "[dry-run] " if args.dry_run else ""
    copied = 0
    for rel in to_copy:
        print(f"{tag}copy   {rel}")
        if not args.dry_run:
            try:
                _copy(SOURCE / rel, DEST / rel)
                copied += 1
            except OSError as e:
                failures.append(("copy", rel, str(e)))
        else:
            copied += 1

    deleted = 0
    for rel in to_delete:
        print(f"{tag}delete {rel}")
        if not args.dry_run:
            try:
                _delete(DEST / rel)
                deleted += 1
            except OSError as e:
                failures.append(("delete", rel, str(e)))
        else:
            deleted += 1

    preserved_status = [f"{rel.as_posix()} ({'present' if (DEST / rel).exists() else 'absent'})"
                         for rel in sorted(PRESERVE)]

    print()
    print(f"{'[DRY RUN] ' if args.dry_run else ''}"
          f"{copied} copied, {deleted} deleted, "
          f"runtime files preserved: {', '.join(preserved_status)}")

    if failures:
        print(f"\n⚠ {len(failures)} FAILED (mirror continued past them):")
        for op, rel, err in failures:
            print(f"  {op:7s} {rel}  — {err}")
        print("The installed copy may be stale where listed. Fix the files "
              "(reserved names may need:  del \\\\?\\<full path>  ) and rerun.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
