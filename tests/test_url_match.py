"""Hostname matching for provider URLs (VM-2484, CodeQL py/incomplete-url-substring-sanitization).

The old checks were ``"openai.com" in url``, which a spoofed URL passes. These
tests pin the parsed-hostname behaviour of ``voice_mode.url_match`` and of the
call sites that now use it.
"""

import pytest

from voice_mode.provider_discovery import detect_provider_type
from voice_mode.url_match import host_matches, is_openai_url, url_hostname


class TestUrlHostname:
    @pytest.mark.parametrize(
        "url, host",
        [
            ("https://api.openai.com/v1", "api.openai.com"),
            ("https://API.OpenAI.com/v1", "api.openai.com"),
            ("https://api.openai.com./v1", "api.openai.com"),
            ("http://127.0.0.1:8880/v1", "127.0.0.1"),
            ("http://localhost:2022/v1", "localhost"),
            ("api.openai.com/v1", "api.openai.com"),
            ("https://user:pw@api.openai.com:443/v1", "api.openai.com"),
            ("http://[::1]:8880/v1", "::1"),
        ],
    )
    def test_extracts_host(self, url, host):
        assert url_hostname(url) == host

    @pytest.mark.parametrize("url", [None, "", "   ", "https://", "/v1/audio", 42])
    def test_no_host(self, url):
        assert url_hostname(url) is None

    def test_malformed_ipv6_is_no_host(self):
        # urlparse raises ValueError on an unclosed bracket; that is "no host".
        assert url_hostname("http://[::1/v1") is None


class TestHostMatches:
    def test_exact_and_subdomain(self):
        assert host_matches("https://openai.com/v1", "openai.com")
        assert host_matches("https://api.openai.com/v1", "openai.com")
        assert host_matches("https://a.b.openai.com/v1", "openai.com")

    def test_domain_argument_is_normalised(self):
        assert host_matches("https://api.openai.com/v1", "OpenAI.com.")

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.com/api.openai.com",          # host in the path
            "https://api.openai.com.evil.com/v1",       # host as a prefix
            "https://evilopenai.com/v1",                # suffix without a dot boundary
            "https://evil.com/?next=https://api.openai.com",  # host in the query
            "https://evil.com/#api.openai.com",         # host in the fragment
            "https://api.openai.com@evil.com/v1",       # host as userinfo
            "https://openai.com.evil.com/v1",
            "http://127.0.0.1:8880/openai.com/v1",
        ],
    )
    def test_spoofs_do_not_match(self, url):
        assert not host_matches(url, "openai.com")
        assert not is_openai_url(url)


class TestIsOpenaiUrl:
    @pytest.mark.parametrize(
        "url", ["https://api.openai.com/v1", "https://openai.com", "api.openai.com/v1"]
    )
    def test_openai(self, url):
        assert is_openai_url(url)

    @pytest.mark.parametrize(
        "url",
        [None, "", "http://127.0.0.1:8880/v1", "http://localhost:2022/v1",
         "https://api.cartesia.ai/tts"],
    )
    def test_not_openai(self, url):
        assert not is_openai_url(url)


class TestCallSites:
    """The call sites CodeQL flagged now decide by hostname."""

    def test_detect_provider_type_rejects_spoofs(self):
        assert detect_provider_type("https://api.openai.com/v1") == "openai"
        assert detect_provider_type("https://evil.com/api.openai.com") != "openai"
        assert detect_provider_type("https://api.openai.com.evil.com/v1") != "openai"

    @pytest.mark.asyncio
    async def test_discover_voices_seeds_only_real_openai(self, monkeypatch):
        from voice_mode.provider_discovery import ProviderRegistry

        registry = ProviderRegistry()
        voices = await registry._discover_voices("https://api.openai.com/v1", client=None)
        assert voices == ["alloy", "echo", "fable", "nova", "onyx", "shimmer"]

        # A spoofed host is not OpenAI, so it is probed like any other
        # endpoint (here: the probe fails) instead of getting OpenAI's seed.
        import httpx

        probed = []

        class _Boom:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url):
                probed.append(url)
                raise httpx.ConnectError("no network in tests")

        monkeypatch.setattr("voice_mode.provider_discovery.httpx.AsyncClient", _Boom)
        spoofed = await registry._discover_voices("https://api.openai.com.evil.com/v1", client=None)
        assert spoofed == []
        assert probed == ["https://api.openai.com.evil.com/v1/audio/voices"]
