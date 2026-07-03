import importlib


def _reload_config(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import voice_mode.config as cfg
    return importlib.reload(cfg)


def test_silence_release_sec_default_zero(monkeypatch):
    cfg = _reload_config(monkeypatch)
    assert cfg.SILENCE_RELEASE_SEC == 0.0


def test_significance_threshold_default(monkeypatch):
    cfg = _reload_config(monkeypatch)
    assert cfg.SIGNIFICANCE_THRESHOLD_SEC == 2.0


def test_default_listen_duration_is_180(monkeypatch):
    cfg = _reload_config(monkeypatch)
    assert cfg.DEFAULT_LISTEN_DURATION == 180.0


def test_max_listen_duration_hard_cap(monkeypatch):
    cfg = _reload_config(monkeypatch)
    assert cfg.MAX_LISTEN_DURATION == 300.0


def test_silence_release_sec_env_override(monkeypatch):
    cfg = _reload_config(monkeypatch, VOICEMODE_SILENCE_RELEASE_SEC="60")
    assert cfg.SILENCE_RELEASE_SEC == 60.0
