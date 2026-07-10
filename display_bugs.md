# Display-companion bugs (not fixed — out of scope for the engine-only session)

Found while investigating engine bugs reported from the `kobold-warren-shakedown`
shakedown session. Both root causes are inside `skills/dnd/display/`, which was
declared off-limits for that session. Captured here so they aren't lost.

---

## Bug: phone roller reuses the previous roll's advantage/config

**File:** `skills/dnd/display/templates/index.html`
**Function:** `_applyDiceRequest(req)` (~line 7940), also touches `_setLocked` (~line 7918)

**Symptom:** after a PC attack roll goes out via the phone (e.g. `1d20+5`,
advantage), a *second* dice request for the follow-up damage roll (e.g.
`1d6+3`, normal) gets submitted by the phone still carrying the *first*
roll's advantage state — resolves as `1d20+3` with advantage instead of
`1d6+3` flat.

**Root cause:** after a prescribed roll resolves, the pad is deliberately
kept locked (`_setLocked(true, spec, adv)` at ~line 7898) rather than
unlocked, so the player can't fire an unsolicited re-roll. That lock disables
every `.dp-die` / `.dp-adv` button except the ones matching the *first*
roll's spec/advantage.

When the *second* `dice_request` broadcasts, `_applyDiceRequest` tries to
select the new spec/advantage by simulating clicks on the corresponding
buttons:

```js
const dieBtn  = document.querySelector(`.dp-die[data-spec="${reqSpec}"]`)
             || document.querySelector('.dp-die[data-spec="1d20"]');
if (dieBtn) dieBtn.click();
...
const advBtn = document.querySelector(`.dp-adv[data-adv="${req.advantage || 'normal'}"]`);
if (advBtn && !advBtn.hasAttribute('disabled')) advBtn.click();
```

But these buttons are *still disabled* from the previous roll's lock — only
the die/adv buttons matching the **first** roll's spec/advantage were left
enabled. A `.click()` call (real or synthetic) on a `disabled` `<button>`
does not dispatch a click event in browsers, so:
- `dieBtn.click()` silently no-ops when `reqSpec` differs from the previous
  roll's spec (the button for the new die size is disabled) → the `spec` JS
  variable is never updated, stays at the old value.
- Same for `advBtn.click()` — the guard `!advBtn.hasAttribute('disabled')`
  is checking exactly the state left over from the *previous* lock, so it
  correctly detects the button is disabled and skips the click — but the
  fallback is to do nothing, leaving `adv` stale, instead of forcing the
  value through.

`mod` (the modifier) is the exception: it's assigned directly
(`mod = Math.max(-30, Math.min(30, Number(req.modifier) || 0));`), not
click-driven, so it *does* update correctly — which is exactly why the
observed bad roll had the right modifier (`+3`) but the wrong die/advantage
(`1d20`/advantage instead of `1d6`/normal).

`_setLocked(true, reqSpec, ...)` is called at the *end* of
`_applyDiceRequest` (~line 7982), which does clear the disabled attributes
for the new spec/adv — but by then the click attempts have already silently
failed, so `spec`/`adv` were never updated to begin with.

**Fix:** unlock (clear all disabled attributes) *before* attempting to
select the new spec/advantage, so the simulated clicks can actually fire.
Add a call to `_setLocked(false)` at the top of `_applyDiceRequest`, right
after the "not for this phone" early return, before the `dieBtn`/`advBtn`
lookups:

```js
function _applyDiceRequest(req) {
    if (!req) return;
    const me      = (nameEl.value || '').trim().toLowerCase();
    const targets = Array.isArray(req.characters) && req.characters.length
      ? req.characters.map(c => String(c).toLowerCase())
      : [String(req.character || 'any').toLowerCase()];
    const isAny   = targets.includes('any');
    if (!isAny && !targets.includes(me)) return;                  // not for this phone

    _activeRequestId = String(req.request_id || '');

    // NEW: clear any lock left over from a previous prescribed roll so the
    // die/adv buttons below are actually clickable — a disabled <button>
    // silently no-ops on .click(), which is what let `spec`/`adv` go stale.
    if (_locked) _setLocked(false);

    // Spec → click the matching die button. If unknown, fall back to d20.
    const reqSpec = (req.spec || '1d20').toLowerCase();
    ... (unchanged)
```

Everything after that (the `dieBtn.click()`, `advBtn.click()`, and the final
`_setLocked(true, reqSpec, (req.advantage || 'normal'))`) stays as-is — the
final `_setLocked(true, ...)` re-applies the correct lock for the *new*
roll once `spec`/`adv` are correctly set via the now-functional clicks.

This is a one-line addition (`if (_locked) _setLocked(false);`), not a
rewrite — the existing click-driven update path is correct once the buttons
it's clicking aren't disabled.

---

## Bug: input-staging auto-fire threshold defaults to total character count, not human-player count

**Files:** `skills/dnd/display/dnd-display-app.py` (`_expected_count`,
~lines 331-334, 1053-1058, 1640-1646), `skills/dnd/display/push_stats.py`
(`--autorun-threshold` CLI flag, already implemented)

**Symptom:** with 4 party characters but only 1 human player (the other 3
are DM-run allies), a single ready action never promotes into the queue —
the auto-fire condition never reaches its threshold.

**Root cause — NOT actually a bug, once traced fully:** `_expected_count`
is computed server-side as `max(1, len(players))` from whatever `"players"`
array was pushed via `push_stats.py --json` at campaign load — i.e. it
counts *every* character pushed, DM-run or not, because the pushed payload
has no way to distinguish them (no `dm_run`/`is_human` flag in the player
schema). The server has **already got an override for exactly this case**:
`_autorun_threshold`, settable via `push_stats.py --autorun-threshold N`,
which takes precedence over `_expected_count` (`dnd-display-app.py:383`).
This is even documented in `SKILL-scripts.md` under "N-player threshold."

So the actual gap isn't broken code — it's that nothing in the documented
campaign-load flow tells Claude to *call* `--autorun-threshold` with the
human-player count when the party includes DM-run allies. **Fixed this
session as a `SKILL-scripts.md` documentation addition** (no `display/`
files touched) rather than a code change — see the commit for this bug.

**Possible future code-level improvement** (not done — would require
touching `display/`): extend the `"players"` schema pushed via
`push_stats.py --json` with a per-player `"dm_run": true/false` flag, and
change the `_expected_count` computation in both places it's calculated
(`dnd-display-app.py:1058` and `:1645`) from `len(players)` to
`sum(1 for p in players if not p.get("dm_run"))`. Falls back to today's
behavior for any payload that doesn't set the flag, so it's backward
compatible. Would make the correct threshold automatic instead of relying
on the DM to remember `--autorun-threshold`.
