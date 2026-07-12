# D&D Skill — Wiring Spec (Table Law)

Born from the 17-defect harvest of the 2026-07-10 measured play session
(kobold-warren-shakedown). Every rule below kills a defect class that occurred
in live play; the appendix maps each harvested defect to the rule that makes it
impossible by construction. Load this file at `/dm:dnd load` alongside
`SKILL-scripts.md` and `SKILL-commands.md`. It is law, not guidance.

> **Path note:** commands below use `${CLAUDE_SKILL_DIR}` for the skill
> directory. This file is read verbatim, so that token is **not** auto-expanded
> here — substitute the absolute skill-dir path (from `SKILL.md`) before
> running any command, or it will fail with a broken `/scripts/…` path.

---

## §0 The Contract

**The app owns truth; the DM narrates it.** Scripts decide numbers. Files hold
state. The display shows what the scripts said. The DM's fingers never
manufacture, retype, or duplicate a fact that a script or file already owns.
Every rule in this file is that one invariant applied to a place it broke.

- If any older instruction — in this skill, a campaign file, or habit — appears
  to conflict with this file, **this file wins**. (`SKILL.md`'s per-turn combat
  sequence is the hot-path skeleton; this file is the law each step invokes.
  They are written to agree; if they ever don't, that is a bug — log it.)
- Rules carry citable IDs (`§1-a`, `§4-a`, …). During play, a defect gets ONE
  line in the campaign's `defects.md` citing the rule it violated (or `no-rule`
  if the law is missing) and the game continues. Never fix mid-session.
- Nothing in this file requires code changes. Every mechanism below runs on
  the scripts as they exist today.

---

## §1 The Dice Pipe — displayed numbers are script output

**LAW: a number shown on the display must have traveled from script stdout to
`send.py` through machinery — a shell variable or a pipe — never through
retyping.** Fiction and context are yours; digits are the script's.

**The one pattern.** Capture once, look at it, send the same bytes:

```bash
OUT=$(python3 ${CLAUDE_SKILL_DIR}/scripts/dice.py d20+5 --label "Ren - Insight")
echo "$OUT"     # ← you read the result HERE, from the same variable you send
{ echo "Ren - Insight (reading Scritch):"; echo "$OUT"; } \
  | python3 ${CLAUDE_SKILL_DIR}/display/send.py --dice
```

> **ASCII rule RETIRED (2026-07-12):** defect #3 was killed at the root by
> `c2e50f0` (stdin forced to UTF-8 across the pipe, verified byte-level under
> cp1252) and the fix is synced. Composed display strings may use full
> punctuation again. If mojibake EVER reappears on any surface, that is a new
> defect line citing #3 — log it, don't work around it.

- The header line carries name / skill / in-fiction context. It **may not
  contain roll digits** — no restated totals, no "= 17". A DC may appear only
  if you are reading it off a stat block or file in front of you, never from
  memory.
- `$OUT` goes to the display verbatim. Editing, summarizing, reformatting, or
  "cleaning up" `$OUT` is a defect **(§1-a)**. The nat-20/nat-1 flags ride the
  script's own line untouched.

**Attack rolls** — `combat.py attack` already prints a chip-shaped block; pipe
it whole:

```bash
OUT=$(python3 ${CLAUDE_SKILL_DIR}/scripts/combat.py attack --atk 4 --ac 15 --dmg 1d6+2)
echo "$OUT"
{ echo "Kobold 3 -> Ren:"; echo "$OUT"; } \
  | python3 ${CLAUDE_SKILL_DIR}/display/send.py --dice
```

**Attack modifiers are flags, not workarounds (§1-c).** The pipe expresses
every common attack state directly — two attack calls picking the higher, or
hand-summed buff dice, are §1 defects now that the flags exist:

