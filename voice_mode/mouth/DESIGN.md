# mouth: design, against Mike's asks of 21:21-21:25 Thu 2026-09-24

Pip, 21:28. The source is Cora's capture `<1790249197.4456.2038@m5.session-mail>`
(heard seq 7207, walking back to the van). Each ask gets its status and a
proposed shape. Nothing here is live until Mike says so.

## Where each ask stands

1. **Several agents, one mouth.** Works NOW. There is one queue, and each
   line carries `agent` and `session`. `--channel` / `$VOICEMODE_MOUTH_PAN`
   can give each agent its own ear.
2. **Status back.** Works NOW. `said` carries what played, where it was cut
   and why, and `say --wait` returns it. Over mail (8), the `said` becomes
   the reply.
3. **Amend or retract before it's spoken.** BUILT (dev, `aa4af354`):
   `mouth amend UTT TEXT` rewrites a queued line in place, keeping its
   position. `mouth retract UTT` drops it, and if it's already playing, cuts
   it. Either way a `said reason=retracted` closes it. It's the `Supersedes:`
   of the queue.
4. **Interrupts.** BUILT (dev, `aa4af354`): `say --next` jumps the queue, and
   `say --now` cuts the current line (`reason=interrupted`) and speaks at
   once. The cut is aimed at the one playing utterance, never the queue
   behind it.
5. **Sounds, a file or part of one.** BUILT (dev, this commit):
   `mouth play FILE|URL [--start S] [--end S]`. It decodes through ffmpeg
   into the same queue, so it gets the same stop, priority, pan and log.
6. **DJ inside the mouth.** SPLIT:
   - **ducking** is BUILT (dev, this commit, opt-in `$VOICEMODE_MOUTH_DUCK=PCT`). The
     DJ's mpv is lowered at `saying` and restored at `said`, through
     `DJController.volume()`. No mixing is needed, because mpv stays its own
     stream.
   - **playlists** exist already: `voicemode dj play`.
   - **the same music on several speakers, in time**, is NOT started. It
     needs clock-aligned start across devices, which is the several-device
     work (legs) plus an aligned start time. Big.
7. **L-cuts and J-cuts** (sound leading or trailing the picture). NOT
   started. It needs two streams overlapping on a timeline, i.e. a mixer.
   Today's model is "one playing at a time". Proposal: a later `at:` field
   (start at t, or at an offset from another utterance's start or end),
   with the player mixing. Big, and it wants the video use case in front
   of us.
8. **Mail as the transport.** RULED by Mike at 21:40 ("mail feeds mouth",
   slipbox 515) and BUILT (dev, this commit): `mouth mail` watches
   `~/.mail/agents/mouth` (`mouth@m5`, box made and mapped 21:42).
   - body = the text (lightly un-markdowned); an empty body speaks the Subject
   - `Supersedes:` amends a line not yet spoken; if it has been spoken, the
     correction is queued as news
   - `Supersedes:` with an empty body retracts
   - `Importance: high` or `X-Mouth-Priority: next|now` sets the priority
   - `X-Mouth-File` / `-Start` / `-End` plays a sound
   - `X-Mouth-Voice|Speed|Device|Channel|Pan` set per-line options
   - agent = From, session = `X-Session-From`, and `mail_id` goes on
     saying/said

   Only a From on this host, or in `$VOICEMODE_MOUTH_MAIL_ALLOW`, is
   spoken. It's a From check; verifying the signature is the follow-up.
   **Measured end to end through postfix at 21:47:** send to queued in
   244 ms, then queued to first frame in 323 ms (cold player).
   Not yet: a `said` mailed back as a reply (the heard log carries it).

## The shape it keeps

- One queue, one player, one line at a time. Stacked lines are gapless
  (prefetch). 7 is the first ask that breaks "one at a time", and it
  should be designed with a real video in hand.
- Every utterance ends in exactly one `said`, whatever happens to it:
  done, stop, barge-in, interrupted, retracted, device-absent,
  device-lost or error.
- The heard log is the timeline, and the mouth writes to it only through
  `heard.append`.
