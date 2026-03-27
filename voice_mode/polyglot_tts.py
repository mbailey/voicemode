"""
Polyglot TTS - Language-aware text-to-speech synthesis.

Detects language segments within text (e.g., English words inside Portuguese sentences)
and synthesizes each segment with the appropriate voice, then concatenates the audio.

Controlled by:
  VOICEMODE_POLYGLOT=true|false        (default: false)
  VOICEMODE_POLYGLOT_PT_VOICE=pf_dora  (voice for Portuguese segments)
  VOICEMODE_POLYGLOT_EN_VOICE=af_sky   (voice for English segments)
  VOICEMODE_POLYGLOT_PRIMARY_LANG=pt   (primary language: pt or en)
  VOICEMODE_POLYGLOT_MIN_EN_WORDS=2    (min consecutive English words to switch voice)
"""

import logging
import os
import re
from typing import List, Tuple, Optional
import io

logger = logging.getLogger("voicemode")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLYGLOT_ENABLED = os.environ.get("VOICEMODE_POLYGLOT", "false").lower() in ("true", "1", "yes")
POLYGLOT_PT_VOICE = os.environ.get("VOICEMODE_POLYGLOT_PT_VOICE", "pf_dora")
POLYGLOT_EN_VOICE = os.environ.get("VOICEMODE_POLYGLOT_EN_VOICE", "af_sky")
POLYGLOT_PRIMARY_LANG = os.environ.get("VOICEMODE_POLYGLOT_PRIMARY_LANG", "pt").lower()
POLYGLOT_MIN_EN_WORDS = int(os.environ.get("VOICEMODE_POLYGLOT_MIN_EN_WORDS", "2"))

# ---------------------------------------------------------------------------
# Language detection helpers
# ---------------------------------------------------------------------------

# Portuguese-exclusive characters and patterns
_PT_ACCENTS = re.compile(r'[ãõçáéíóúâêôàÃÕÇÁÉÍÓÚÂÊÔÀ]')

# Common Portuguese function words (stopwords)
_PT_STOPWORDS = frozenset([
    'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas',
    'de', 'do', 'da', 'dos', 'das', 'no', 'na', 'nos', 'nas',
    'ao', 'aos', 'à', 'às', 'pelo', 'pela', 'pelos', 'pelas',
    'em', 'com', 'sem', 'por', 'para', 'sobre', 'entre', 'até',
    'que', 'se', 'não', 'sim', 'mas', 'ou', 'e', 'nem',
    'quando', 'onde', 'como', 'porque', 'pois', 'então', 'assim',
    'isso', 'isto', 'aqui', 'ali', 'lá', 'aquele', 'aquela',
    'eu', 'tu', 'ele', 'ela', 'nós', 'vós', 'eles', 'elas', 'você', 'vocês',
    'meu', 'minha', 'teu', 'tua', 'seu', 'sua', 'nosso', 'nossa',
    'muito', 'pouco', 'mais', 'menos', 'bem', 'mal', 'já', 'ainda',
    'ser', 'estar', 'ter', 'ter', 'haver', 'fazer', 'ir', 'vir',
    'foi', 'era', 'tem', 'teve', 'vai', 'pode', 'deve', 'quer',
    'agora', 'antes', 'depois', 'sempre', 'nunca', 'talvez',
    'tudo', 'nada', 'algo', 'alguém', 'ninguém',
])

# Common English stopwords / function words (clearly English)
_EN_STOPWORDS = frozenset([
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
    'for', 'of', 'with', 'by', 'from', 'into', 'through', 'during',
    'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'must',
    'that', 'this', 'these', 'those', 'which', 'who', 'whom',
    'it', 'its', 'we', 'they', 'you', 'he', 'she', 'i', 'me',
    'my', 'your', 'his', 'her', 'our', 'their', 'its',
    'what', 'when', 'where', 'why', 'how',
    'all', 'each', 'every', 'some', 'any', 'few', 'more', 'most',
    'also', 'just', 'only', 'even', 'still', 'already', 'yet',
    'if', 'then', 'than', 'so', 'as', 'while', 'because', 'since',
    'not', 'no', 'yes',
])

