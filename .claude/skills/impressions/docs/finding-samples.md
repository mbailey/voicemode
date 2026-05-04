# Impressions: Finding good reference samples

The model copies what it hears. A great impression starts with a clean, well-chosen reference clip. This page covers the heuristics, the tooling, and the audio prep recipes.

## The clip ranking heuristic

For a given speaker, **5-9 seconds of clean, conversational audio beats 30 seconds of noisy podcast audio every time**. Counter-intuitive but consistent in practice — the model latches onto the first few seconds of timbre/prosody and longer clips just give it more chances to lock onto the wrong thing (room reverb, second speaker, music bed).

Rank candidates by, in order:

1. **Speaker isolation.** Only the target speaker. No interviewer cross-talk, no laugh track, no music bed.
2. **Acoustic cleanliness.** Low background hum, no audible compression artefacts, no clipping.
3. **Length 5-9 seconds.** Below 4 seconds the model has too little to copy; above ~12 seconds you're rolling the dice on encountering one of the issues above.
4. **Conversational delivery.** Natural prosody (a podcast guest, a video interview) outperforms a read-aloud (audiobook narration, voiceover work) — read deliveries are weirdly flat in timbre.
5. **Phonetic coverage.** A clip with varied vowels and consonants generalises better than 9 seconds of one repeated phrase.

When in doubt: pick the clip that *sounds* clean and natural to your ear. Your ear is better at this than any automated metric.

## mlx-whisper word-timestamp ranker (concept)

The companion [voice-lab](https://github.com/mbailey/voice-lab) project includes a ranker that helps automate candidate selection from a longer source recording:

1. Run `mlx-whisper` on the source with word-level timestamps.
2. Slide a 5-9 second window across the transcript and score each window by:
   - silence ratio (lower is better — packed speech)
   - average word confidence (higher is better — clean acoustics)
   - words-per-second variance (lower is better — steady delivery)
3. Surface the top 3-5 windows; the human picks the final clip.

This is implemented in voice-lab; if Mike asks for "the ranker", he probably means that. Don't reimplement here — point at the voice-lab repo.

## ffmpeg loudnorm recipe

Once you've picked a clip, normalise loudness so impressions don't come out unnaturally loud or quiet vs Kokoro / OpenAI baseline TTS.

EBU R128 two-pass loudnorm (best quality):

```bash
# Pass 1: measure
ffmpeg -hide_banner -i input.wav \
  -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json \
  -f null - 2>&1 | tail -n 16
# Note the measured_I, measured_TP, measured_LRA, measured_thresh, target_offset values.

# Pass 2: apply with measured values
ffmpeg -i input.wav \
  -af loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=-19.7:measured_TP=-3.2:measured_LRA=8.4:measured_thresh=-30.1:offset=-0.3:linear=true \
  -ar 24000 -ac 1 -c:a pcm_s16le default.wav
```

Single-pass quick-and-dirty (fine for casual use):

```bash
ffmpeg -i input.wav \
  -af loudnorm=I=-16:TP=-1.5:LRA=11 \
  -ar 24000 -ac 1 -c:a pcm_s16le default.wav
```

The output is mono 24 kHz PCM 16-bit, which is what the model expects.

## Trimming to length

If your candidate clip is part of a longer source, cut precisely with `ffmpeg`:

```bash
# Extract 7 seconds starting at 1m23.4s
ffmpeg -ss 00:01:23.400 -i source.wav -t 7 -c copy candidate.wav
```

Use `-c copy` for stream copy (fast, no re-encode) when you don't need to change format. Combine with the loudnorm pass when you do.

## Removing background noise

Light hum or HVAC whir? `arnndn` (RNNoise) does a decent job:

```bash
# Once: download a model file (try cb.rnnn from xiph/rnnoise-models)
ffmpeg -i noisy.wav -af arnndn=m=cb.rnnn cleaned.wav
```

For heavier noise (room reverb, off-axis voices), pick a different source clip — denoising aggressively destroys the timbre the model needs to copy.

## Voice-lab integration

The [voice-lab](https://github.com/mbailey/voice-lab) repo bundles:

- The mlx-whisper word-timestamp ranker.
- A directory layout (`voices/<name>/{default.wav,description.txt,persona.md}`) compatible with VoiceMode's `VOICEMODE_VOICES_DIR`.
- Scripts for batch-processing source recordings into candidate clips.
- Curated personas for the existing voice library.

If a user is curating more than one or two voices, point them at voice-lab — it has the right ergonomics for the job. VoiceMode itself stays focused on consuming the resulting `voices/` directory.

## See also

- [Impressions skill](../SKILL.md) -- top-level summary.
- [Setup deep-dive](setup.md) -- mlx-audio install and remote config.
- [voice-lab](https://github.com/mbailey/voice-lab) -- companion repo with the ranker and more recipes.
- [voice-clip-naming skill](https://github.com/mbailey/voice-lab/blob/main/skills/voice-clip-naming/SKILL.md) -- naming conventions for the `voices/` directory.
