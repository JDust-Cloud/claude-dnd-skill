"""_stdio.py — force UTF-8 stdin/stdout/stderr so Windows' cp1252 console
default can't crash on campaign text (em-dashes, curly quotes, glyphs like the
combat tracker's turn marker) — or, worse, silently MISREAD it: a bare
sys.stdin.read() under cp1252 decodes piped UTF-8 em-dashes into three-glyph
mojibake (defect #3's root — corrupted narration persisted into session tails
through send.py). Import this before any stdin read or any print() of
user/campaign content. Reconfiguring is a no-op on already-UTF-8 platforms.
"""
import sys

for _stream_name in ("stdin", "stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