# English-only digraphs and patterns (rare/absent in Portuguese)
_EN_PATTERNS = re.compile(r'\b\w*(?:th|wh|ck|gh|sh|ch|ph|qu|wr|kn|gn|mn)\w*\b', re.IGNORECASE)

# English-only word endings
_EN_ENDINGS = re.compile(
    r'\b\w+(?:ing|tion|tions|ness|ment|ful|less|ish|ous|ive|ation|ity|ed|er|est|'
    r'ify|ize|ise|ary|ery|ory|ward|wards|ship|hood|dom|ism|ist)\b',
    re.IGNORECASE
)

# Common English tech/programming words that appear inside PT text
_EN_TECH_WORDS = frozenset([
    # Version control
    'branch', 'branches', 'commit', 'commits', 'merge', 'pull', 'push', 'rebase',
    'checkout', 'stash', 'diff', 'patch', 'fork', 'clone', 'remote', 'upstream',
    'tag', 'release', 'changelog', 'pipeline',
    # Dev tools
    'deploy', 'deployment', 'build', 'rebuild', 'test', 'tests', 'debug', 'debugger',
    'lint', 'linter', 'format', 'formatter', 'bundle', 'bundler', 'package',
    'install', 'uninstall', 'upgrade', 'downgrade', 'setup', 'scaffold',
    # Architecture
    'backend', 'frontend', 'fullstack', 'microservice', 'monolith', 'serverless',
    'middleware', 'gateway', 'proxy', 'load', 'balancer', 'cache', 'queue',
    'worker', 'broker', 'scheduler', 'job', 'batch', 'stream', 'event',
    # APIs & Protocols
    'api', 'rest', 'graphql', 'grpc', 'websocket', 'webhook', 'endpoint',
    'request', 'response', 'payload', 'header', 'token', 'auth', 'oauth',
    'jwt', 'cors', 'csrf', 'ssl', 'tls', 'http', 'https', 'json', 'xml',
    # Database
    'database', 'query', 'queries', 'index', 'indexes', 'migration', 'seed',
    'schema', 'model', 'entity', 'relation', 'join', 'transaction',
    # Cloud / Infra
    'docker', 'container', 'image', 'pod', 'cluster', 'node', 'instance',
    'bucket', 'storage', 'function', 'lambda', 'trigger', 'cron',
    # Languages / Frameworks
    'react', 'angular', 'vue', 'next', 'nuxt', 'nest', 'express', 'fastapi',
    'django', 'rails', 'spring', 'laravel', 'flutter', 'kotlin', 'swift',
    'python', 'javascript', 'typescript', 'golang', 'rust', 'java', 'ruby',
    'scala', 'elixir', 'haskell', 'clojure', 'erlang', 'lua', 'bash',
    # Project management
    'sprint', 'backlog', 'kanban', 'scrum', 'story', 'epic', 'ticket',
    'issue', 'review', 'feedback', 'blocker', 'blocker', 'standup',
    # UI/UX
    'component', 'layout', 'theme', 'style', 'stylesheet', 'template',
    'modal', 'popup', 'toast', 'tooltip', 'dropdown', 'sidebar', 'navbar',
    'button', 'input', 'form', 'table', 'grid', 'flex', 'breakpoint',
    # General tech
    'config', 'settings', 'env', 'environment', 'variable', 'secret',
    'log', 'logs', 'logger', 'metric', 'metrics', 'trace', 'tracing',
    'timeout', 'retry', 'fallback', 'circuit', 'breaker', 'rate', 'limit',
    'benchmark', 'profiler', 'memory', 'cpu', 'thread', 'async', 'await',
    'callback', 'promise', 'future', 'coroutine', 'concurrency',
    'singleton', 'factory', 'observer', 'strategy', 'adapter', 'decorator',
    # Tools & Platforms
    'github', 'gitlab', 'bitbucket', 'jira', 'confluence', 'slack',
    'discord', 'notion', 'figma', 'vercel', 'netlify', 'heroku', 'aws',
    'gcp', 'azure', 'cloudflare', 'datadog', 'sentry', 'grafana',
    # Types / concepts
    'string', 'number', 'boolean', 'integer', 'float', 'array', 'object',
    'null', 'undefined', 'true', 'false', 'void', 'interface', 'type',
    'class', 'struct', 'enum', 'generic', 'template', 'namespace',
    'import', 'export', 'module', 'library', 'dependency', 'version',
])


