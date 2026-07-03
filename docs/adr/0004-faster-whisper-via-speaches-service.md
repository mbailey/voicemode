# faster-whisper word timestamps via a speaches service, not whisper.cpp

**Context:** Personal customization on branch `feat/explicit-turn-handoff` (not
tracked in the upstream issue tracker). The block timeline (ADR 0003) needs
**accurate word timestamps** to assign transcript text to the correct block. The
existing local STT backend is whisper.cpp, exposed as an OpenAI-compatible HTTP
server on port 2022. Its `verbose_json` / `timestamp_granularities=["word"]`
support is uncertain — the current code sends the parameter "regardless and
handles gracefully if words are absent" (`simple_failover.py`). Unreliable word
timestamps mean unreliable block assignment.

**Decision:** Add **faster-whisper** as a local STT backend by running
[speaches](https://github.com/speaches-ai/speaches) (a faster-whisper /
CTranslate2 server) as an OpenAI-compatible HTTP service on its own port, exactly
mirroring the existing **mlx-audio** precedent (install tool + start script +
launchd/systemd registration + provider-type detection). It is added to
`VOICEMODE_STT_BASE_URLS`, so the existing discovery/failover path
(`simple_failover.py`, `provider_discovery.py`) uses it unchanged. speaches
supports `response_format=verbose_json` with `timestamp_granularities=["word"]`
natively, giving reliable word timestamps for block assignment.

**Why:** VoiceMode's STT layer is already "any OpenAI-compatible endpoint," and
mlx-audio proves a second local backend drops in with no failover changes. A
dedicated speaches service isolates the accurate-timestamp path without
destabilizing whisper.cpp for users who don't opt into `measure_blocks`. Word
timestamps are the *reason* faster-whisper is wanted (per the design), and
CTranslate2 makes the verbose_json path cheap enough that the block timeline can
request it on every gap-bearing turn locally.

**Considered alternatives:**
(a) Fix/upgrade the whisper.cpp server to emit reliable word timestamps —
rejected: uncertain feasibility, and it entangles the measurement path with the
default STT everyone uses.
(b) Load faster-whisper in-process (no HTTP server) — rejected: breaks the
uniform OpenAI-compatible-endpoint abstraction the whole provider/failover system
is built on, and duplicates model management.
(c) Always use OpenAI cloud verbose_json — rejected: defeats the local,
low-latency goal and the explicit "use faster-whisper" requirement.
