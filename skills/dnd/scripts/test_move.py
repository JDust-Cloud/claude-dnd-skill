"""Tests for move.py (map module v1).

Run: pytest test_move.py -v
Place move.py alongside this file (or adjust import to the package path).

move.py imports the skill's `combat` and `lookup` modules if present; outside
the repo they're absent (so move._combat / move._lookup_record are None). These
tests inject fakes so the opportunity-attack roll and monster-stat lookup paths
are exercised deterministically.
"""

import copy
import move


# --- fakes for the skill's sibling modules ---------------------------------

class FakeCombat:
    """Stand-in for combat.py: a deterministic resolve_attack."""
    def __init__(self, hit=True, damage=7, crit=False):
        self._hit, self._dmg, self._crit = hit, damage, crit
        self.calls = []

    def resolve_attack(self, atk_bonus, target_ac, dmg_notation, is_crit=False):
        self.calls.append((atk_bonus, target_ac, dmg_notation))
        return {"d20": 15, "attack_bonus": atk_bonus, "total": 15 + atk_bonus,
                "target_ac": target_ac, "hit": self._hit, "crit": self._crit,
                "fumble": False,
                "damage": self._dmg if self._hit else None,
                "damage_rolls": [self._dmg], "damage_notation": dmg_notation}


def install_fake_combat(monkeypatch, **kw):
    fake = FakeCombat(**kw)
    monkeypatch.setattr(move, "_combat", fake)
    return fake


# --- map fixtures ----------------------------------------------------------

def base_map(**grid):
    g = {"width": 12, "height": 1}
    g.update(grid)
    return {"grid": g, "walls": [], "difficult": [], "tokens": {}}


def pc(square, side="pc", **kw):
    d = {"square": list(square), "side": side, "speed_ft": 30, "reach_ft": 5,
         "reaction_available": True}
    d.update(kw)
    return d


# --- tests -----------------------------------------------------------------

def test_over_speed_move_bounces_without_writing(monkeypatch):
    install_fake_combat(monkeypatch)
    m = base_map()
    m["tokens"]["Flerb"] = pc((0, 0))
    snapshot = copy.deepcopy(m)

    r = move.resolve_move(m, "Flerb", (7, 0))  # 7 squares = 35 ft > 30

    assert r["ok"] is False
    assert "too far" in r["reason"]
    assert m["tokens"]["Flerb"]["square"] == [0, 0]      # unchanged
    assert m == snapshot                                  # nothing mutated


def test_moving_away_from_ogre_provokes_and_resolves(monkeypatch):
    fake = install_fake_combat(monkeypatch, hit=True, damage=9)
    m = base_map()
    m["tokens"]["Flerb"] = pc((1, 0), ac=14)
    m["tokens"]["Ogre"] = pc((0, 0), side="enemy", speed_ft=40, reach_ft=5,
                             atk_bonus=6, dmg="2d8+4")

    r = move.resolve_move(m, "Flerb", (4, 0))

    assert r["ok"] is True
    assert len(r["oas"]) == 1
    oa = r["oas"][0]
    assert oa["attacker"] == "Ogre" and oa["hit"] is True and oa["damage"] == 9
    assert m["tokens"]["Ogre"]["reaction_available"] is False   # reaction spent
    assert m["tokens"]["Flerb"]["square"] == [4, 0]             # move completes
    # the OA roll saw the mover's AC and the ogre's override stats
    assert fake.calls == [(6, 14, "2d8+4")]


def test_disengage_suppresses_oa(monkeypatch):
    fake = install_fake_combat(monkeypatch)
    m = base_map()
    m["tokens"]["Flerb"] = pc((1, 0))
    m["tokens"]["Ogre"] = pc((0, 0), side="enemy", atk_bonus=6, dmg="2d8+4")

    r = move.resolve_move(m, "Flerb", (4, 0), disengage=True)

    assert r["ok"] is True
    assert r["oas"] == []
    assert m["tokens"]["Ogre"]["reaction_available"] is True     # not spent
    assert fake.calls == []                                       # no roll made


