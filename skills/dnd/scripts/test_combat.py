"""Tests for combat.py — the pbtso-test ledger fixes.

Covers:
  #28  init preserves a caller-supplied max_hp (wounded-PC regression)
  #36  adv/dis flags + real arg parser (--help exits 0, missing args named)
  #37  --crit forces a critical on a hit the die didn't crit; nat-1 still misses
  #23  damage line substitutes the real modifier and notation (no "+ mod",
       no mangled "d6dmg")
  #35  compound damage notation rides resolve_attack (crit doubles all groups)

Run: pytest test_combat.py -v
"""

import json
import subprocess
import sys
import os

import combat


HERE = os.path.dirname(os.path.abspath(__file__))
COMBAT = os.path.join(HERE, "combat.py")


def _run(*argv):
    return subprocess.run([sys.executable, COMBAT, *argv],
                          capture_output=True, encoding="utf-8")


# --- #28: init max_hp preservation ------------------------------------------

def test_init_preserves_supplied_max_hp_wounded_pc():
    """Wounded Rennet enters at hp 5 / max_hp 12 — the tracker and STATE_JSON
    must carry 5/12, not 5/5 (healing cap + massive-damage threshold hang on
    this)."""
    combatants = json.dumps([
        {"name": "Rennet", "dex_mod": 1, "hp": 5, "ac": 14, "type": "pc", "max_hp": 12},
        {"name": "Goblin", "dex_mod": 2, "hp": 7, "ac": 15, "type": "npc"},
    ])
    r = _run("init", combatants)
    assert r.returncode == 0
    state_line = [l for l in r.stdout.splitlines() if l.startswith("STATE_JSON:")][0]
    state = json.loads(state_line.split("STATE_JSON:", 1)[1])
    rennet = next(c for c in state if c["name"] == "Rennet")
    goblin = next(c for c in state if c["name"] == "Goblin")
    assert rennet["hp"] == 5 and rennet["max_hp"] == 12
    assert goblin["max_hp"] == 7          # unsupplied still defaults to hp
    assert "5/12" in r.stdout             # tracker table shows the true max


# --- #36: adv/dis + argparse -------------------------------------------------

def test_attack_help_exits_zero_with_usage():
    r = _run("attack", "--help")
    assert r.returncode == 0
    assert "usage" in r.stdout.lower()
    assert "--adv" in r.stdout and "--crit" in r.stdout


def test_top_level_help_exits_zero():
    r = _run("--help")
    assert r.returncode == 0
    assert "usage" in r.stdout.lower()


def test_attack_missing_arg_is_named_error_not_traceback():
    r = _run("attack", "--atk", "4")
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert "--ac" in r.stderr or "--dmg" in r.stderr


def test_advantage_keeps_higher_of_two_d20s(monkeypatch):
    seq = iter([4, 17, 3])  # two d20s, then damage die
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(seq))
    r = combat.resolve_attack(4, 15, "1d6+2", advantage=True)
    assert r["d20_rolls"] == [4, 17]
    assert r["d20"] == 17 and r["mode"] == "advantage"
    assert r["hit"] is True


def test_disadvantage_keeps_lower(monkeypatch):
    seq = iter([4, 17])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(seq))
    r = combat.resolve_attack(4, 15, "1d6+2", disadvantage=True)
    assert r["d20"] == 4 and r["mode"] == "disadvantage"
    assert r["hit"] is False


def test_adv_plus_dis_cancel_to_straight(monkeypatch):
    seq = iter([10, 3])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(seq))
    r = combat.resolve_attack(4, 12, "1d6+2", advantage=True, disadvantage=True)
    assert r["mode"] == "straight"
    assert r["d20_rolls"] == [10]         # one die — 5e RAW cancellation


def test_adv_attack_line_shows_both_rolls(monkeypatch):
    seq = iter([4, 17, 3])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(seq))
    r = combat.resolve_attack(4, 15, "1d6+2", advantage=True)
    line = combat.format_attack(r).splitlines()[0]
    assert "ADV" in line and "4" in line and "17" in line


