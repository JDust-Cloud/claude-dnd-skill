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

## Status / next task (refreshed 2026-07-12)
- **Engine LANDED and WIRED.** `move.py` (+9 tests) has lived in `skills/dnd/scripts/` since 7/10 — the old "staged in Drive" note is history. The wiring spec `SKILL-wiring.md` (table law: dice pipe, tactical frame + move pipe, zones, beats, player agency, narration register, ledger) shipped 7/11 and is loaded at `/dnd load` with the other booklets. Stage 2 CLOSED; latency gate cleared (play config = Sonnet + `/effort high`, local command `/dnd`).
- **PBTSO ch.1 playtest COMPLETE (7/11 night)** — 38-defect ledger at `campaigns/pbtso-test/defects.md` (numbering canon). The 2026-07-12 build session fixed the engine items: #28 init max_hp, #35/#36/#37 §1-pipe flags (compound dice, adv/dis, forced crit, real arg parsing), #31 award-raw split, #29 concentrate auto-close, #23 damage line, #24 dataset skills/saves/senses, #27 campaign supplement (`lookup.py --campaign`, populated at import), plus law lines §2-d/§4-b/§6-b and a hardened `sync_skill.py`.
- **Foundry Phase 0 — ✅ DONE (2026-07-08/09):** Docker relay (ThreeHats `foundryvtt-rest-api-relay`, `localhost:3010`) + Foundry v14.364 + dnd5e 5.3.3 + `foundry-rest-api` module; world paired via a one-time code (relay Connections → module Enter Code — NOT the Pair button, NOT the API key). Stage A (read `/clients`) and Stage B (move a token via `POST /move-token`) BOTH PASSED, confirmed from plain Python. clientId `fvtt_d287d626b40874b9`. Runbook: `PHASE0_RESULTS.md` (Drive, AI Dungeon Master folder). **Relay/`foundry_sync.py` stays PARKED until Stage 5** — manual GM-window drags mirror the engine for the wife game (that IS the Stage-4 design, not a stopgap).
- **Next:** ch.1 MAP PREP via the proven Cowork→Foundry browser path (MAD pack scenes are walled/lit; the pack ships maps NOT monsters — build goblins ×6, goblin boss, wolves ×3, Klarg, Yeemik as display-minimum actors + tokens, place Tbone, fog reset) → voiced dress rehearsal (Stage-3 gate; TTS needs the pay-as-you-go key flip first) → game night next weekend.
- **Cowork environment facts:** the desktop folder bridge cannot mount anything under `C:\Users\zarat\.claude` — campaign-root files reach cloud sessions via chat attach or the hub's summaries only; never ask to Add-folder it. Cloud sessions CAN `git clone` the public fork for read/audit; writes go through the mounted repo folder, git stays in Jeff's PowerShell.

## Build order (non-negotiable)
Engine before bridge before beauty. Get `move.py` green and correct against the real dataset first; prove the Foundry pipe (Phase 0) before spending anything; the map only renders state the engine already produced.

## Content side-thread (private; keep OUT of this repo)
A personal Dragonlance (*Shadow of the Dragon Queen*) module is being built via the engine's import path (paste book text → markdown → `import_campaign.py`). **Never commit book text to this fork.** Campaign/character data live under `DND_CAMPAIGN_ROOT` (default `~/.claude/dnd`) — OUTSIDE the repo tree; git never sees it. Don't save raw book markdown inside the repo folder and don't point the data root into the repo. Verify: `python skills/dnd/scripts/path_config.py show`.

## Full plan (source of truth)
Notion hub: https://app.notion.com/p/397cefb058ee8186ad03c809f2ec7088 — read the **START HERE** block, then **Visual Layer Build — Foundry front-end (CURRENT DIRECTION)**, **Settled Questions & How It Runs**, and **Codebase Map**. (Prior Art & Build-On Target, Build Spec, and Tooling & Workflow give background; Map Module — v1 Spec and Map Panel — Claude Design Brief are SUPERSEDED.)
