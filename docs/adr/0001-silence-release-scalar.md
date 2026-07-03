# Unify silence turn-ending into a single `silence_release_sec` scalar

**Context:** Personal customization on branch `feat/explicit-turn-handoff` (not
tracked in the upstream issue tracker). Users hesitating mid-speech are cut off
when VAD reads the pause as end-of-turn. The obvious fixes
each add a boolean (`disable_silence_detection`, a proposed `patient_listening`),
but two booleans that both "turn off VAD ending" collide: their meanings overlap
and you must define combination rules for when both are set.

**Decision:** Collapse the behavior into one continuous scalar,
`silence_release_sec`: `0` = end on the normal VAD threshold (current behavior),
`N > 0` = tolerate silence up to N seconds then release (patient listening,
canonically 60), `-1` = never release on silence (ends only at
`listen_duration_max` or on explicit `skip_forward`). The existing
`disable_silence_detection=true` is kept as an alias for `-1` for backward
compatibility.

**Why:** The feature is inherently a single question — "how long do we tolerate
silence?" — so splitting it into discrete booleans was an artificial
decomposition that manufactured the overlap/combination problem. A scalar makes
the two booleans two points (0 and -1) on one axis, removes any need for
combination rules (a single value cannot contradict itself), and naturally
expresses intermediate tolerances (30s, 90s).

**Considered alternatives:** (a) Two coexisting booleans with an OR/precedence
rule — rejected: manufactures combination semantics and ongoing ambiguity.
(b) A `patient_listening` boolean superseding `disable_silence_detection` —
rejected: still two names for one axis, and no intermediate values.