```bash
# advantage / disadvantage (both d20s ride the chip; adv+dis cancel to straight)
python3 ${CLAUDE_SKILL_DIR}/scripts/combat.py attack --atk 4 --ac 15 --dmg 1d6+2 --adv
# forced crit — unconscious target within 5 ft (nat-20 doubling is automatic;
# --crit covers the crits the die doesn't show; nat-1 still auto-misses)
python3 ${CLAUDE_SKILL_DIR}/scripts/combat.py attack --atk 4 --ac 10 --dmg 1d6+2 --crit
# compound damage — sneak attack, smite riders (crit doubles every dice group)
python3 ${CLAUDE_SKILL_DIR}/scripts/combat.py attack --atk 6 --ac 14 --dmg 1d8+2d6+3
```

**Buffed checks and saves** — Bless/Bane/Guidance ride ONE `dice.py` call
(compound notation, `adv`/`dis` applies to the first die):

```bash
OUT=$(python3 ${CLAUDE_SKILL_DIR}/scripts/dice.py "d20+5+1d4" --label "Ren - WIS save (Bless)")
OUT=$(python3 ${CLAUDE_SKILL_DIR}/scripts/dice.py "d20+3-1d4 adv" --label "Kobold - save (Bane)")
```

**Hidden rolls** — `--silent` returns the bare integer; you adjudicate from the
variable and narrate only the perceived result. If table style later surfaces
the number, build that chip from `"$ROLL"` by substitution, never by retyping:

```bash
ROLL=$(python3 ${CLAUDE_SKILL_DIR}/scripts/dice.py d20+5 --silent)
echo "hidden Insight: $ROLL"    # terminal only — resolve from this
```

**Initiative** — send the rolls block exactly as `combat.py init` printed it
(extraction by `sed` is machinery; retyping is not):

```bash
OUT=$(python3 ${CLAUDE_SKILL_DIR}/scripts/combat.py init "$COMBATANTS_JSON")
echo "$OUT"
echo "$OUT" | sed -n '/Initiative rolls:/,$p' | grep -v '^STATE_JSON:' \
  | python3 ${CLAUDE_SKILL_DIR}/display/send.py --dice
```

**Opportunity attacks from `move.py`** — the result is JSON; chips are built
from it BY CODE, then sent only if any OA actually fired (empty stdin makes
`send.py --dice` abort by design):

```bash
RES=$(python3 ${CLAUDE_SKILL_DIR}/scripts/move.py --map "$MAP" --token "Grosh" --to 7,4 --write)
echo "$RES"
CHIPS=$(RES="$RES" python3 - <<'PY'
import json, os
r = json.loads(os.environ["RES"])
for o in r.get("oas", []):
    if o.get("hit") is None:
        verdict = "UNRESOLVED (no attack stats)"
    elif o["hit"]:
        verdict = "HIT" + (" - CRITICAL" if o.get("crit") else "") + f", {o.get('damage', 0)} damage"
    else:
        verdict = "MISS"
    print(f"OA - {o['attacker']} -> {o['target']}: d20({o.get('d20', '?')}) {verdict}")
PY
)
[ -n "$CHIPS" ] && echo "$CHIPS" | python3 ${CLAUDE_SKILL_DIR}/display/send.py --dice
```

**Failure discipline.** `send.py` prints failures to stderr and exits non-zero
on partial failure. A failed send is surfaced at the table and re-sent — a
resend after a FAILED send is not a duplicate (§4 governs duplicates). A
swallowed send error is a defect **(§1-b)**.

*Kills: defect #6 (chip showed 12, dice rolled 9).*

---

## §2 The Tactical Frame & the Move Pipe — space is mechanical

Every gridded combat has a live map file:
`~/.claude/dnd/campaigns/<name>/map.json` (grid, walls, difficult, tokens —
and `zones`, §3). It is created at combat start with a token for every
combatant (`side`, `speed_ft`, `reach_ft`; `atk_bonus`/`dmg` overrides for
anything not in the SRD — INCLUDING every PC, whose melee numbers come off
their sheet at combat start, so PC opportunity attacks resolve inside the
move.py pipe instead of by hand). The combat blob still owns HP/AC/initiative;
**map.json owns space, and `move.py` is its only writer.** Join key = name.

**Turn opening — every combat turn, no exceptions, in this order:**

1. **Drain queued input** (every mode, including solo `roll_mode: auto`):
   `python3 ${CLAUDE_SKILL_DIR}/display/check_input.py`
