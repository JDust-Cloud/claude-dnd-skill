"""Tests for lookup.py — #24 (dataset skills/saves/senses restored) and
#27 (campaign-local monster supplement, campaign entry wins).

Run: pytest test_lookup.py -v
"""

import json
import os
import subprocess
import sys

import pytest


HERE = os.path.dirname(os.path.abspath(__file__))
LOOKUP = os.path.join(HERE, "lookup.py")

BOSS = {
    "name": "Goblin Boss", "index": "goblin-boss", "cr": 1, "xp": 200,
    "size": "Small", "type": "humanoid", "alignment": "neutral evil",
    "ac": 17, "hp": 21, "hp_dice": "6d6", "speed": "walk 30 ft.",
    "str": 10, "dex": 14, "con": 10, "int": 10, "wis": 8, "cha": 10,
    "skills": {"Stealth": 6}, "senses": {"darkvision": "60 ft.", "passive_perception": 9},
    "languages": "Common, Goblin",
    "description": ("Action — Multiattack: The goblin makes two attacks with its "
                    "scimitar. The second attack has disadvantage.\n\n"
                    "Action — Scimitar: Melee Weapon Attack: +4 to hit, reach 5 ft., "
                    "one target. Hit: 5 (1d6 + 2) slashing damage."),
}

SHADOW_GOBLIN = {
    "name": "Goblin", "index": "goblin", "cr": 0.25, "xp": 50,
    "size": "Small", "type": "humanoid", "alignment": "neutral evil",
    "ac": 15, "hp": 99, "hp_dice": "2d6", "speed": "walk 30 ft.",
    "str": 8, "dex": 14, "con": 10, "int": 10, "wis": 8, "cha": 8,
    "description": "Campaign-tuned goblin.",
}


@pytest.fixture()
def camp_root(tmp_path):
    camp = tmp_path / "campaigns" / "pbtso"
    camp.mkdir(parents=True)
    (camp / "supplement.json").write_text(
        json.dumps({"monsters": [BOSS, SHADOW_GOBLIN]}), encoding="utf-8")
    return tmp_path


def _run(campaign_root, *argv):
    env = dict(os.environ)
    if campaign_root is not None:
        env["DND_CAMPAIGN_ROOT"] = str(campaign_root)
    return subprocess.run([sys.executable, LOOKUP, *argv],
                          capture_output=True, encoding="utf-8", env=env)


# --- #24: dataset carries skills / saves / senses ------------------------------

def test_dataset_goblin_has_stealth_and_senses():
    """The exact playtest gap: Goblin's Stealth +6 was unrecoverable (#24)."""
    r = _run(None, "monster", "goblin", "--json")
    assert r.returncode == 0
    rec = json.loads(r.stdout)
    assert rec["skills"] == {"Stealth": 6}
    assert rec["senses"]["passive_perception"] == 9


def test_formatted_output_prints_new_fields():
    r = _run(None, "monster", "goblin")
    assert "Skills: Stealth +6" in r.stdout
    assert "Senses: darkvision 60 ft., passive perception 9" in r.stdout


def test_dataset_saves_present_where_source_has_them():
    r = _run(None, "monster", "adult red dragon", "--json")
    assert r.returncode == 0
    rec = json.loads(r.stdout)
    assert rec.get("saves"), "big dragons carry saving-throw proficiencies"
    assert "Immunities: fire" in "".join(f"{k}: {', '.join(v)}" for k, v in
                                          [("Immunities", rec.get("immunities", []))])


# --- #27: campaign supplement ---------------------------------------------------

def test_goblin_boss_missing_without_campaign(camp_root):
    r = _run(camp_root, "monster", "goblin boss")
    assert "No match" in r.stdout
    assert "--campaign" in r.stdout            # the hint names the fix


def test_goblin_boss_resolves_with_campaign(camp_root):
    r = _run(camp_root, "monster", "goblin boss", "--campaign", "pbtso")
    assert r.returncode == 0
    assert "Goblin Boss" in r.stdout
    assert "AC 17" in r.stdout
    assert "[campaign supplement]" in r.stdout  # provenance visible at the table


def test_campaign_entry_wins_over_srd(camp_root):
    r = _run(camp_root, "monster", "goblin", "--campaign", "pbtso", "--json")
    rec = json.loads(r.stdout)
    assert rec["hp"] == 99                      # campaign shadow, not SRD 7
    assert rec["_source"] == "campaign"


def test_srd_untouched_without_campaign_flag(camp_root):
    r = _run(camp_root, "monster", "goblin", "--json")
    rec = json.loads(r.stdout)
    assert rec["hp"] == 7


def test_programmatic_lookup_record_campaign_kwarg(camp_root, monkeypatch):
    monkeypatch.setenv("DND_CAMPAIGN_ROOT", str(camp_root))
    import importlib
    import paths, lookup
    importlib.reload(paths)
    importlib.reload(lookup)
    rec = lookup.lookup_record("goblin boss", category="monster", campaign="pbtso")
    assert rec and rec["ac"] == 17


def test_supplement_prose_attack_parses_for_move_oas(camp_root, monkeypatch):
    """A supplement stat block written in the SRD prose shape feeds
    move.py's OA regex — the supplement serves the whole pipe, not just
    lookup display."""
    import move
    got = move._first_melee_attack(BOSS)
    assert got == (4, "1d6+2")