def _score_word_english(word: str) -> float:
    """
    Return a score 0.0–1.0 indicating how likely a word is English.
    1.0 = definitely English, 0.0 = definitely not English.
    """
    clean = word.strip(".,;:!?\"'()[]{}").lower()
    if not clean:
        return 0.0

    # Portuguese accent characters → definitely not English
    if _PT_ACCENTS.search(clean):
        return 0.0

    # Known Portuguese stopword → definitely not English
    if clean in _PT_STOPWORDS:
        return 0.0

    # Known English stopword → definitely English
    if clean in _EN_STOPWORDS:
        return 1.0

    # Known English tech word → definitely English
    if clean in _EN_TECH_WORDS:
        return 1.0

    # English-only digraph patterns
    if _EN_PATTERNS.match(clean):
        return 0.8

    # English-only word endings (only if word is long enough)
    if len(clean) >= 5 and _EN_ENDINGS.match(clean):
        return 0.7

    # Mixed / ambiguous (numbers, proper nouns, short words)
    return 0.0


def detect_language_segments(text: str, primary_lang: str = "pt") -> List[Tuple[str, str]]:
    """
    Split text into [(lang, segment)] pairs.

    Args:
        text: Input text (may contain mixed PT/EN content)
        primary_lang: The dominant language ("pt" or "en")

    Returns:
        List of (language_code, text_segment) tuples.
        language_code is "pt" or "en".
    """
    if not text.strip():
        return [(primary_lang, text)]

    # Split into tokens preserving whitespace/punctuation
    # Strategy: split on sentence boundaries first, then word by word
    tokens = re.split(r'(\s+)', text)

    # Score each non-whitespace token
    scored: List[Tuple[str, float]] = []
    for tok in tokens:
        if tok.strip():
            score = _score_word_english(tok)
            scored.append((tok, score))
        else:
            # Whitespace - inherits previous token's language
            scored.append((tok, -1.0))  # -1 = whitespace marker

    # Assign language to each token
    langs: List[str] = []
    for tok, score in scored:
        if score < 0:
            # Whitespace: copy previous language
            langs.append(langs[-1] if langs else primary_lang)
        elif score >= 0.5:
            langs.append("en")
        else:
            langs.append(primary_lang)

    # Apply minimum consecutive English words rule
    # Convert isolated English words back to primary_lang
    min_en = POLYGLOT_MIN_EN_WORDS
    if min_en > 1:
        # Count consecutive EN tokens (non-whitespace)
        i = 0
        result_langs = list(langs)
        word_positions = [j for j, (tok, sc) in enumerate(scored) if sc >= 0]
        for wi, pos in enumerate(word_positions):
            if langs[pos] == "en":
                # Count how many consecutive EN words starting here
                run = 0
                for wj in range(wi, len(word_positions)):
                    if langs[word_positions[wj]] == "en":
                        run += 1
                    else:
                        break
                if run < min_en:
                    # Too short: revert to primary
                    for wj in range(wi, wi + run):
                        result_langs[word_positions[wj]] = primary_lang
        langs = result_langs

    # Group consecutive same-language tokens into segments
    segments: List[Tuple[str, str]] = []
    current_lang = langs[0] if langs else primary_lang
    current_text = ""
    for (tok, _), lang in zip(scored, langs):
        if lang == current_lang:
            current_text += tok
        else:
            if current_text.strip():
                segments.append((current_lang, current_text))
            elif current_text:
                # Pure whitespace between segments: attach to previous
                if segments:
                    prev_lang, prev_text = segments[-1]
                    segments[-1] = (prev_lang, prev_text + current_text)
            current_lang = lang
            current_text = tok

    if current_text.strip():
        segments.append((current_lang, current_text))
    elif current_text and segments:
        prev_lang, prev_text = segments[-1]
        segments[-1] = (prev_lang, prev_text + current_text)

    return segments if segments else [(primary_lang, text)]


