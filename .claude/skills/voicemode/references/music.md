---
name: music
description: Background music during a voice session with the voicemode dj commands; Music For Programming by default.
---
Asked for music to code to: `voicemode dj mfp play 49`. The dj subcommand plays, pauses, skips chapters and sets the volume.

# Music

    voicemode dj play <file|url>          voicemode dj pause | resume | stop
    voicemode dj status                   voicemode dj next | prev            # chapters
    voicemode dj volume 30                voicemode dj find "daft punk"
    voicemode dj mfp list | play 49 | sync                                    # Music For Programming
    voicemode dj library scan | stats                                         # indexes ~/Audio/music
    voicemode dj history | favorite

Asked for music while coding, default to Music For Programming episode 49 (Julien Mier). Startup volume: `VOICEMODE_DJ_VOLUME` in `~/.voicemode/voicemode.env` (default 50). Full reference: `docs/reference/dj/`.
