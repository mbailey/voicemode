# Block timeline replaces the significant-silence marker model

**Context:** Personal customization on branch `feat/explicit-turn-handoff` (not
tracked in the upstream issue tracker). ADR 0002 shipped silence observability as
inline markers (`⟨pause 5.1s⟩` / `⟨pre-speech 3.2s⟩`) inserted **only** at
*significant* silences (≥2.0s), with a `Silence:` summary field attached only on
turns that had one. The new requirement is finer: the assistant wants the user's
turn rendered as an explicit, per-block timeline — every speech block and every
gap with its own duration — so it can perceive *"어… 하는 시간", "그… 하는
시간", 침묵 시간* and judge how much the user is stumbling or thinking.

**Decision:** Add an opt-in **block timeline** (`measure_blocks` converse
parameter) that renders a whole turn as a time-ordered sequence of blocks:

```
모델은 (0.7s) (gap 5.3s) 음 잘모르겠어요. 그... (6.3s) (gap 10.2s) 그러니까 (1.6s)
```

Two block kinds alternate: **speech blocks** (`text (Ns)`) and **gaps**
(`(gap Ns)`). **Only a gap (silence) breaks a speech block** — fillers ("음",
"그...") stay inside the block as ordinary text and are neither identified nor
timed separately. Block/gap durations come from the **VAD** (single source of
truth); word timestamps are used only to assign transcript text to its block.
When `measure_blocks` is on, the block timeline **replaces** the significant-
silence markers and `Silence:` field for that turn. When off, behavior is
exactly ADR 0002.

**Why:** The marker model answered "*was there* a notable silence, and where?"
The new goal is a complete timing picture of the turn, which markers-only cannot
give: a filled, stumbling 6.3s block with little content is invisible to a model
that only flags *silences*. Expressing the whole turn as timed blocks makes both
silence *and* slow/filled speech legible from durations alone — and keeps the
system a pure **measurement** (ADR 0002): it reports seconds, the assistant
judges disfluency/deliberation. Rendering every turn (not only significant ones)
is what lets "long block, few words" surface at all.

**Considered alternatives:**
(a) Keep markers and add a separate block field — rejected: two overlapping
renderings of the same turn, duplicated timing, ambiguous which the assistant
should trust.
(b) Also identify and time fillers separately (dictionary + word-duration
threshold, `⟨filler Ns⟩`) — rejected: the user twice drew the target format with
the filler left inline ("그...") and no separate number; block duration already
exposes the stumble, so a filler subsystem adds classification risk ("그 책" vs
"그…") for no gain.
(c) Derive a disfluency/deliberation *score* in the system — rejected: crosses
from measurement into policy; the assistant interprets, per ADR 0002.
