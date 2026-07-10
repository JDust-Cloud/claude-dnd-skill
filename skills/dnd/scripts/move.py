#!/usr/bin/env python3
"""
move.py — tactical grid movement for the D&D map module (v1)

Adds positional combat to the skill. Follows the same conventions as the other
scripts in this folder: a stateless CLI that takes JSON in, computes, prints
JSON out. Claude pipes state between turns; nothing persists in-process.

DESIGN (locked):
  * Space is owned by map.json (grid + walls + difficult terrain + token
    positions), separate from the combat blob (HP/AC/initiative/conditions).
    Join key between the two is the token NAME.
  * move.py is the ONLY writer of token positions. Player proposes a
    destination; this validates, resolves any opportunity attacks, and commits
    the new position to map.json — or rejects with a reason and writes nothing.
  * Opportunity-attack rolls go through combat.resolve_attack() (real import).
  * Monster attack stats come from lookup_record(name, "monster"); a per-token
    override (atk_bonus/dmg on the map token) wins if present, so homebrew
    creatures not in the SRD still work.

map.json shape:
{
  "grid":      {"width": 20, "height": 15},
  "walls":     [[3,3],[3,4]],
  "difficult": [[5,5],[5,6]],
  "tokens": {
    "Flerb": {"square": [1,1], "side": "pc",    "speed_ft": 30, "reach_ft": 5,
              "reaction_available": true, "movement_remaining_ft": 30},
    "Ogre":  {"square": [4,1], "side": "enemy", "speed_ft": 40, "reach_ft": 10,
              "reaction_available": true, "atk_bonus": 6, "dmg": "2d8+4"}
  }
}

The combat blob (from combat.py) is passed with --combat so we can read a
target's AC for OA rolls. It is NOT modified here; apply HP changes via your
existing combat/tracker flow using the events list this script returns.

CLI:
    python3 move.py --map map.json --combat combat.json --token "Flerb" --to 4,3
    python3 move.py --map map.json --token "Flerb" --to 4,3 --disengage
    python3 move.py --map map.json --token "Goblin" --to 2,2 --begin-turn --write

Output (stdout): JSON
    {"ok": true, "path": [[1,1],...], "cost": 15, "new_position": [4,3],
     "oas": [{"attacker":"Ogre","hit":true,"damage":9,"target":"Flerb"}],
     "dropped": false, "map": { ...updated map.json... }}
    {"ok": false, "reason": "too far: needs 35 ft, 30 ft remaining"}

Exit code: 0 on a valid (committed) move, 2 on a rejected move, 1 on error.
"""

from __future__ import annotations

import argparse
import heapq
import json
import os
import re
import sys

# Import sibling scripts the same way lookup.py does (folder on sys.path).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import combat as _combat  # resolve_attack(atk_bonus, target_ac, dmg, is_crit=False) -> dict
except Exception:  # exercised only outside the repo
    _combat = None

try:
    from lookup import lookup_record as _lookup_record  # (name, category) -> dict | None
except Exception:
    _lookup_record = None

SQUARE_FT = 5


# ── geometry ──────────────────────────────────────────────────────────────

def _t(sq):
    """Normalize a square to a hashable tuple."""
    return (int(sq[0]), int(sq[1]))


