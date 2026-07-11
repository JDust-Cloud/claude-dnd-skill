"""Regression tests for defect #3 — mojibake on the stdin→send path.

Root cause: on Windows, sys.stdin defaults to the console code page (cp1252),
so piped UTF-8 em-dashes decode as three-glyph mojibake BEFORE any of our
explicit-encoding file IO runs; the wrong-but-valid string then persists into
text_log.json / session_tail.json. The class fix reconfigures stdin alongside
stdout/stderr (scripts/_stdio.py; mirrored inline in display/send.py).

These tests simulate the Windows condition with PYTHONIOENCODING=cp1252, which
sets the broken default at interpreter start; the reconfigure must repair it.
"""
import os
import pathlib
import subprocess
import sys

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
DISPLAY_DIR = SCRIPTS_DIR.parent / "display"

EM_DASH_UTF8 = "The blade sweeps wide — a clean miss.".encode("utf-8")


def _run_roundtrip(preamble: str) -> bytes:
    """Pipe UTF-8 bytes through a cp1252-defaulted interpreter and return
    what the child actually decoded (re-encoded as UTF-8 bytes)."""
    code = (
        preamble
        + "import sys\n"
        + "data = sys.stdin.read()\n"
        + "sys.stdout.buffer.write(data.encode('utf-8'))\n"
    )
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    proc = subprocess.run(
        [sys.executable, "-c", code],
        input=EM_DASH_UTF8,
        capture_output=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return proc.stdout


def test_cp1252_stdin_corrupts_without_fix():
    """Sanity: the failure mode is real — without _stdio, cp1252 stdin mangles
    the em-dash into mojibake. If this ever starts passing clean, the platform
    default changed and the guard below is redundant rather than load-bearing."""
    out = _run_roundtrip("")
    assert EM_DASH_UTF8 not in out or b"\xc3\xa2" not in out  # tolerate future-clean platforms
    if EM_DASH_UTF8 not in out:
        assert b"\xc3\xa2\xe2\x82\xac" in out  # 'â€' — the observed live corruption


def test_stdio_import_repairs_stdin():
    """The class fix: importing _stdio makes the same pipe round-trip intact."""
    preamble = (
        f"import sys; sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
        "import _stdio\n"
    )
    out = _run_roundtrip(preamble)
    assert out == EM_DASH_UTF8, f"em-dash did not survive: {out!r}"


def test_send_py_reconfigures_stdin_before_reading():
    """Static guard in the spirit of test_encoding_hygiene: display/send.py
    (which cannot import scripts/_stdio) must carry the inline reconfigure,
    and it must appear BEFORE the first sys.stdin.read()."""
    src = (DISPLAY_DIR / "send.py").read_text(encoding="utf-8")
    code_lines = [
        (n, ln) for n, ln in enumerate(src.splitlines(), 1)
        if not ln.lstrip().startswith("#")
    ]
    fix_line = next((n for n, ln in code_lines if "reconfigure(" in ln), None)
    read_line = next((n for n, ln in code_lines if "sys.stdin.read()" in ln), None)
    assert fix_line, "send.py lost its stdin UTF-8 reconfigure (defect #3 regression)"
    assert read_line is None or fix_line < read_line, (
        "send.py reads stdin before reconfiguring it to UTF-8"
    )


def test_stdio_covers_stdin_stream():
    """scripts/_stdio.py must keep stdin in its stream list."""
    src = (SCRIPTS_DIR / "_stdio.py").read_text(encoding="utf-8")
    assert '"stdin"' in src, "_stdio.py no longer reconfigures stdin"
