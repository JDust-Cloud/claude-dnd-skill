"""_stdio.py — force UTF-8 stdout/stderr so Windows' cp1252 console default
can't crash on campaign text (em-dashes, curly quotes, glyphs like the combat
tracker's turn marker). Import this before any print() of user/campaign
content. Reconfiguring is a no-op on platforms that are already UTF-8.
"""
import sys

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