# --- #37: forced crit ---------------------------------------------------------

def test_forced_crit_doubles_dice_on_hit(monkeypatch):
    seq = iter([12, 6, 5])  # d20, then 1d6 rolled twice (crit doubling)
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(seq))
    r = combat.resolve_attack(10, 5, "1d6+2", is_crit=True)
    assert r["hit"] and r["crit"] and r["forced_crit"]
    assert r["damage_rolls"] == [6, 5]
    assert r["damage"] == 13              # 6 + 5 + 2 — modifier NOT doubled
    assert "forced" in combat.format_attack(r)


def test_forced_crit_does_not_rescue_a_miss(monkeypatch):
    seq = iter([3])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(seq))
    r = combat.resolve_attack(0, 18, "1d6+2", is_crit=True)
    assert not r["hit"] and not r["crit"]


def test_nat_1_still_auto_misses_under_forced_crit(monkeypatch):
    seq = iter([1])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(seq))
    r = combat.resolve_attack(30, 5, "1d6+2", is_crit=True)
    assert not r["hit"] and r["fumble"]


def test_nat_20_crit_still_automatic(monkeypatch):
    seq = iter([20, 4, 2])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(seq))
    r = combat.resolve_attack(0, 25, "1d6+2", is_crit=False)
    assert r["hit"] and r["crit"] and not r["forced_crit"]


# --- #23: damage-line substitution --------------------------------------------

def test_damage_line_substitutes_modifier_and_notation(monkeypatch):
    seq = iter([12, 6])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(seq))
    r = combat.resolve_attack(4, 10, "1d6+2")
    dmg_line = [l for l in combat.format_attack(r).splitlines()
                if l.startswith("Damage:")][0]
    assert dmg_line == "Damage: [6] + 2 = 8 (1d6+2)"
    assert "mod" not in dmg_line          # the literal words never print
    assert "d6dmg" not in dmg_line        # the mangled suffix never prints


def test_damage_line_negative_modifier(monkeypatch):
    seq = iter([12, 6])
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(seq))
    r = combat.resolve_attack(4, 10, "1d6-1")
    dmg_line = [l for l in combat.format_attack(r).splitlines()
                if l.startswith("Damage:")][0]
    assert "= 5 (1d6-1)" in dmg_line and " - 1 " in dmg_line


# --- #35: compound damage through the attack pipe ------------------------------

def test_compound_damage_resolves(monkeypatch):
    seq = iter([10, 3, 5, 2])   # d20, 2d6, 1d4
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(seq))
    r = combat.resolve_attack(30, 5, "2d6+1d4+3")
    assert r["hit"] and not r["crit"]
    assert r["damage_rolls"] == [3, 5, 2]
    assert r["damage"] == 3 + 5 + 2 + 3


def test_compound_damage_crit_doubles_every_group(monkeypatch):
    seq = iter([12, 3, 4, 5, 6, 2, 1])  # d20, 2d6 crit->4 dice, 1d4 crit->2 dice
    monkeypatch.setattr(combat.random, "randint", lambda a, b: next(seq))
    r = combat.resolve_attack(10, 5, "2d6+1d4+3", is_crit=True)
    assert r["damage_rolls"] == [3, 4, 5, 6, 2, 1]
    assert r["damage"] == 3 + 4 + 5 + 6 + 2 + 1 + 3


def test_bad_damage_notation_is_named_cli_error():
    """Notation is validated BEFORE the d20 is cast — a bad --dmg fails with a
    named error even on a would-be miss (a nat-1 in the first Windows run
    exposed hit-only validation)."""
    r = _run("attack", "--atk", "4", "--ac", "1", "--dmg", "banana")
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert "banana" in r.stderr or "--dmg" in r.stderr


def test_bad_damage_notation_rejected_in_api_before_rolling(monkeypatch):
    def no_dice(a, b):
        raise AssertionError("no die should be cast for an invalid notation")
    monkeypatch.setattr(combat.random, "randint", no_dice)
    import pytest as _pytest
    with _pytest.raises(ValueError):
        combat.resolve_attack(4, 15, "banana")