2. **Reset the actor's turn budget** — the zero-cost self-move idiom (begin-turn
   reset applies even though the token doesn't move):

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/move.py --map "$MAP" \
     --token "Grosh" --to <current X,Y> --begin-turn --write
   ```
3. **Send the tactical frame** — composed from map.json (the file is the only
   source for positions; never from memory), as a plain table-channel send:

   ```
   == ROUND 2 | TURN 3/7: Grosh ==
   1. Grosh     @ (7,4) - 30 ft mv - adjacent: Kobold 2 (5 ft)
   2. Ren       @ (5,9) - nearest threat Kobold 4, 15 ft - Darkness edge 10 ft NE
   3. Kobold 2  @ (8,4) - engaged with Grosh
   4. Kobold 4  @ (5,12) - 15 ft from Ren, in Darkness
   ZONES: Darkness - center (9,7), r 15 ft - Aessa conc, ~8 min left
   ```
   Distances are squares × 5 ft (Chebyshev). When a distance is
   load-bearing — an OA window, a spell range, a zone edge — compute it with
   the §3 one-liner; never eyeball a number a decision hangs on.
4. **Then the actor acts — gated by pilot (§5-c).** If the acting token is a
   PC with a human pilot, STOP here: the frame is the question. No movement,
   no resource spend, no roll of theirs resolves until that player's declared
   action arrives (under autorun, the wait loop carries it back). DM-piloted
   tokens — designated DM-run allies and monsters — act immediately.

A combat turn that opens without steps 1–3 is a defect **(§2-a)**; resolving
any part of a human-piloted PC's turn without their input is a §5 defect
regardless of how disposable the PC looks.

**Every position change goes through `move.py --write`** — PC, ally, monster,
and forced movement (push, pull, grapple-drag). Movement that exists only in
narration is a defect **(§2-b)**: if a creature moved, there is a `move.py`
call that moved it; if `move.py` rejected it, it didn't move — relay the
printed reason and offer the legal options (Dash, shorter path, Disengage).
The player picks; you never pick for them (§5).

**Provoking moves.** Reach is visible on the frame, so you know before
committing whether a path provokes:

- Mover is a **PC** leaving enemy reach → the OA belongs to the enemy; run the
  move normally (`--write`) and chip any OA per §1. Offer Disengage first when
  the player's declared intent implies escaping (§5 — their action, their
  choice).
- Mover is an **enemy/ally** leaving a **PC's** reach → the PC's reaction is a
  player resource; `oa_consent` (§5) governs:
  - `auto` → run with `--write`; move.py rolls the PC's OA; chip it per §1.
  - `ask` → **dry-run first** (same command WITHOUT `--write` — nothing
    commits), read `.oas`; if a PC OA would fire, ask that player: *"Kobold 2
    is leaving your reach — spend your reaction?"* On yes, rerun with
    `--write` (that run's dice stand — the dry-run's dice are void). On no,
    set that PC token's `reaction_available` to `false` in map.json, run the
    move with `--write`, then restore it to `true` in the same beat —
    declining is not spending. The ask goes to that PC's designated pilot
    (§5-c) and ONLY the pilot answers it — the DM answering its own dry-run
    question is a §5-b breach, however tactically obvious the answer.

**Death cleanup (§2-c).** In the same beat a combatant drops to 0 HP or
otherwise leaves the fight: set its map.json token's `reaction_available` to
`false`, and remove the token at the end of that turn. map.json carries no
alive/dead state, so a dead token left in place still fires opportunity
attacks (found live: a 0-HP baaz took an OA at the sdq-test fight). This
manual guard stands until move.py grows its per-token OA-suppression flag
(build list).

**The advantage checklist (§2-d).** Before EVERY attack roll resolves, walk
the sources — then say which fired in the chip header. The pbtso road and H2
ambushes both straight-rolled while the narration explicitly established
unseen shooters; a chapter built of ambushes was under-powered by exactly one
die (#33).

- **Advantage:** attacker unseen/hidden from the target (every ambush
  volley); target restrained, stunned, blinded to the attacker, or prone
  within 5 ft; Pack Tactics with an ally adjacent to the target (already the
  habit); helped (Help action); target paralyzed or unconscious — within
  5 ft those two are ALSO `--crit` on a hit.
- **Disadvantage:** attacker can't see the target; target prone at range
  (beyond 5 ft); attacker restrained, poisoned, prone, or frightened of
  something in line of sight; long range; ranged attack with an enemy
  adjacent to the attacker.
- **Any adv + any dis = CANCEL — straight roll** (5e RAW: one of each cancels
  regardless of counts; #38's rider reasoning). The flags do this themselves
  when both are passed.

Mechanically: `combat.py attack --adv|--dis` (§1-c) — never two calls picking
the better result.

*Kills: defect #15 (six-enemy fight, zero spatial frame); step 1 kills #5
(staged input never consumed in solo auto); §2-c kills sdq-test defect #19
(dead-token OA).*

---

## §3 Zones — space lives in the map, time lives in the tracker

Any effect with an area — Darkness, Web, Fog Cloud, Spirit Guardians, Grease,
Moonbeam — gets **both** of these at cast time, in the same beat:

1. **Geometry → map.json**, a `zones` entry (move.py preserves keys it doesn't
   know — zones ride the same file as positions and survive every move):

   ```json
   "zones": [{"name": "Darkness", "center": [9,7], "radius_ft": 15}]
   ```
2. **Clock → tracker.py**, SAME name, real duration, `conc` when it is
   concentration — plus the display push bundled with that beat's send:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/tracker.py -c $CAMP effect start "Aessa" "Darkness" 10m conc
   # …and on the beat's narration send:  --effect-start "Aessa:Darkness:10m:conc"
   # (real durations: Darkness is conc. up to 10 MINUTES; use Nr only for
   #  genuinely round-denominated effects, e.g. Moonbeam 1 min = 10r in combat)
   ```

