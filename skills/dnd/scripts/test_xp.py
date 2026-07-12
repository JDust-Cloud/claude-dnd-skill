"""Tests for xp.py — #31: the award is RAW XP of the defeated ÷ party (DMG
rule); the group-size multiplier rates difficulty ONLY, on the encounter as
built. The playtest paid 3 goblins at 75/head instead of 37 — doubled
progression at every multi-monster fight.

Run: pytest test_xp.py -v
"""

import os
import re
import subprocess
import sys

import pytest


HERE = os.path.dirname(os.path.abspath(__file__))
XP = os.path.join(HERE, "xp.py")

CHAR_TEMPLATE = """# {name}

**Level:** 3
**XP:** 900 / 2700

## Resources
Hit Dice: 3/3 (d8)
"""


@pytest.fixture()
def campaign(tmp_path):
    chars = tmp_path / "campaigns" / "xptest" / "characters"
    chars.mkdir(parents=True)
    for n in ("aldric", "mira", "tam", "vex"):
        (chars / f"{n}.md").write_text(CHAR_TEMPLATE.format(name=n.title()),
                                       encoding="utf-8")
    return tmp_path


def _run(campaign_root, *argv):
    env = dict(os.environ, DND_CAMPAIGN_ROOT=str(campaign_root))
    return subprocess.run([sys.executable, XP, *argv],
                          capture_output=True, encoding="utf-8", env=env)


def _char_xp(campaign_root, name):
    text = (campaign_root / "campaigns" / "xptest" / "characters" / f"{name}.md"
            ).read_text(encoding="utf-8")
    return int(re.search(r"\*\*XP:\*\*\s*(\d+)", text).group(1))


def test_award_is_raw_xp_divided_by_party(campaign):
    """3 goblins (CR 1/4, 50 raw each) vs a party of 4 → 150 raw ÷ 4 = 37 each.
    The old code paid the ADJUSTED 300 ÷ 4 = 75 — the exact #31 repro."""
    r = _run(campaign, "award", "--campaign", "xptest",
             "--characters", "Aldric,Mira,Tam,Vex",
             "--monsters", "goblin:1/4:3")
    assert r.returncode == 0
    for n in ("aldric", "mira", "tam", "vex"):
        assert _char_xp(campaign, n) == 900 + 37
    assert "37" in r.stdout
    assert "75" not in r.stdout.replace("Raw", "")  # the wrong number is gone


def test_difficulty_is_rated_on_adjusted_as_built(campaign):
    """The difficulty label still comes from ADJUSTED XP (raw × multiplier)."""
    r = _run(campaign, "award", "--campaign", "xptest",
             "--characters", "Aldric,Mira,Tam,Vex",
             "--monsters", "goblin:1/4:4")
    assert r.returncode == 0
    # 4 goblins: raw 200, ×2 = adjusted 400 → 100/head vs L3 thresholds
    # (75/150/225/400) ⇒ EASY — the label reads the ADJUSTED number
    assert "EASY" in r.stdout
    assert "400" in r.stdout
    # award stays raw: 200 ÷ 4 = 50
    assert _char_xp(campaign, "aldric") == 950


def test_encounter_flag_rates_difficulty_on_fight_as_built(campaign):
    """Partial defeat: 2 goblins killed out of a 4-goblin + boss ambush — the
    award pays what was DEFEATED, the label rates what was FACED."""
    r = _run(campaign, "award", "--campaign", "xptest",
             "--characters", "Aldric,Mira,Tam,Vex",
             "--monsters", "goblin:1/4:2",
             "--encounter", "goblin:1/4:4,goblin boss:1:1")
    assert r.returncode == 0
    # award: raw 100 ÷ 4 = 25 each
    assert _char_xp(campaign, "aldric") == 925
    # as built: raw 400, 5 monsters ×2 = adjusted 800 → 200/head vs L3
    # thresholds (75/150/225/400) ⇒ MEDIUM — rated on what was FACED
    assert "MEDIUM" in r.stdout
    assert "--encounter" in r.stdout


def test_calc_shows_raw_award_and_adjusted_difficulty():
    r = subprocess.run(
        [sys.executable, XP, "calc", "--level", "3", "--players", "4",
         "--monsters", "goblin:1/4:3"],
        capture_output=True, encoding="utf-8")
    assert r.returncode == 0
    assert "37" in r.stdout            # award per player from RAW
    assert "300" in r.stdout           # adjusted drives the label only
    assert "Difficulty" in r.stdout


def test_difficulty_rated_award_path_unchanged(campaign):
    """Difficulty-rated awards (no monster list) still pay the threshold value."""
    r = _run(campaign, "award", "--campaign", "xptest",
             "--characters", "Aldric,Mira,Tam,Vex",
             "--difficulty", "hard", "--type", "noncombat")
    assert r.returncode == 0
    assert _char_xp(campaign, "aldric") == 900 + 225   # L3 hard threshold
