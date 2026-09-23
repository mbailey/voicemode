<!-- PROPOSED. Written by Cora 7, 03:25-03:45 Thu 2026-09-24, on Mike's word
     (voice 03:18: "Yes, I think yes" to openspec living in this repo with
     this as its first change; 03:24: "use your own judgment and you can
     write it, and then we can discuss tomorrow"). What he has said yes to
     is under "Ruled so far", each with its time. Everything else is my
     draft and waits on his read. Sources: Cora's mailbox /IDEAS 2280 and
     its children (tonight, 02:43-03:24), /IDEAS 1040 (the 11 Sep design,
     twelve children), /IDEAS 1640; the kin task KIN-2 (the Delta review);
     VoiceMode tasks VM-2270, VM-1010, VM-1282, VM-1715. -->

## Why

**An agent using VoiceMode is deaf while it works and stuck while it
listens.** `converse` is a turn: say something, then block until the human
stops talking, then return their words. While that call is open the agent
makes no tool calls, so nothing can reach it; while the agent is working,
nothing is listening. On the phone it is already better than this: a Delta
Chat call to an agent (kin) is an open microphone, the words arrive as they
are said, and the agent can talk over them. Mike's aim for this change,
voice 02:15 Thu 2026-09-24: *"the same experience locally with VoiceMode
ambient voice as we do with Delta Chat."*

What "the same experience" means, in his words tonight:

- *"You receive the voice via hooks, or by a backgrounded listener if the
  hooks aren't working because you've stopped, if you're idle."* (02:45)
- *"Make the conversation log a bit better, and the ride-along comes off the
  conversation log. It uses a seen cursor, and we have a hook that provides
  some of the stuff. Probably not all of it, because we should be
  context-conservative. It's already JSONL."* (03:19)
- *"Make converse have a listen mode where it gets backgrounded and doesn't
  return unless there's an end of turn detected that's more than a certain
  age, so that we're basically getting ride-along."* (03:20)
- *"This is a change in behaviour, so I do feel like we want to make a new
  tool."* (03:23)

The pattern exists twice already and this change is the third copy made
canonical: `pager listen` (sessionmail) is a backgrounded listener whose
return wakes an idle agent and whose ride-along hook feeds a busy one; the
standalone `deltachat` plugin writes `inbox.jsonl` and a hook delivers it.
VoiceMode has the hook plumbing (`voicemode claude hooks add`) and the JSONL
log (`~/.voicemode/logs/conversations/exchanges_YYYY-MM-DD.jsonl`, followed
by `voicemode exchanges tail`) but nothing that writes DURING a listen and
nothing that reads the log back into the agent.

## What changes

1. **A new tool, `listen`.** Long-lived. It starts capturing on a source
   (the microphone today; a call later), writes what it hears to the
   conversation log as it is recognised, and returns only when an end of
   turn is older than a configured age, an end word is heard, a ceiling is
   reached, or it fails. Its return is the wake for an idle agent; the log
   is the feed for a busy one. `converse` is unchanged.
2. **The conversation log becomes the ride-along's source.** One JSONL line
   per partial, turn or event, the same shape whatever the source. A
   per-session cursor marks what the agent has been shown. A VoiceMode hook
   prints the lines past the cursor on the agent's next tool call, within a
   budget.
3. **Every line says where it came from.** The input device (headphones,
   the Mac's microphone, the car) or the call and account. The Mac already
   knows; VoiceMode does not pass it on (VM-1010).
4. **Control words.** A wake word starts attention, an end word ends a turn.
   Both are events in the log; the model decides what they mean.
5. **`listen` shares `converse`'s ears.** One capture path, one VAD, one
   STT, one conch. Never a second copy of the pipeline.

## Ruled so far (Mike, by voice, Thu 2026-09-24)

- **02:43-02:48** A setup tool starts one long-running process on a sound
  source, mic or WebRTC. Words arrive by hook, or by the backgrounded
  listener when the agent is idle. Three modes: listening to me, wake word,
  transcribing my day. (Cora /IDEAS 2280)
- **03:04-03:06** Every stream is labelled with its device, in and out.
  Device identity is not person identity. (2280.6)
- **03:07** Two tasks: VoiceMode reports the input device (VM-1010);
  VoiceMode lays the words down as JSONL and the hook scoops them
  (VM-2270). (2280.7)
- **03:10-03:13** Build order: preview transcription first; a turn is a
  hint, the model decides; files are the default, mail an option, the hook
  reads whichever is configured; converse long-lived even on plain mic and
  speakers. (2280.8)
- **03:18** openspec lives in this repo; this is its first change. (Cora
  /RULINGS 3210)
- **03:27** *"New tool, listen. And when the model wants to speak, it just
  calls converse with skip STT; it doesn't listen. It just speaks, and the
  listener is feeding it with ride-along, or waking it."*
- **03:19-03:24** The ride-along comes off the conversation log, with a
  seen cursor and a context-conservative hook. Listen mode is backgrounded
  and returns on an end of turn older than a certain age. Whether a
  partial wakes an idle session is configurable, possibly only on a wake
  word. Control words: wake words and end words. Start with a listen that
  only appends to a file, as a new tool. (2280.10)

## Open questions, for Mike

Numbered so a reply can rule them one line each. My recommendation follows
each.

- **Q1 The name.** RULED 03:27: *"So new tool, listen."* Speaking is
  `converse` with `wait_for_response: false` (*"it just speaks"*), which
  exists today; no new speaking tool.
- **Q11 Fresh or shared.** He said at 03:27 *"listen can just be a fresh
  ambient listener that can be written from scratch"*; the *listen* spec
  says it must share `converse`'s capture path (one VAD, one STT client,
  one microphone stream). These can both hold: a new tool with its own
  loop, built on the same capture objects. They cannot if "from scratch"
  means a separate listener process with its own VAD and STT. Rec: fresh
  tool, shared ears; the second pipeline is the mistake kin already made.
- **Q2 The end-of-turn age.** How old must a detected end of turn be before
  `listen` returns? Rec: 8 s default, configurable; short enough that an
  idle agent answers within a breath, long enough to ride out a pause.
- **Q3 Wake on partial.** Off by default? Rec: off; on only with a wake
  word, which is what he floated at 03:21.
- **Q4 The control words.** Defaults? Rec: wake "hey Claude" (his), end
  "over" and "over and out" (his); per-agent additions in config.
- **Q5 The ceiling.** He put ~29 minutes on one MCP request; unmeasured.
  Rec: `listen` re-arms itself on a ceiling the way pager does, so the
  ceiling is a restart, not a gap; measure the real number in task 8.
- **Q6 One log or two.** Write the partials into `exchanges_*.jsonl`, or a
  sibling `heard_*.jsonl`? Rec: a sibling; the exchange log is one line per
  exchange and every reader of it assumes so.
- **Q7 The conch.** Does `listen` hold it for its whole life? Rec: no; the
  conch is for speaking. `listen` holds the microphone, and a `converse`
  from the same session shares its capture rather than opening a second.
- **Q8 The budget.** How much does the hook print per tool call? Rec: the
  lines since the cursor, newest last, capped at N tokens with a "+k more"
  tail, N in config, default 400.
- **Q9 Mail.** Ship the mail consumer in this change, or the next? Rec: the
  next. Files need nothing but VoiceMode, which is his reason for files
  first.
- **Q10 Idle wake.** When `listen` returns to wake an idle session, does
  the return carry the turn's text, or only "there is a turn; read the
  log"? Rec: the text of the aged turn and the cursor, nothing older; the
  hook has already shown the rest.

## Non-goals, and where they live

- **The Delta Chat transport**, calls in and out: kin (KIN-2), gated by
  DCP-2. kin's bridge writes the same line shape into the same log, so the
  hook is shared; that is the whole of "the same experience".
- **Moving the call pipeline into VoiceMode** (KIN-2 Recommendation 1): a
  later change. This one adds a tool, not a transport.
- **Encrypting audio and text to disk, the key on a hardware key**
  (/IDEAS 2280.1): future, by his word.
- **The output-device registry and speaking to a chosen target**
  (/IDEAS 2280.2): its own change; this one is ears, not mouth.
- **Streaming STT with a revisable tail** (WhisperLiveKit, /IDEAS 1040.12):
  the log's `partial` line is written so that it can carry a revisable
  tail later, but this change uses today's chunked whisper.

## Relations

- Tasks: **VM-2270** (words as JSONL for the hook; this change's build),
  **VM-1010** (report the input device), **VM-1282** (converse as carrier
  wave, May; superseded in part by the hook here), **VM-1715** (the
  always-on epic), **VM-1074** (ambient mode research, April).
- kin **KIN-2** (the Delta review), whose Next Steps candidate 4 is the
  same partials idea from the call side (kin's `calls.py` already closes a
  chunk on 0.35 s of quiet).
- Prior design: Cora /IDEAS 1040 (11 Sep, "continuous transcription rides
  along in the hook"), 1040.9 ("the ears are an arm"), 1040.11 ("silence
  does not find his sentences"), 1640 (devices, attention, routing, on/off).
