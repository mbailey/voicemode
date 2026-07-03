from voice_mode.tools.converse import _resolve_silence_release, _clamp_listen


def test_disable_alias_forces_minus_one():
    assert _resolve_silence_release(None, True) == -1.0
    assert _resolve_silence_release(60, True) == -1.0  # alias wins when set


def test_none_uses_config_default(monkeypatch):
    import voice_mode.tools.converse as c
    monkeypatch.setattr(c, "SILENCE_RELEASE_SEC", 0.0)
    assert _resolve_silence_release(None, False) == 0.0


def test_explicit_value_passthrough():
    assert _resolve_silence_release(60, False) == 60.0


def test_clamp_listen_caps_at_300():
    assert _clamp_listen(500) == 300.0
    assert _clamp_listen(180) == 180.0
