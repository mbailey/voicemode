"""In-process STT backends.

Most STT in VoiceMode happens over an OpenAI-compatible HTTP endpoint (whisper.cpp,
mlx-audio, or OpenAI cloud). Backends in this package are the exception: they run
inference *in-process*, selected via a custom scheme in ``VOICEMODE_STT_BASE_URLS``
(e.g. ``parakeet://local``). The STT failover loop dispatches to them instead of
building an HTTP client.
"""
