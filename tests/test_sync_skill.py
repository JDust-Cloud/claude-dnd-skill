"""Tests for sync_skill.py failure discipline (2026-07-12 hardening).

The 7/11 close-out crashed mid-sweep: a Windows reserved-name file (`nul`)
in the installed dir raised PermissionError and aborted the ENTIRE mirror.
The mirror must now continue past per-file failures, print a failure
summary, and exit non-zero — never silently, never fatally.
"""

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sync_skill


@pytest.fixture()
def mirror(tmp_path, monkeypatch):
    src = tmp_path / "repo" / "skills" / "dnd"
    dst = tmp_path / "installed"
    src.mkdir(parents=True)
    dst.mkdir(parents=True)
    monkeypatch.setattr(sync_skill, "SOURCE", src)
    monkeypatch.setattr(sync_skill, "DEST", dst)
    return src, dst


def test_clean_mirror_copies_and_exits_zero(mirror, capsys):
    src, dst = mirror
    (src / "a.py").write_text("A", encoding="utf-8")
    (src / "sub").mkdir()
    (src / "sub" / "b.py").write_text("B", encoding="utf-8")

    rc = sync_skill.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert (dst / "a.py").read_text(encoding="utf-8") == "A"
    assert (dst / "sub" / "b.py").exists()
    assert "2 copied" in out


def test_unreadable_file_does_not_abort_the_mirror(mirror, capsys, monkeypatch):
    """The `nul` shape (7/11 crash): a file present in BOTH trees whose read
    raises during the hash compare — every OTHER file must still be
    compared/copied, and the run must end with a summary + rc 1."""
    src, dst = mirror
    (src / "aaa_bad.py").write_text("X", encoding="utf-8")
    (dst / "aaa_bad.py").write_text("stale", encoding="utf-8")   # forces the hash compare
    (src / "zzz_good.py").write_text("G", encoding="utf-8")

    real_read = sync_skill._read_bytes

    def poisoned(path):
        if path.name == "aaa_bad.py":
            raise PermissionError(13, "Permission denied", str(path))
        return real_read(path)

    monkeypatch.setattr(sync_skill, "_read_bytes", poisoned)
    rc = sync_skill.main([])
    out = capsys.readouterr().out

    assert rc == 1
    assert (dst / "zzz_good.py").exists()          # the sweep continued
    assert "FAILED" in out and "aaa_bad.py" in out  # and named the casualty


def test_undeletable_stale_file_is_reported_not_fatal(mirror, capsys, monkeypatch):
    src, dst = mirror
    (src / "keep.py").write_text("K", encoding="utf-8")
    (dst / "stale_locked.py").write_text("S", encoding="utf-8")
    (dst / "stale_ok.py").write_text("S2", encoding="utf-8")

    def poisoned_delete(path):
        if path.name == "stale_locked.py":
            raise PermissionError(13, "Permission denied", str(path))
        path.unlink()

    monkeypatch.setattr(sync_skill, "_delete", poisoned_delete)
    rc = sync_skill.main([])
    out = capsys.readouterr().out

    assert rc == 1
    assert (dst / "keep.py").exists()
    assert not (dst / "stale_ok.py").exists()      # other delete still ran
    assert "stale_locked.py" in out


def test_dry_run_touches_nothing(mirror, capsys):
    src, dst = mirror
    (src / "a.py").write_text("A", encoding="utf-8")
    rc = sync_skill.main(["--dry-run"])
    assert rc == 0
    assert not (dst / "a.py").exists()
    assert "[dry-run]" in capsys.readouterr().out


def test_runtime_files_still_preserved(mirror):
    src, dst = mirror
    (src / "display").mkdir()
    (src / "display" / "send.py").write_text("S", encoding="utf-8")
    (dst / "display").mkdir()
    (dst / "display" / "app.log").write_text("runtime", encoding="utf-8")

    rc = sync_skill.main([])
    assert rc == 0
    assert (dst / "display" / "app.log").read_text(encoding="utf-8") == "runtime"