def test_difficult_terrain_doubles_cost(monkeypatch):
    install_fake_combat(monkeypatch)
    m = base_map()
    m["difficult"] = [[1, 0], [2, 0], [3, 0]]
    m["tokens"]["Flerb"] = pc((0, 0))

    # entering 3 difficult (10 each) + 1 normal (5) = 35 ft > 30 -> bounce
    r = move.resolve_move(m, "Flerb", (4, 0))

    assert r["ok"] is False
    assert m["tokens"]["Flerb"]["square"] == [0, 0]


def test_token_override_stats_used_without_lookup(monkeypatch):
    fake = install_fake_combat(monkeypatch, hit=True, damage=5)
    # ensure lookup is NOT consulted when the token carries its own stats
    monkeypatch.setattr(move, "_lookup_record",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("lookup used")))
    m = base_map()
    m["tokens"]["Flerb"] = pc((1, 0), ac=12)
    m["tokens"]["Bandit"] = pc((0, 0), side="enemy", atk_bonus=3, dmg="1d6+1")

    r = move.resolve_move(m, "Flerb", (4, 0))

    assert r["ok"] is True and r["oas"][0]["damage"] == 5
    assert fake.calls == [(3, 12, "1d6+1")]


def test_srd_lookup_fallback_when_no_override(monkeypatch):
    fake = install_fake_combat(monkeypatch, hit=True, damage=6)
    # no atk_bonus/dmg on the token -> move.py must consult lookup_record
    monster_rec = {"name": "Goblin",
                   "actions": [{"name": "Scimitar", "attack_bonus": 4,
                                "damage_dice": "1d6", "damage_bonus": 2}]}
    monkeypatch.setattr(move, "_lookup_record", lambda name, category=None: monster_rec)
    m = base_map()
    m["tokens"]["Flerb"] = pc((1, 0), ac=13)
    m["tokens"]["Goblin"] = pc((0, 0), side="enemy")   # bare, no stats

    r = move.resolve_move(m, "Flerb", (4, 0))

    assert r["ok"] is True
    assert r["oas"][0]["damage"] == 6
    # dug attack_bonus=4 and stitched damage_dice+bonus into "1d6+2"
    assert fake.calls == [(4, 13, "1d6+2")]


def test_first_melee_attack_digger():
    rec = {"actions": [{"name": "Bite", "attack_bonus": 5,
                        "damage_dice": "2d6", "damage_bonus": 3}]}
    assert move._first_melee_attack(rec) == (5, "2d6+3")
    assert move._first_melee_attack({"actions": []}) is None
    assert move._first_melee_attack({}) is None


def test_wall_and_occupied_blocking(monkeypatch):
    install_fake_combat(monkeypatch)
    m = base_map(width=5, height=5)
    m["walls"] = [[2, 0]]
    m["tokens"]["Flerb"] = pc((0, 0))
    m["tokens"]["Wolf"] = pc((4, 0), side="enemy")

    assert move.resolve_move(m, "Flerb", (2, 0))["ok"] is False   # into a wall
    assert move.resolve_move(m, "Flerb", (4, 0))["ok"] is False   # onto a token


def test_begin_turn_refreshes_movement_and_reaction(monkeypatch):
    install_fake_combat(monkeypatch)
    m = base_map()
    # spent token: no movement left, reaction gone
    m["tokens"]["Flerb"] = pc((0, 0), movement_remaining_ft=0, reaction_available=False)

    r = move.resolve_move(m, "Flerb", (3, 0), begin_turn=True)  # 15 ft after refresh

    assert r["ok"] is True
    assert m["tokens"]["Flerb"]["reaction_available"] is True
    assert m["tokens"]["Flerb"]["movement_remaining_ft"] == 15   # 30 - 15