**One owner per fact:** map.json owns WHERE, tracker.json owns HOW LONG and
concentration, the display is a projection of both. The join is the effect
name — the identical string in both places, always.

**In/out is arithmetic, not eyeball** — Chebyshev distance, squares × 5 ft:

```bash
python3 -c "print(max(abs(7-9), abs(4-7)) * 5)"   # Grosh (7,4) vs center (9,7) → 15 ft → inside r15
```

- The frame lists every active zone every turn: name, center, radius, rounds
  remaining (from the last tick), owner if concentration (§2).
- **Expiry or break** — when `tracker.py effect tick` prints an expiry, or
  concentration breaks: in the SAME beat, (a) push `--effect-end
  "NAME:SPELL"`, (b) delete the zone entry from map.json, (c) one
  fiction-channel line marks it (*"The darkness thins and is gone."*).
- A zone in map.json with no living tracker effect — or a ticking effect whose
  zone is missing — is a defect **(§3-a)**.

*Kills: the Darkness finding (area effects with no spatial existence) and the
geometric half of #13 (zones that outlive their spells).*

---

## §4 Send Discipline — beats, not essays

**REPEALED:** *"compose the complete narration first, then call send.py as the
very last action"* and *"ONE Bash tool call per response."* The delivery rule
replaces any word cap. Dead air is the enemy, not speech length.

**A turn is delivered in beats.** A beat is one dramatic unit — a roll and its
consequence, an exchange of dialogue, 1–3 short paragraphs of scene.

- **A roll's chip goes out in the same Bash call that rolled it** — §1's
  pattern makes roll-and-chip atomic. The screen is never empty while you
  compose.
- **The first beat is sent before any long composition begins.** If the turn
  needs a page, the table reads its opening line while you write the rest.
- **Stats ride the beat where the change happened** — `--stat-*` /
  `--effect-*` flags bundle onto that beat's send, not a cleanup push at turn
  end.
- **Block order within a beat** (unchanged): `--player` → `--dice` → narration
  (+ stat flags) → `--npc` → `--tutor`.
- **Each beat is sent exactly once (§4-a).** Never resend to fix wording — a
  correction is a NEW short beat (*"(correction: the bolt takes Kobold 4,
  not 3.)"*). The one exception: a resend after `send.py` REPORTED failure
  (§1-b) is recovery, not duplication.
