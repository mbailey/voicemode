"""Hostname matching for provider base URLs (VM-2484).

A substring test such as ``"openai.com" in url`` is true for
``https://evil.example/api.openai.com`` and ``https://api.openai.com.evil.example``,
so it cannot say which host a URL points at (CodeQL
``py/incomplete-url-substring-sanitization``). These helpers parse the URL and
compare the *hostname* instead: an exact match, or a true subdomain
(``.endswith("." + domain)``).
"""

from typing import Optional
from urllib.parse import urlparse

OPENAI_DOMAIN = "openai.com"


def url_hostname(url: Optional[str]) -> Optional[str]:
    """Return the lower-cased hostname of ``url``, or ``None`` if it has none.

    A URL written without a scheme (``api.openai.com/v1``) is parsed as if it
    had one, so its host is still found rather than read as a path.
    """
    if not url or not isinstance(url, str):
        return None
    candidate = url.strip()
    if "://" not in candidate:
        candidate = "//" + candidate
    try:
        host = urlparse(candidate).hostname
    except ValueError:
        return None
    if not host:
        return None
    return host.rstrip(".")


def host_matches(url: Optional[str], domain: str) -> bool:
    """True when ``url``'s host is ``domain`` itself or a subdomain of it."""
    host = url_hostname(url)
    if host is None:
        return False
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)


def is_openai_url(url: Optional[str]) -> bool:
    """True when ``url`` points at an OpenAI host (``openai.com`` or a subdomain)."""
    return host_matches(url, OPENAI_DOMAIN)


ELEVENLABS_DOMAIN = "elevenlabs.io"


def is_elevenlabs_url(url: Optional[str]) -> bool:
    """True when ``url`` points at an ElevenLabs host (``elevenlabs.io`` or a subdomain)."""
    return host_matches(url, ELEVENLABS_DOMAIN)
