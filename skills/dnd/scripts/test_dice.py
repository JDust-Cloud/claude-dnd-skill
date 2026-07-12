"""Tests for dice.py — compound expressions (#35) and CLI failure discipline.

The Bless pattern (d20+X+NdY), 5e's most common buff, must be expressible in
one §1-pipe call; a bad notation must be a named error, never a traceback.

Run: pytest test_dice.py -v
"""

import subprocess
import sys
import os

import pytest

import dice


HERE = os.path.dirname(os.path.abspath(__file__))
DICE = os.path.join(HERE, "dice.py")


def _run(*argv):
    env = dict(os.environ, DND_DICE_PHYSICAL="0")
    return subprocess.run([sys.executable, DICE, *argv],
                          capture_output=True, encoding="utf-8", env=env)


# --- parser -------------------------------------------------------------------

def test_parse_compound_bless_pattern():
    tokens = dice.parse_compound("d20+5+1d4")
    assert tokens == [("dice", 1, 1, 20), ("mod", 5), ("dice", 1, 1, 4)]


def test_parse_compound_negative_group_bane():
    tokens = dice.parse_compound("d20+7-1d4")
    assert tokens == [("dice", 1, 1, 20), ("mod", 7), ("dice", -1, 1, 4)]


def test_parse_compound_rejects_garbage():
    with pytest.raises(ValueError):
        dice.parse_compound("banana")
    with pytest.raises(ValueError):
        dice.parse_compound("2+3")          # no dice term
    with pytest.raises(ValueError):
        dice.parse_compound("d20+5+")       # trailing junk


def test_legacy_notations_still_use_legacy_parser():
    """Single-group forms keep their exact pre-#35 parse (and thus output)."""
    assert dice.parse_notation("d20+5")[0:3] == (1, 20, 5)
    assert dice.parse_notation("4d6kh3")[3:5] == ("kh", 3)
    adv = dice.parse_notation("d20 adv")
    assert adv[5] is True


# --- rolling ------------------------------------------------------------------

def test_roll_compound_total_and_order(monkeypatch):
    seq = iter([13, 3])
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(seq))
    res = dice.roll_compound(dice.parse_compound("d20+5+1d4"))
    assert res["total"] == 13 + 5 + 3
    line = dice._fmt_compound(res)
    assert line == "Rolls: d20(13) + 5 + d4(3) = 21"


def test_roll_compound_advantage_first_die_only(monkeypatch):
    seq = iter([9, 14, 3])   # d20 twice (adv), then the 1d4 exactly once
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(seq))
    res = dice.roll_compound(dice.parse_compound("d20+5+1d4"), adv=True)
    assert res["first_pair"] is not None
    kept, other = res["first_pair"]
    assert kept == [14] and other == [9]
    assert res["total"] == 14 + 5 + 3


def test_roll_compound_disadvantage(monkeypatch):
    seq = iter([9, 14, 3])
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(seq))
    res = dice.roll_compound(dice.parse_compound("d20+5+1d4"), dis=True)
    kept, other = res["first_pair"]
    assert kept == [9] and other == [14]


def test_roll_compound_nat20_flag(monkeypatch):
    seq = iter([20, 1])
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(seq))
    res = dice.roll_compound(dice.parse_compound("d20+5+1d4"))
    assert "CRITICAL" in dice._fmt_compound(res)


def test_negative_group_subtracts(monkeypatch):
    seq = iter([13, 2])
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(seq))
    res = dice.roll_compound(dice.parse_compound("d20+7-1d4"))
    assert res["total"] == 13 + 7 - 2


# --- CLI ----------------------------------------------------------------------

def test_cli_compound_runs_clean():
    r = _run("d20+5+1d4")
    assert r.returncode == 0
    assert r.stdout.startswith("Rolls: d20(")
    assert "= " in r.stdout


def test_cli_compound_silent_prints_total_only():
    r = _run("d20+5+1d4", "--silent")
    assert r.returncode == 0
    total = int(r.stdout.strip())
    assert 1 + 5 + 1 <= total <= 20 + 5 + 4


def test_cli_compound_adv_shows_both_first_dice():
    r = _run("d20+5+1d4", "adv")
    assert r.returncode == 0
    assert "[ADV] first die:" in r.stdout


def test_cli_bad_notation_named_error_not_traceback():
    r = _run("garbage+x")
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert "dice.py:" in r.stderr and "Supported:" in r.stderr


def test_cli_legacy_single_group_output_unchanged():
    r = _run("2d6+3")
    assert r.returncode == 0
    assert r.stdout.startswith("Rolls: [")   # exact pre-#35 shape
