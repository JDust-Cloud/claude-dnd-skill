# CLAUDE.md — AI Dungeon Master build (map module → Foundry visual layer)

> Auto-loaded by Claude Code at session start. This repo is a **fork of `neuralinitiative/claude-dnd-skill`** (AGPL) that we're extending with a tactical battle map. This file orients you to the CURRENT build; the full living plan is in Notion (link at the bottom). If this file and Notion disagree, Notion's START HERE block wins — then update this file to match.
>
> If the upstream repo already ships a CLAUDE.md, APPEND this section rather than overwriting. This file is dev orientation and should be excluded from any upstream PR.

## What this repo is
An unofficial D&D 5e Dungeon Master skill/plugin for Claude Code: persistent markdown campaigns, full 5e mechanics, and an optional Flask + Server-Sent-Events display companion (typewriter narration on a TV, players act from phones). We forked it to add the one thing it lacks: a **tactical battle map with tokens and movement**.

## CURRENT DIRECTION (pivoted 2026-07-08) — Foundry VTT is the map renderer
The tactical map is rendered by **Foundry VTT**, driven by our engine over a self-hosted REST relay bridge — **NOT** a bespoke canvas panel in the Flask display. A graph-paper canvas won't clear the visual bar (painted-map / miniature quality); Foundry gives lighting, fog, aligned art, and animations on day one.
- **SUPERSEDED — do NOT build:** the map-canvas panel in the skill's display, and the SSE map message shapes (`map_state` / `token_update` / `oa_event`). (In Notion, "Map Module — v1 Spec" and "Map Panel — Claude Design Brief" are superseded by "Visual Layer Build".)
- **The Flask/SSE display STAYS** for narration, dice, stats, and phone input — it is no longer a map renderer.
- **Load-bearing caveat — RESOLVED ✅ (2026-07-08/09):** our Python engine CAN drive Foundry — Phase 0 proved it end-to-end. `move_test.py` moved a token via `POST /move-token` on the self-hosted relay at `localhost:3010`, from plain stdlib Python. Foundry is purchased (v14.364). Full working setup + endpoints + gotchas: `PHASE0_RESULTS.md` (Google Drive, AI Dungeon Master folder).

## Core invariant (do not violate)
The app owns truth; the LLM only narrates. Deterministic code resolves all mechanics. `move.py` is the ONLY writer of token positions — Claude proposes a destination, the script validates and commits or rejects with a reason. Engine = rules authority; Foundry = display only (engine→Foundry push; a player drag is at most a *proposed* move the engine validates). Never let the model write game state directly.

## Architecture (decided; matches the code)
- **Space** lives in `map.json` (grid, walls, difficult terrain, `{name:[x,y]}` positions), separate from the combat blob (HP/AC/initiative/conditions). Join key = token name.
- These scripts are **stateless CLIs**: JSON in → compute → JSON out. State is piped between turns; nothing persists in-process. `move.py` follows that pattern.
- **Two seams** (confirmed by reading the code):
  - Attack roll → `combat.resolve_attack(atk_bonus, target_ac, dmg_notation, is_crit=False) -> dict` (keys: hit, crit, damage, d20). Direct import.
  - Monster stats → `lookup.lookup_record(name, category="monster") -> dict | None`. A per-token `atk_bonus`/`dmg` override wins; else SRD lookup; else skip the roll. `move._first_melee_attack()` digs attack + damage out of the stat block.
- **The bridge (`foundry_sync.py`, Phase 1):** after each engine state change (position, HP), push the *result* into Foundry via the relay. `move.py`'s movement + OA logic survives the pivot; its role may narrow depending on what Foundry's own movement/OA modules give for free (resolved in Phase 1).

## Status / next task
- `move.py` + `test_move.py` written, **9 pytest cases green out-of-repo**. Plus `test_map.json` (bare-Goblin fixture). All three **staged in Google Drive** (AI Dungeon Master folder), pending drop into the repo.
- **Engine (do first — survives the pivot, independent of Foundry):**
  1. Place `move.py`, `test_move.py`, `test_map.json` in `skills/dnd/scripts/`.
  2. `pytest skills/dnd/scripts/test_move.py -v` → confirm 9 pass in place.
  3. `python skills/dnd/scripts/move.py --map test_map.json --token "Flerb" --to 5,1` → the Goblin should provoke an OA firing the real SRD lookup. **Known fix:** the goblin's attack lives in the free-text `description` field, NOT a structured attack array — so `_first_melee_attack` must regex-parse the prose for to-hit (`+4`) and damage (`1d6+2`). Write/verify that parse.
  4. Commit to `map-module`; then delete the Drive copies (code lives in git only).
- **Foundry Phase 0 — ✅ DONE (2026-07-08/09):** Docker relay (ThreeHats `foundryvtt-rest-api-relay`, `localhost:3010`) + Foundry v14.364 + dnd5e 5.3.3 + `foundry-rest-api` module; world paired via a one-time code (relay Connections → module Enter Code — NOT the Pair button, NOT the API key). Stage A (read `/clients`) and Stage B (move a token via `POST /move-token`) BOTH PASSED, confirmed from plain Python. clientId `fvtt_d287d626b40874b9`. Runbook: `PHASE0_RESULTS.md`.
- **Then (Phase 1+):** `foundry_sync.py` bridge → one full combat in sync on the TV → import pre-walled maps + fog/lighting/effects (Phase 2) → optional ComfyUI art on the 3080 (Phase 3).

## Build order (non-negotiable)
Engine before bridge before beauty. Get `move.py` green and correct against the real dataset first; prove the Foundry pipe (Phase 0) before spending anything; the map only renders state the engine already produced.

## Content side-thread (private; keep OUT of this repo)
A personal Dragonlance (*Shadow of the Dragon Queen*) module is being built via the engine's import path (paste book text → markdown → `import_campaign.py`). **Never commit book text to this fork.** Campaign/character data live under `DND_CAMPAIGN_ROOT` (default `~/.claude/dnd`) — OUTSIDE the repo tree; git never sees it. Don't save raw book markdown inside the repo folder and don't point the data root into the repo. Verify: `python skills/dnd/scripts/path_config.py show`.

## Full plan (source of truth)
Notion hub: https://app.notion.com/p/397cefb058ee8186ad03c809f2ec7088 — read the **START HERE** block, then **Visual Layer Build — Foundry front-end (CURRENT DIRECTION)**, **Settled Questions & How It Runs**, and **Codebase Map**. (Prior Art & Build-On Target, Build Spec, and Tooling & Workflow give background; Map Module — v1 Spec and Map Panel — Claude Design Brief are SUPERSEDED.)