def get_voice_for_lang(lang: str) -> str:
    """Return the configured voice for a given language code."""
    if lang == "en":
        return POLYGLOT_EN_VOICE
    return POLYGLOT_PT_VOICE


# ---------------------------------------------------------------------------
# Polyglot synthesis
# ---------------------------------------------------------------------------

async def polyglot_text_to_speech(
    text: str,
    base_url: str,
    model: str,
    api_key: str,
    audio_format: str = "wav",
    speed: Optional[float] = None,
) -> Optional[bytes]:
    """
    Synthesize text with language-appropriate voices and return concatenated audio bytes.

    Falls back to None if anything fails (caller should use regular TTS).

    Args:
        text: The text to synthesize (may contain mixed PT/EN)
        base_url: Kokoro TTS endpoint base URL
        model: TTS model name (e.g. "tts-1")
        api_key: API key (may be dummy for local)
        audio_format: Audio format to request ("wav", "mp3", "pcm")
        speed: Speech speed multiplier

    Returns:
        Concatenated audio bytes, or None on failure.
    """
    from pydub import AudioSegment
    from openai import AsyncOpenAI
    import httpx

    segments = detect_language_segments(text, POLYGLOT_PRIMARY_LANG)
    logger.info(f"Polyglot TTS: {len(segments)} segment(s) detected")
    for lang, seg in segments:
        logger.debug(f"  [{lang}] {seg[:60]!r}{'...' if len(seg) > 60 else ''}")

    # If only one segment with the primary language, no need for polyglot
    if len(segments) == 1 and segments[0][0] == POLYGLOT_PRIMARY_LANG:
        logger.debug("Polyglot TTS: single primary-language segment, skipping")
        return None

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
        ),
        max_retries=0,
    )

    combined = AudioSegment.empty()
    synthesis_format = audio_format if audio_format in ("mp3", "wav", "opus", "flac") else "wav"

    try:
        for lang, segment_text in segments:
            if not segment_text.strip():
                continue

            voice = get_voice_for_lang(lang)
            params = {
                "model": model,
                "input": segment_text,
                "voice": voice,
                "response_format": synthesis_format,
            }
            if speed is not None:
                params["speed"] = speed

            logger.debug(f"Polyglot TTS synthesizing [{lang}] with voice {voice!r}: {segment_text[:40]!r}")
            async with client.audio.speech.with_streaming_response.create(**params) as resp:
                audio_bytes = await resp.read()

            segment_audio = AudioSegment.from_file(
                io.BytesIO(audio_bytes), format=synthesis_format
            )
            combined += segment_audio

        if len(combined) == 0:
            return None

        output_buf = io.BytesIO()
        combined.export(output_buf, format=synthesis_format)
        result = output_buf.getvalue()
        logger.info(f"Polyglot TTS: combined audio {len(result)} bytes ({len(combined)}ms)")
        return result

    except Exception as exc:
        logger.warning(f"Polyglot TTS failed, falling back to regular TTS: {exc}")
        return None
    finally:
        await client._client.aclose()