- Autorun unchanged: when active, the wait is still the last call of the
  response — beats first, wait last.

**No display ≠ no beats (§4-b).** When no display is attached, the chat/
terminal IS the table channel and this whole section still applies to it: the
turn is DELIVERED in beats — frame, then each roll's chip as it lands, then
narration — printed as they resolve, never compressed into one end-of-run
composition ("I did not see any of this actually play out" is the defect
shape, #30). Bookkeeping (tracker calls, file edits, ledger sweeps) lands
AFTER the beat it belongs to: the table hears the sword hit before the
paperwork about it. Spotted-and-avoided still gets its beat — a trap noticed
is a beat, not a line item in "the journey was uneventful."

*Kills: defect #4 (Thora's turn delivered twice), the dead-air class the
Stage-1 stopwatch measured, and #30 (whole playtest run compressed into one
composition when no display was attached).*

---

## §5 The Player-Agency Protocol — the PC is not yours

**LAW: the DM never decides ANYTHING for a player's PC.**

- **Not resources — spending OR declining.** An unasked *"he saves his hit
  dice"* is the same violation as an unasked spend. Every expenditure and
  every waiver is the player's call: hit dice, ki, slots, rage uses, potions,
  scrolls, Inspiration, ammunition that matters.
- **Not dialogue.** Never put words in a PC's mouth beyond what the player
  gave. Paraphrase their declared intent when echoing to the display
  (`send.py --player`), don't author new speech.
- **Not tactics.** Targets, paths, readied actions, reactions, who they help,
  when they retreat — asked, never assumed.

**Ask-then-act.** Any PC decision point → surface it and wait. Under autorun,
the question goes to the display and the wait loop carries the answer back.

**Pre-roll surfacing (§5-a).** Before resolving any roll, save, or check that
a PC could legally alter, offer the applicable option in one compact
table-channel line — *"Ren - Shadow Arts: Pass Without Trace would cover
this approach (2 ki, concentration, up to 1 hour). Use it?"* This includes reactions (Shield, opportunity
attacks), features and spells, advantage sources, Inspiration — and
**explicitly the hand-transcribed non-core traits** on the sheet: consult the
PC's features list before any group check or defining-moment roll. Live
evidence says core traits fire on their own and hand-transcribed ones don't —
this rule is the compensation until the Stage-2 trait test says otherwise.

**Rests are itemized.** Short rest: each PC's hit dice offered die by die;
features that recharge, named. Long rest: recovery stated, choices asked.

**The one standing consent (§5-b).** At session start — once, not per event —
ask: *"When an enemy provokes an opportunity attack, may I auto-spend your
reaction to take it, or ask you each time?"* Store the answer in `state.md →
## Session Flags` as `oa_consent: auto` or `oa_consent: ask` (per player if
several humans are at the table; default on dismissal is `ask`). This flag
covers OA reactions ONLY — every other reaction is asked per event. §2 defines
the mechanical dance for each value. This is what preserves the measured
latency win without silently spending player resources.

**Pilot designation (§5-c).** Every PC has exactly one pilot — a named human
or the DM — recorded in `state.md → ## Session Flags` as
`pilots: Kest = Jeff, Levna = DM`, set at PC creation or session setup and
NEVER inferred. "Throwaway," "test," or "disposable" is not a designation;
an undesignated PC's decision point is a hard stop-and-ask, not a license
(the sdq-test fight produced three violations from this one gap). If a
mid-session instruction contradicts the stored config, the DM echoes the
config in one table-channel line — *"standing config: I run Grosh/Thora/
Aessa — say the word to take one over"* — instead of silently resolving the
conflict in either direction.

