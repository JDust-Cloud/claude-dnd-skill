"""Tests for tracker.py — #29: the script's own concentration-break paths
auto-close superseded/broken concentration effects instead of orphaning
their chips (two independent repros in the pbtso-test playtest: PWT-over-Bless
naming slip, and a genuine break leaving an expired Bless behind).

Run: pytest test_tracker.py -v
"""

import json
import importlib

import pytest


@pytest.fixture()
def tracker_env(tmp_path, monkeypatch):
    """Isolated campaign root + silenced display pushes."""
    monkeypatch.setenv("DND_CAMPAIGN_ROOT", str(tmp_path))
    (tmp_path / "campaigns" / "t").mkdir(parents=True)
    import paths
    importlib.reload(paths)
    import tracker
    importlib.reload(tracker)
    monkeypatch.setattr(tracker, "_send_announce", lambda msg: None)
    monkeypatch.setattr(tracker, "_push_conditions", lambda *a, **k: None)
    return tracker, tmp_path / "campaigns" / "t" / "tracker.json"


def _effects(state_path, entity):
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return state[entity.lower()].get("effects", []), state[entity.lower()].get("concentration")


def test_concentrate_new_spell_closes_old_conc_effect(tracker_env):
    tracker, state_path = tracker_env
    tracker.cmd_effect("t", "start", "Aessa", spell="Bless", duration="10m", is_conc=True)
    tracker.cmd_concentrate("t", "Aessa", "Pass Without Trace")

    effects, conc = _effects(state_path, "Aessa")
    assert conc == "Pass Without Trace"
    assert all(e["name"].lower() != "bless" for e in effects)   # no orphan chip


def test_concentrate_break_closes_conc_effect(tracker_env):
    tracker, state_path = tracker_env
    tracker.cmd_effect("t", "start", "Aessa", spell="Bless", duration="10m", is_conc=True)
    tracker.cmd_concentrate("t", "Aessa", "break")

    effects, conc = _effects(state_path, "Aessa")
    assert conc is None
    assert effects == []


def test_effect_start_conc_supersedes_prior_conc_effect(tracker_env):
    tracker, state_path = tracker_env
    tracker.cmd_effect("t", "start", "Aessa", spell="Bless", duration="10m", is_conc=True)
    tracker.cmd_effect("t", "start", "Aessa", spell="Darkness", duration="10m", is_conc=True)

    effects, conc = _effects(state_path, "Aessa")
    assert conc == "Darkness"
    names = [e["name"] for e in effects]
    assert names == ["Darkness"]                                # Bless auto-closed


def test_non_conc_effects_survive_concentration_change(tracker_env):
    tracker, state_path = tracker_env
    tracker.cmd_effect("t", "start", "Grosh", spell="Rage", duration="10r")          # not conc
    tracker.cmd_effect("t", "start", "Grosh", spell="Shield of Faith", duration="10m", is_conc=True)
    tracker.cmd_concentrate("t", "Grosh", "break")

    effects, conc = _effects(state_path, "Grosh")
    assert conc is None
    assert [e["name"] for e in effects] == ["Rage"]             # only conc chips close


def test_same_spell_reconcentrate_keeps_its_effect(tracker_env):
    tracker, state_path = tracker_env
    tracker.cmd_effect("t", "start", "Aessa", spell="Bless", duration="10m", is_conc=True)
    tracker.cmd_concentrate("t", "Aessa", "Bless")

    effects, conc = _effects(state_path, "Aessa")
    assert conc == "Bless"
    assert [e["name"] for e in effects] == ["Bless"]