def chebyshev(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _neighbors(sq):
    x, y = sq
    return [(x + dx, y + dy)
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            if not (dx == 0 and dy == 0)]


class Grid:
    def __init__(self, mapdata: dict):
        g = mapdata.get("grid", {})
        self.width = int(g.get("width", 0))
        self.height = int(g.get("height", 0))
        self.walls = {_t(w) for w in mapdata.get("walls", [])}
        self.difficult = {_t(d) for d in mapdata.get("difficult", [])}

    def in_bounds(self, sq) -> bool:
        return 0 <= sq[0] < self.width and 0 <= sq[1] < self.height

    def entry_cost(self, sq) -> int:
        return SQUARE_FT * 2 if _t(sq) in self.difficult else SQUARE_FT


def _occupied_squares(tokens: dict, mover_name: str) -> set:
    out = set()
    for name, tok in tokens.items():
        if name == mover_name:
            continue
        if tok.get("square") is not None:
            out.add(_t(tok["square"]))
    return out


def cheapest_path(grid: Grid, occupied: set, start, dest):
    """Weighted Dijkstra: routes around walls/occupied, weights difficult
    terrain. Returns (path_including_start, cost) or None."""
    blocked = grid.walls | occupied
    dist = {start: 0}
    prev = {}
    pq = [(0, start)]
    while pq:
        d, cur = heapq.heappop(pq)
        if cur == dest:
            break
        if d > dist.get(cur, 1 << 30):
            continue
        for nb in _neighbors(cur):
            if not grid.in_bounds(nb) or nb in blocked:
                continue
            nd = d + grid.entry_cost(nb)
            if nd < dist.get(nb, 1 << 30):
                dist[nb] = nd
                prev[nb] = cur
                heapq.heappush(pq, (nd, nb))
    if dest not in dist:
        return None
    path = [dest]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path, dist[dest]


# ── monster attack stats (lookup with token override) ─────────────────────

# Some SRD records (e.g. Goblin) have no structured "actions" list — the
# attack is buried in prose inside "description", like:
#   "Action — Scimitar: Melee Weapon Attack: +4 to hit, reach 5 ft., one
#    target. Hit: 5 (1d6 + 2) slashing damage."
# Non-greedy .*? between "to hit" and "Hit:" binds this attack's own damage
# roll rather than a later Ranged attack's.
_MELEE_PROSE_RE = re.compile(
    r"Melee Weapon Attack:\s*([+-]?\d+)\s*to hit.*?"
    r"Hit:\s*\d+\s*\((\d+d\d+)\s*(?:([+-])\s*(\d+))?\)",
    re.IGNORECASE | re.DOTALL,
)


def _first_melee_attack(rec: dict):
    """Dig an (attack_bonus, damage_notation) out of an SRD monster record.
    Stat blocks vary between datasets, so probe a few common shapes and give
    up gracefully (return None) rather than guessing wrong."""
    if not isinstance(rec, dict):
        return None
    actions = rec.get("actions") or rec.get("action") or []
    if isinstance(actions, dict):
        actions = list(actions.values())
    for a in actions:
        if not isinstance(a, dict):
            continue
        bonus = a.get("attack_bonus", a.get("atk_bonus"))
        dmg = (a.get("damage_dice") or a.get("damage") or a.get("dmg"))
        if isinstance(dmg, dict):
            dmg = dmg.get("damage_dice") or dmg.get("dice")
        if isinstance(dmg, list) and dmg:
            first = dmg[0]
            if isinstance(first, dict):
                dmg = first.get("damage_dice") or first.get("dice")
        if bonus is not None and dmg:
            bonus = int(bonus)
            bmod = a.get("damage_bonus")
            if bmod and isinstance(dmg, str) and "+" not in dmg and "-" not in dmg:
                dmg = f"{dmg}+{int(bmod)}"
            return bonus, str(dmg)
    desc = rec.get("description")
    if isinstance(desc, str):
        m = _MELEE_PROSE_RE.search(desc)
        if m:
            bonus = int(m.group(1))
            dice, sign, mod = m.group(2), m.group(3), m.group(4)
            dmg = f"{dice}{sign}{mod}" if sign and mod else dice
            return bonus, dmg
    return None


def attacker_stats(name: str, tok: dict):
    """Return (atk_bonus, dmg_notation) for an OA. Token override wins; else
    look up the SRD stat block; else None (caller then skips the OA roll)."""
    if tok.get("atk_bonus") is not None and tok.get("dmg"):
        return int(tok["atk_bonus"]), str(tok["dmg"])
    if _lookup_record is not None:
        rec = _lookup_record(name, category="monster")
        got = _first_melee_attack(rec) if rec else None
        if got:
            return got
    return None


def _target_ac(combat_blob, name, tok):
    """AC of the moving token (the OA target). Prefer combat blob, then map
    token, then a sane default."""
    if combat_blob:
        pool = combat_blob.get("combatants", []) if isinstance(combat_blob, dict) else combat_blob
        for c in pool:
            if isinstance(c, dict) and c.get("name") == name:
                return int(c.get("ac", 10))
    if tok.get("ac") is not None:
        return int(tok["ac"])
    return 10


# ── the one mutator ───────────────────────────────────────────────────────

def resolve_move(mapdata: dict, mover_name: str, dest, combat_blob=None,
                 disengage=False, begin_turn=False):
    tokens = mapdata.setdefault("tokens", {})
    mover = tokens.get(mover_name)
    if mover is None:
        return {"ok": False, "reason": f"no token named {mover_name!r} on the map"}

    if begin_turn:
        mover["movement_remaining_ft"] = mover.get("speed_ft", 30)
        mover["reaction_available"] = True

    grid = Grid(mapdata)
    start = _t(mover["square"])
    dest = _t(dest)
    budget = mover.get("movement_remaining_ft")
    if budget is None:
        budget = mover.get("speed_ft", 30)

    if dest == start:
        return {"ok": True, "path": [list(start)], "cost": 0,
                "new_position": list(start), "oas": [], "dropped": False,
                "map": mapdata}
    if not grid.in_bounds(dest):
        return {"ok": False, "reason": "destination is off the map"}
    if dest in grid.walls:
        return {"ok": False, "reason": "destination is a wall"}

    occupied = _occupied_squares(tokens, mover_name)
    if dest in occupied:
        return {"ok": False, "reason": "destination is occupied"}

    found = cheapest_path(grid, occupied, start, dest)
    if found is None:
        return {"ok": False, "reason": "no path to destination"}
    path, cost = found
    if cost > budget:
        return {"ok": False,
                "reason": f"too far: needs {cost} ft, {budget} ft remaining",
                "path": [list(p) for p in path], "cost": cost}

    # enemies of the mover that could take an OA
    mover_side = mover.get("side", "pc")
    enemies = {n: t for n, t in tokens.items()
               if n != mover_name and t.get("side", "enemy") != mover_side
               and t.get("reaction_available", True) and t.get("square") is not None}

    oas = []
    provoked = set()

    for i in range(len(path) - 1):
        frm, to = path[i], path[i + 1]
        if disengage:
            continue
        for en, et in enemies.items():
            if en in provoked or not et.get("reaction_available", True):
                continue
            reach_sq = int(et.get("reach_ft", 5)) // SQUARE_FT
            esq = _t(et["square"])
            if chebyshev(esq, frm) <= reach_sq and chebyshev(esq, to) > reach_sq:
                stats = attacker_stats(en, et)
                provoked.add(en)
                et["reaction_available"] = False
                if stats is None or _combat is None:
                    oas.append({"attacker": en, "target": mover_name,
                                "hit": None, "damage": 0,
                                "note": "no attack stats; resolve manually"})
                    continue
                atk_bonus, dmg = stats
                r = _combat.resolve_attack(
                    atk_bonus, _target_ac(combat_blob, mover_name, mover), dmg)
                oas.append({"attacker": en, "target": mover_name,
                            "hit": r.get("hit"), "damage": r.get("damage", 0),
                            "crit": r.get("crit", False), "d20": r.get("d20")})

    # commit
    mover["square"] = list(dest)
    mover["movement_remaining_ft"] = budget - cost
    return {"ok": True, "path": [list(p) for p in path], "cost": cost,
            "new_position": list(dest), "oas": oas, "dropped": False,
            "map": mapdata}


# ── CLI ───────────────────────────────────────────────────────────────────

def _parse_square(s: str):
    parts = s.replace(" ", "").split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("--to must be X,Y (e.g. 4,3)")
    return (int(parts[0]), int(parts[1]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tactical grid movement (map module v1)")
    ap.add_argument("--map", required=True, help="path to map.json")
    ap.add_argument("--combat", help="path to combat state JSON (for target AC)")
    ap.add_argument("--token", required=True, help="name of the moving token")
    ap.add_argument("--to", required=True, type=_parse_square, help="destination square X,Y")
    ap.add_argument("--disengage", action="store_true", help="suppress opportunity attacks (costs the action)")
    ap.add_argument("--begin-turn", action="store_true", help="reset movement + reaction for a new turn before moving")
    ap.add_argument("--write", action="store_true", help="write the updated map back to --map on a valid move")
    args = ap.parse_args(argv)

    try:
        with open(args.map, encoding="utf-8") as f:
            mapdata = json.load(f)
    except Exception as e:
        print(json.dumps({"ok": False, "reason": f"could not read map: {e}"}))
        return 1

    combat_blob = None
    if args.combat:
        try:
            with open(args.combat, encoding="utf-8") as f:
                combat_blob = json.load(f)
        except Exception as e:
            print(json.dumps({"ok": False, "reason": f"could not read combat: {e}"}))
            return 1

    result = resolve_move(mapdata, args.token, args.to, combat_blob=combat_blob,
                          disengage=args.disengage, begin_turn=args.begin_turn)

    if result.get("ok") and args.write:
        try:
            with open(args.map, "w", encoding="utf-8") as f:
                json.dump(result["map"], f, indent=2)
        except Exception as e:
            result = {"ok": False, "reason": f"move valid but could not write map: {e}"}

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