**Exempt: DM-run allies.** Characters designated `= DM` under §5-c (the
party's NPC allies) are the DM's to play — fully, including their resources
and tactics.
`roll_mode` law in SKILL.md sits above this section and is unchanged: under
`players`, PC dice are never rolled by the DM, period.

*Kills: defects #14 (declined hit dice unasked, PC micro-decisions narrated),
#16 (auto-spent reaction), #8 (Pass Without Trace never offered).*

---

## §6 The Narration Register — fiction never speaks mechanics

Two channels, hard wall between them:

- **Fiction channel** — scene narration and every word spoken by a character
  (NPC or ally). Contains ZERO game vocabulary: no rolls, DCs, saves, HP,
  slots, action economy, condition names as rules terms — and no numerals for
  game quantities.
- **Table channel** — dice chips, DM statements, tutor blocks, the tactical
  frame. ALL mechanics live here.

A character may urge, warn, and describe in-world — *"She's bleeding out,
with me, NOW!"* — but never adjudicate — ~~"we're all making death saves in
the same round."~~ A spell name in speech is permitted only as words the
character would actually say (a prayer's name, an incantation), never inside
rules-talk; when in doubt, cut it.

Need to convey a mechanic mid-dialogue? Drop to a table-channel line, then
return to fiction. **Test (§6-a): read the character's line aloud — if it
teaches the listener a rule, it's a defect.**

**The wall also holds at load — and on every piped surface (§6-b).**
PLAYER-FACING means: recaps, scene-sets, **tactical frames (§2)**, traversal
frames, chip headers, and EVERY block `send.py` pipes to the display — plus
their terminal equivalents under §4-b. All of them speak only facts the
players have learned in play. Fields marked `(secret)` / DM-only in
npcs-full.md, world.md, or the arc never surface there until revealed at the
table — and **module source prose never rides a frame**: the pbtso H1 frame
printed a Development note ("H2 lookouts are supposed to be watching this
spot") verbatim onto what becomes a display surface in the live game (#32).
Harmless solo, a spoiler at the table. The sdq-test session-0 recap narrating
an undiscovered betrayal is the same defect shape.

*Kills: defect #10 (Thora naming death saves and "Preserve Life" as mechanics
in speech).*

---

## §7 Traversal Pacing — risk buys a decision

A **risky traversal** — infiltration, climb, swim, chase leg, crossing under
watch, trap-suspected passage; anything where failure has real stakes — may
not be presented and resolved in the same beat.

Minimum shape, in order:

1. **Stakes beat** — what makes it hard, what failure costs, rendered in
   fiction (§6).
2. **At least one real decision** — route, marching order, precaution, tool,
   pace, who leads. A decision with consequence, not *"do you proceed?"*
3. **Then the resolving roll(s)** — framed by the choice: the chosen
   precaution buys advantage, a lower DC, or a different ability, and the
   table-channel line says which.

Collapsing a multi-stage passage into one group check, entrance to exit, is a
defect **(§7-a)**. This rule prices RISK, not distance — trivial travel still
fast-forwards (SKILL.md Standard 6 is untouched; this is its floor, not its
ceiling).

*Kills: defect #9 (the infiltration tunnel resolved in one Stealth check with
zero decision points).*

---

## §8 The Ledger — one home per fact, pushes, no prose copies

Every mechanical fact has exactly ONE home; everything else is a projection
pushed FROM that home. **The owner changes first; the push rides the same
beat; prose never carries a balance.**

| Fact | Home (only writer) | Projections (same-beat push) |
|---|---|---|
| Token positions | `map.json` (`move.py` only) | tactical frame; Foundry (Stage 3+) |
| Conditions, concentration, timed effects, death saves | `tracker.json` (`tracker.py` only) | `--stat-condition-*`, `--stat-concentrate`, `--effect-*` |
| HP in combat | combat blob (`combat.py` / DM) | `--stat-hp`; character file at save |
| Spendable pools — ki, rage uses, spell slots, hit dice, Second Wind | the character file's `## Resources` block — one structured line per pool (`Ki: 2/3`) | `--stat-slot-*`, `push_stats.py` partial flags |
| XP | `xp.py` (writes the character file) | `xp.py`'s own push + `--xp-award` block |
| World clock | `calendar.py` | `--world-time` |

**The spend flow** (any pool, every time): player consents (§5) → edit the
`## Resources` line → same-beat display push → narrate. Three moves, one beat.

**Bootstrapping:** if a character file has no `## Resources` block yet, create
it at session load — one line per pool (`Ki: 2/3`, `Rage: 1/3`, `Hit Dice:
3/3 (d8)`), moving each current value IN and deleting every prose copy it
replaces (§8-a). The block exists from that load onward; the sheets stop
being novels about resources and start being ledgers.

**Prose copies are banned (§8-a).** No current-value or active-state claim
exists anywhere except the home and its pushes. A sheet's feature text
describes RULES (*"costs 1 ki"*), never balances (~~"2/3 remaining"~~).
`state.md` summarizes the flags it owns, never pool values. Narration may
gesture (*"winded, down to her last tricks"*), never number.

**NPCs are tracked entities too (§8-b).** Any state change on an NPC the
display knows — HP band, condition, unconscious/conscious — pushes in the
same beat. A sidebar that still says UNCONSCIOUS after the heal landed is a
defect.

**Effect lifecycle (§8-c).** Start → tracker + `--effect-start` (+ zone, §3).
Tick → `tracker.py effect tick <actor>` on that actor's every turn. End —
expiry, break, or dispel → `--effect-end` in the SAME beat, plus zone removal
(§3). A chip glowing on screen for an effect the tracker says is dead is a
defect. RAGING ends when the rage ends, not when someone notices.

**Global roster ruling (§8-d).** `~/.claude/dnd/characters/` is a WRITE-ONLY
mirror, touched exactly once per session at `/dm:dnd save`, `mkdir -p` before
the first write, never read during play. Campaign-local
`campaigns/<name>/characters/` is the play-time truth. (This retires the
close-out crash into a nonexistent directory.)

**The close-out drift check (§8-e)** — mandatory before `/dm:dnd save` is
allowed to complete:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/session_recap.py diff --campaign $CAMP --no-roll
python3 ${CLAUDE_SKILL_DIR}/scripts/tracker.py -c $CAMP status
```

Read every sheet's `## Resources` and effect state against those two outputs;
fix mismatches BEFORE writing the save; the save confirmation states either
**"drift check: clean"** or lists what was corrected. All four sheets rotted
last session because nothing forced this look.

*Kills: defects #17 (ki triplicated and diverged; four stale sheets at
close-out), #7 (Scritch's frozen sidebar), #13 (immortal effect chips),
#12 (global-roster crash).*

