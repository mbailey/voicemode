# Tasks

Mike's build order (voice 03:10-03:13 Thu 2026-09-24): preview first;
turn as a hint; files as the default, mail an option; converse long-lived;
device on every line. Each task names the requirement it lands and the
VoiceMode card it belongs to. None started.

## 1. Write during the listen (VM-2270)

- [ ] 1.1 Add the `heard_YYYY-MM-DD.jsonl` writer beside
  `conversation_logger.py`: append-only, `seq`, date rollover shared with
  the exchange log. (*conversation log*, shape)
- [ ] 1.2 In the capture path `converse` already uses, append a `partial`
  line per STT chunk and a `turn` line at end of turn, with `via:
  "converse"` when the caller is `converse`. No behaviour change to
  `converse`'s return. (*conversation log*, shape)
- [ ] 1.3 `listen started`, `heartbeat`, `listen stopped` events.
  (*listen*, alive)
- [ ] 1.4 `voicemode exchanges tail --heard` follows the new file, so the
  "tail the JSON logs" tool Mike remembers covers it.

## 2. The hook and the cursor (VM-2270)

- [ ] 2.1 A `heard` hook script under `voice_mode/data/hooks/`, installed
  by `voicemode claude hooks add heard`, on `PostToolUse` (and
  `PostToolBatch` where offered). (*conversation log*, hook)
- [ ] 2.2 Per-session cursor files under `~/.voicemode/state/heard-cursor/`.
  (*conversation log*, cursor)
- [ ] 2.3 Print lines past the cursor, partials collapsed into their turn,
  device and time on each, within the budget; `+k more, seq a-b` on a cut;
  cursor never past what was printed. (*conversation log*, cursor)
- [ ] 2.4 Watch it fail once: a budget of 1 line against 40, and prove the
  next call resumes at the right `seq`. Charter 3: a gate never seen
  failing is a decoration.

## 3. The `listen` tool, as a spike on a branch first (VM-2270)

- [ ] 3.0 **The spike** (Mike, 03:31: "quite easy to do as a spike, on a
  branch"): a `listen` tool that does not return; its own capture loop;
  end of turn by the current two-second silence; partials and turns
  written to the log; return on an aged turn. Nothing else. Measure it on
  m5 with the AirPods and the Mac mic before anything below. (*listen*,
  fresh)
- [ ] 3.1 Register `listen` in the MCP server with `source`, `age`,
  `ceiling`, `wake_on_partial`, `stop` parameters; return `{reason, text,
  cursor}`. (*listen*, long-lived)
- [ ] 3.2 Return only on aged turn, end word, ceiling, stop, error.
  (*listen*, long-lived)
- [ ] 3.3 Advance the session cursor past a returned turn. (*conversation
  log*, cursor)
- [ ] 3.4 Silero VAD behind the same end-of-turn interface as the silence
  timer; compare on the same recording. (*listen*, fresh)
- [ ] 3.5 Transcription behind one interface: whisper (today's server),
  Apple on-device speech, and Parakeet (MLX) for previews; the 19 Sep
  ground-truth eval (`~/.cora/apple-fm/research/streaming-eval.md`) as the
  yardstick: 1.5-1.9% WER for Apple and Parakeet, 3.9% for a Parakeet
  preview at the moment speech stops. (*listen*, fresh)
- [ ] 3.6 Confirm `listen` never takes the conch, with a second agent
  speaking while it runs. (*listen*, fresh)
- [ ] 3.7 Echo cancellation: list what the fresh loop needs so that its
  own agent's speech is not heard back as the human's (kin's `echo.py`
  is the prior art); build it in a later task if the spike shows echo.

## 4. Devices (VM-1010)

- [ ] 4.1 Resolve the input device name from the audio library at listen
  start and on each chunk; `device` on every line; `device changed` event.
  (*conversation log*, device)
- [ ] 4.2 Report the input device in `converse`'s result. (*conversation
  log*, device)

## 5. Control words

- [ ] 5.1 Config: wake words and end words, machine-level and per agent.
- [ ] 5.2 Text match on partials and turns; `event` lines; end word returns
  `listen`. (*control words*)

## 6. Wake on partial

- [ ] 6.1 `wake_on_partial` config, default off; gated by the wake word when
  one is set. (*listen*, partial)

## 7. Docs and the skill

- [ ] 7.1 The VoiceMode skill: when to arm `listen`, that re-arming is the
  caller's job, and that the hook shows what was heard. Mirror the pager's
  wording: "re-arm is the next thing you do".

## 8. Measure what this spec left unmeasured

- [ ] 8.1 The ceiling on one backgrounded MCP call on m5 (Mike: "about 29
  minutes, I'm not sure").
- [ ] 8.2 Whisper load under a one-hour `listen`.
- [ ] 8.3 Two capture consumers on one device.

## Later, not this change

- Mail as a second consumer of the log (Q9).
- kin writes `source: "call"` lines into the same file (KIN-2, candidate 4).
- Streaming STT with a revisable tail (WhisperLiveKit, /IDEAS 1040.12).
- The output-device registry (/IDEAS 2280.2); encrypted-to-disk (2280.1).