---

## §9 Session Boot & the Compliance Loop

**Additions at `/dm:dnd load`** (procedure text lives in `SKILL-commands.md`):

1. Read this booklet with the other two (scripts, commands).
2. Ask the standing-consent question (§5-b) as setup Q3; write `oa_consent`
   to `## Session Flags`.
3. Snapshot the recap baseline:
   `python3 ${CLAUDE_SKILL_DIR}/scripts/session_recap.py snapshot --campaign $CAMP`
4. If combat is plausible this session, verify `map.json` exists or note that
   it will be created at first initiative (§2).
5. **Before a real game night:** check the session tail for stale/test lines
   (`~/.claude/dnd/campaigns/<name>/session_tail.json`) and clean it if
   polluted — the purge tool is a build-list item; the CHECK is table law.

**In play:** a defect gets one line in the campaign's `defects.md`, citing the
rule it broke (*"§4-a — beat resent"*) or `no-rule`, and the game continues.
Build sessions and play sessions never mix.

**The loop:** at the next build session, read the new harvest against the
appendix. A defect against an existing rule = that rule failed — strengthen
it. A `no-rule` defect = new law. The spec is alive; this file grows at build
time, never at the table.

---

## Appendix — Defect → Rule map (2026-07-10 harvest)

| # | Defect (short name) | Killed by |
|---|---|---|
| 1 | Dark-theme readability on TV | out of scope — Stage 3 "TV mode" |
| 2 | Stale test lines in session tail | §9-5 boot check (purge tool: build list) |
| 3 | Mojibake â€" in new send→render path | out of scope — encoding class sweep, next build session |
| 4 | Narration block delivered twice | §4-a |
| 5 | Staged input unconsumed in solo auto | §2 turn-opening step 1 |
| 6 | Dice chip 12 shown, 9 rolled | §1 |
| 7 | Scritch sidebar stuck UNCONSCIOUS | §8-b |
| 8 | Pass Without Trace never surfaced | §5-a |
| 9 | Tunnel infiltration = one group check | §7 |
| 10 | Thora speaks mechanics in character | §6 |
| 11 | Voice untestable on m720q host | out of scope — Stage 3 dress rehearsal |
| 12 | Close-out crash: nonexistent roster dir | §8-d |
| 13 | Effect chips never expire (RAGING/Bless/Web) | §8-c + §3 |
| 14 | DM decides for PCs (hit dice, micro-choices) | §5 |
| 15 | Combat with no spatial frame | §2 |
| 16 | Auto-spent reaction on OA | §5-b + §2 |
| 17 | Ki in three places, all diverging | §8 + §8-a + §8-e |

## Appendix 2 — Defect → Rule map (2026-07-11 sdq-test harvest)

| # | Defect (short name) | Killed by |
|---|---|---|
| 18 | Session-0 recap narrated secret state | §6-b |
| 19 | Dead token fired an OA | §2-c (manual guard; move.py flag on build list) |
| 20 | DM piloted an undesignated PC (moves, attacks, Second Wind) | §5-c + §2 step 4 gate |
| 21 | DM answered its own `oa_consent: ask` question | §5-b + §2 ask-bullet sentence |
| 22 | PC tokens outside the move.py OA pipe | §2 map-creation override rule |

## Appendix 3 — Defect → Rule/Fix map (2026-07-11 pbtso-test ch.1 playtest — ledger canon: campaigns/pbtso-test/defects.md, FINAL at 38)

| # | Defect (short name) | Killed by |
|---|---|---|
| 23 | Damage line printed `[6] + mod = 8 d6dmg` unsubstituted | combat.py format_attack fix (2026-07-12 build) |
| 24 | Dataset monsters carry no skills/saves (Stealth +6 unrecoverable) | build_srd.py + dataset rebuild: skills/saves/senses/resist fields (2026-07-12 build) |
| 25 | Road ambush has no surprise spec (DM house-ruled) | content lane — modules hub revision checklist |
| 26 | Bludgeoning-only capture rule too narrow | content lane — modules hub |
| 27 | `goblin boss` missing — non-SRD monsters can't enter the repo | lookup.py campaign supplement (campaign entry wins) + import populates supplement.json (2026-07-12 build) |
| 28 | `combat.py init` discards caller max_hp (wrongly kills wounded PCs) | init setdefault + wounded-PC regression test (2026-07-12 build) |
| 29 | `tracker.py concentrate` orphans superseded/broken conc chips | tracker auto-close in every break path (2026-07-12 build) |
| 30 | §4 beats silently stop applying with no display | §4-b terminal-beats fallback |
| 31 | `xp.py` awards ADJUSTED XP (75/head for 37-XP goblins) | xp.py award-raw split + `--encounter` as-built difficulty (2026-07-12 build; supersedes the 7/10 adjusted-award ruling) |
| 32 | H1 frame printed module Development prose player-facing | §6-b names frames + every piped surface |
| 33 | Unseen-attacker advantage never applied on ambush volleys | §2-d advantage checklist + combat.py `--adv/--dis` |
| 34 | Cross-reference on the #28 symptom (timing-probe 19-for-24) | evidence under #28 |
| 35 | `dice.py` can't parse `d20+X+NdY` (Bless inexpressible in §1) | dice.py compound expressions (2026-07-12 build) |
| 36 | `combat.py attack` has no adv/dis; `--help` crashes | argparse CLI + `--adv/--dis` flags (2026-07-12 build) |
| 37 | No die-independent forced-crit flag (auto-crit hand-rolled) | `--crit` forces crit on hit (2026-07-12 build) |
| 38 | Boss rider omitted; adv+dis=cancel mis-derived risk | §2-d cancel rule + content-lane rider completeness check |

**Later (explicitly not now):** `dice.py` chip-header flag; `move.py`
per-token OA suppression flag (retires §2's reaction-toggle dance — and the
§2-c manual guard); zones inside the engine (Stage 5 "zones v2");
session-tail purge tool; `xp.py` append-only award log.

