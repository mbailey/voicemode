"""
Simple failover implementation for voice-mode.

This module provides a direct try-and-failover approach without health checks.
Connection refused errors are instant, so there's no performance penalty.
"""

import asyncio
import logging
import os
from typing import Optional, Tuple, Dict, Any
from openai import AsyncOpenAI, APIConnectionError, APIStatusError
from .openai_error_parser import OpenAIErrorParser
from .provider_discovery import is_local_provider

from .config import (
    TTS_BASE_URLS, STT_BASE_URLS, OPENAI_API_KEY, STT_PROMPT, WHISPER_LANGUAGE,
    STT_RETRY_ATTEMPTS, STT_RETRY_BACKOFF, STT_RETRY_BACKOFF_MAX,
)
from .provider_discovery import detect_provider_type, EndpointInfo
from .providers import _select_stt_model_for_endpoint, _select_tts_model_for_endpoint

logger = logging.getLogger("voicemode")


class UnmappedProviderVoiceError(RuntimeError):
    """Loud per-endpoint refusal (VM-1901 design.md §3.2.7, scope per VM-2190).

    Raised when a provider-native voice reaches an OpenAI endpoint that has
    no mapping for it. Since VM-2190 widened ``resolve_voice()``'s gate to
    every voice a configured endpoint claims (the full kokoro set, not just
    the 7 mapped names), this is an EXPECTED failover case, not only upstream
    drift: ``voice="af_nicole"`` with kokoro/mlx-audio down legitimately lands
    here. Raising skips THIS endpoint (failover continues to the next one)
    instead of silently substituting "alloy" — the identity break VM-1901
    exists to prevent.
    """


def _resolve_tts_endpoints(voice, ref_text_override):
    """Resolve which TTS endpoints to try and the clone profile (if any).

    VM-1901: this is where every "unresolvable voice silently becomes Alloy"
    mouth used to live — ``is_clone_voice()``/``get_profile()`` returning
    False/None for anything they didn't recognise, falling straight through
    to the generic ``TTS_BASE_URLS`` chain. This now calls the TOTAL
    resolver (:func:`voice_profiles.resolve_voice`) directly: an
    unresolvable/ambiguous/undeclared-cast expression raises a
    ``VoiceResolutionError`` here, before any endpoint is tried, instead of
    reaching a provider at all.

    Clone/clip voices route directly to their own endpoint; an explicit
    ``ref_text`` override wins over the profile/sidecar transcript (VM-1278).
    A provider-native resolution (``kind="provider"``, e.g. an OpenAI/Kokoro
    voice name) falls through to the generic chain exactly as before — that
    is legitimate usage, not a fallback. Shared by the play
    (``simple_tts_failover``) and synth-only (``simple_tts_synthesize``)
    paths so endpoint selection stays identical between them.

    Returns:
        tuple: (endpoints_to_try, clone_profile, resolution)

    Raises:
        voice_profiles.VoiceResolutionError: the voice expression could not
            be resolved. Callers must catch this — see
            :func:`simple_tts_failover` / :func:`simple_tts_synthesize`.
    """
    from dataclasses import replace as _dc_replace
    from .voice_profiles import resolve_voice

    resolution = resolve_voice(voice)

    if resolution.kind in ("clone", "clip"):
        clone_profile = resolution.profile
        if ref_text_override is not None:
            clone_profile = _dc_replace(clone_profile, ref_text=ref_text_override)
            logger.info(f"Voice '{voice}': applying ref_text override ({len(ref_text_override)} chars)")
        logger.info(
            f"Voice '{voice}' resolved to {resolution.resolved!r} "
            f"(via={resolution.via}), routing to {clone_profile.base_url}"
        )
        return [clone_profile.base_url], clone_profile, resolution

    if ref_text_override is not None:
        logger.warning(
            f"ref_text override supplied but voice '{voice}' resolved to a "
            f"provider-native voice ({resolution.resolved!r}), not a clone — "
            f"override ignored"
        )
    return TTS_BASE_URLS, None, resolution


def _prepare_tts_endpoint(base_url, voice, model, clone_profile):
    """Build the client + select the voice/model for one TTS endpoint.

    Shared by the play and synth-only failover loops. Returns the configured
    ``AsyncOpenAI`` client plus the voice/model actually sent to the provider
    (clone voices pass through; OpenAI maps Kokoro voice names to equivalents).

    ``voice`` here MUST be ``resolution.resolved`` (the canonical id from
    :func:`voice_profiles.resolve_voice`), never the raw caller expression —
    review fix, VM-1901 observability-001. Passing the raw expression through
    reintroduced this slice's own headline bug one call deeper: for a cast
    (``"peep-show"`` resolving to member ``"peep-show/mark"``) or any other
    request-vs-resolved qualified/index/ambiguous-leaf path, the clone branch
    below did ``selected_voice = voice`` — the unresolved cast/leaf name,
    not the member that will actually sound — and that string is exactly
    what ends up in the exchange log's ``voice`` field (config['voice'] below)
    and, via ``resolution.resolved`` no longer matching what's shown, silently
    defeats the clash detector's "compare resolved ids" contract for the very
    cases (casts, qualified paths) this design exists to make correct.
    Provider-native resolutions are unaffected either way (``resolved ==
    requested`` for those by construction), so this only changes behavior for
    the cases that were wrong.

    Returns:
        tuple: (client, selected_voice, selected_model, provider_type,
        is_fallback, fallback_reason)

        ``is_fallback``/``fallback_reason`` (VM-1901 design.md §5.3) are set
        ONLY for the one legitimate substitution left in this function: a
        known Kokoro voice name mapped to its OpenAI equivalent because the
        endpoint chain failed over to OpenAI. Every other path (clone
        passthrough, an OpenAI-native name used on purpose, Kokoro itself)
        is ``is_fallback=False`` — under P1 the unresolvable-to-alloy
        population that made this hook meaningless is now structurally
        impossible, so ``is_fallback`` finally means one thing.
    """
    provider_type = detect_provider_type(base_url)
    api_key = OPENAI_API_KEY if provider_type == "openai" else (OPENAI_API_KEY or "dummy-key-for-local")
    is_fallback = False
    fallback_reason = None

    if clone_profile:
        # Clone voice: use profile's model and pass voice name through
        # (mlx-audio server accepts any voice string). The per-provider model
        # resolver deliberately does NOT run for clones (VM-1390).
        selected_voice = voice
        selected_model = clone_profile.model
        logger.info(f"Clone voice '{voice}': model={selected_model}")
    else:
        # Per-provider model resolution (VM-1390): pick the model id this
        # provider actually understands so a mixed TTS_BASE_URLS chain can fail
        # over (e.g. HF repo id to mlx-audio, "tts-1" to kokoro/openai). An
        # explicit caller model still wins inside the resolver.
        selected_model = _select_tts_model_for_endpoint(provider_type, model)
        if provider_type == "openai":
            # Map Kokoro voices to OpenAI equivalents, or use OpenAI default
            openai_voices = ["alloy", "echo", "fable", "nova", "onyx", "shimmer"]
            if voice in openai_voices:
                selected_voice = voice
            else:
                voice_mapping = {
                    "af_sky": "nova",
                    "af_sarah": "nova",
                    "af_alloy": "alloy",
                    "am_adam": "onyx",
                    "am_echo": "echo",
                    "am_onyx": "onyx",
                    "bm_fable": "fable"
                }
                # VM-1901: this used to default unrecognised names to
                # "alloy" — the mechanism the alloy-fallback bug actually
                # rode in on. Raise instead of substituting; failover skips
                # this endpoint and moves on. VM-2190: with the resolver now
                # accepting every voice a configured endpoint claims, an
                # unmapped kokoro voice landing here (kokoro/mlx unreachable,
                # chain reached OpenAI) is an expected, loud skip — not
                # necessarily upstream drift.
                if voice not in voice_mapping:
                    raise UnmappedProviderVoiceError(
                        f"Voice {voice!r} has no OpenAI mapping and isn't an "
                        f"OpenAI-native name — this endpoint cannot speak it; "
                        f"skipping (no silent substitution)."
                    )
                selected_voice = voice_mapping[voice]
                # VM-1901: this IS the one legitimate fallback left in the
                # system (design.md §5.3) — a known Kokoro alias mapped to
                # its OpenAI equivalent because this endpoint is OpenAI, not
                # Kokoro. Record it as such, structurally distinct from the
                # bug case (which can no longer reach this line at all).
                is_fallback = True
                fallback_reason = f"endpoint-failover: {voice}→{selected_voice} (kokoro unreachable)"
                logger.info(f"Mapped voice {voice} to {selected_voice} for OpenAI")
        else:
            selected_voice = voice  # Use original voice for Kokoro
    logger.info(f"Endpoint {base_url} ({provider_type}): model={selected_model}")

    # Disable retries for local endpoints - they either work or don't
    max_retries = 0 if is_local_provider(base_url) else 2
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=30.0,  # Reasonable timeout
        max_retries=max_retries
    )
    return client, selected_voice, selected_model, provider_type, is_fallback, fallback_reason


async def simple_tts_failover(
    text: str,
    voice: str,
    model: Optional[str] = None,
    **kwargs
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Simple TTS failover - try each endpoint in order until one works.

    Returns:
        Tuple of (success, metrics, config)
    """
    logger.info(f"simple_tts_failover called with: text='{text[:50]}...', voice={voice}, model={model}")
    logger.info(f"kwargs: {kwargs}")

    from .core import text_to_speech
    from .conversation_logger import get_conversation_logger
    from .voice_profiles import VoiceResolutionError

    # Pull the optional ref_text override out of kwargs before it gets
    # forwarded to text_to_speech (which has no ref_text param). None means
    # "no override" — use the profile/sidecar transcript as resolved.
    ref_text_override = kwargs.pop("ref_text", None)

    # Track attempted endpoints and their errors
    attempted_endpoints = []

    # Get conversation ID from logger
    conversation_logger = get_conversation_logger()
    conversation_id = conversation_logger.conversation_id

    # Check if this is a clone voice — if so, route directly to its endpoint.
    # VM-1901: an unresolvable voice raises HERE, before any endpoint is
    # tried — no TTS request issued, no cross-provider substitution possible.
    try:
        endpoints_to_try, clone_profile, resolution = _resolve_tts_endpoints(voice, ref_text_override)
    except VoiceResolutionError as e:
        logger.error(f"Voice resolution failed for {voice!r}: {e}")
        return False, None, {
            'error_type': 'voice_resolution_failed',
            'error': str(e),
            'attempted_endpoints': [],
        }

    # Try each TTS endpoint in order
    logger.info(f"simple_tts_failover: Starting with endpoints = {endpoints_to_try}")
    for base_url in endpoints_to_try:
        logger.info(f"Trying TTS endpoint: {base_url}")

        # Wrap in try/catch to get actual exception details. _prepare_tts_endpoint
        # can itself raise (VM-1901's defensive UnmappedProviderVoiceError) —
        # treated the same as any other per-endpoint failure so failover
        # continues to the next endpoint.
        last_exception = None
        provider_type = detect_provider_type(base_url)
        selected_voice = voice
        selected_model = model
        try:
            # Review fix (VM-1901 observability-001): pass resolution.resolved,
            # not the raw `voice` expression -- see _prepare_tts_endpoint's
            # docstring. For a cast/qualified request this is the difference
            # between "peep-show" (unresolved) and "peep-show/mark" (what
            # will actually sound) ending up in the exchange log.
            client, selected_voice, selected_model, provider_type, is_fallback, fallback_reason = _prepare_tts_endpoint(
                base_url, resolution.resolved, model, clone_profile
            )

            # Create clients dict for text_to_speech
            openai_clients = {'tts': client}

            # Pass clone profile through kwargs if present
            tts_kwargs = dict(kwargs)
            if clone_profile:
                tts_kwargs['clone_profile'] = clone_profile

            success, metrics = await text_to_speech(
                text=text,
                openai_clients=openai_clients,
                tts_model=selected_model,
                tts_voice=selected_voice,
                tts_base_url=base_url,
                conversation_id=conversation_id,
                **tts_kwargs
            )

            if success:
                config = {
                    'base_url': base_url,
                    'provider': provider_type,
                    'voice': selected_voice,  # Return the voice actually used
                    'model': selected_model,
                    'endpoint': f"{base_url}/audio/speech",
                    # VM-1901: requested-vs-resolved provenance (design.md §5.3),
                    # additive alongside the provider-level 'voice' above.
                    'voice_requested': resolution.requested,
                    'voice_resolved': resolution.resolved,
                    'voice_via': resolution.via,
                    'is_fallback': is_fallback,
                    'fallback_reason': fallback_reason,
                }
                logger.info(f"TTS succeeded with {base_url} using voice {selected_voice}")
                return True, metrics, config
            else:
                # text_to_speech returned False, but we don't have exception details
                # Create a generic error message
                last_exception = Exception("TTS request failed")

        except Exception as e:
            last_exception = e

        # Handle the error (either from exception or False return)
        if last_exception:
            error_message = str(last_exception)
            logger.error(f"TTS failed for {base_url}: {error_message}")
            logger.debug(f"Exception type: {type(last_exception).__name__}")  # Debug logging

            # Parse OpenAI errors for better user feedback
            error_details = None
            if provider_type == "openai":
                error_details = OpenAIErrorParser.parse_error(last_exception, endpoint=f"{base_url}/audio/speech")
                # Log the user-friendly error message
                if error_details and error_details.get('title'):
                    logger.error(f"  {error_details['title']}: {error_details.get('message', '')}")
                    if error_details.get('suggestion'):
                        logger.info(f"  💡 {error_details['suggestion']}")

            # Add to attempted endpoints with error details
            attempted_endpoints.append({
                'endpoint': f"{base_url}/audio/speech",
                'provider': provider_type,
                'voice': selected_voice,
                'model': selected_model,
                'error': error_message,
                'error_details': error_details  # Include parsed error details
            })

            # Continue to next endpoint
            continue

    # All endpoints failed - return detailed error info
    logger.error(f"All TTS endpoints failed after {len(attempted_endpoints)} attempts")
    error_config = {
        'error_type': 'all_providers_failed',
        'attempted_endpoints': attempted_endpoints
    }
    return False, None, error_config


async def simple_tts_synthesize(
    text: str,
    voice: str,
    model: Optional[str] = None,
    **kwargs
) -> Tuple[bool, Optional[Any], Optional[int], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Synth-only TTS failover - decode audio without playing it (VM-1772).

    Mirrors :func:`simple_tts_failover` (same endpoint selection, clone routing,
    voice mapping and error reporting) but calls :func:`core.synthesize_tts_audio`
    so the decoded samples are returned to the caller for pipelined playback.

    Returns:
        Tuple of (success, samples, sample_rate, metrics, config). On total
        failure ``config`` carries ``error_type='all_providers_failed'`` and the
        per-endpoint ``attempted_endpoints`` list, matching the play path.
    """
    logger.info(f"simple_tts_synthesize called with: text='{text[:50]}...', voice={voice}, model={model}")

    from .core import synthesize_tts_audio
    from .conversation_logger import get_conversation_logger
    from .voice_profiles import VoiceResolutionError

    ref_text_override = kwargs.pop("ref_text", None)
    attempted_endpoints = []

    conversation_logger = get_conversation_logger()
    conversation_id = conversation_logger.conversation_id

    # VM-1901: an unresolvable voice raises HERE, before any endpoint is
    # tried — see simple_tts_failover's identical guard for the rationale.
    try:
        endpoints_to_try, clone_profile, resolution = _resolve_tts_endpoints(voice, ref_text_override)
    except VoiceResolutionError as e:
        logger.error(f"Voice resolution failed for {voice!r}: {e}")
        return False, None, None, None, {
            'error_type': 'voice_resolution_failed',
            'error': str(e),
            'attempted_endpoints': [],
        }

    logger.info(f"simple_tts_synthesize: Starting with endpoints = {endpoints_to_try}")
    for base_url in endpoints_to_try:
        logger.info(f"Trying TTS endpoint (synth): {base_url}")

        last_exception = None
        provider_type = detect_provider_type(base_url)
        selected_voice = voice
        selected_model = model
        try:
            # Review fix (VM-1901 observability-001): resolution.resolved, not
            # the raw `voice` -- see _prepare_tts_endpoint's docstring and the
            # identical fix in simple_tts_failover above.
            client, selected_voice, selected_model, provider_type, is_fallback, fallback_reason = _prepare_tts_endpoint(
                base_url, resolution.resolved, model, clone_profile
            )
            openai_clients = {'tts': client}

            tts_kwargs = dict(kwargs)
            if clone_profile:
                tts_kwargs['clone_profile'] = clone_profile

            success, samples, sample_rate, metrics = await synthesize_tts_audio(
                text=text,
                openai_clients=openai_clients,
                tts_model=selected_model,
                tts_voice=selected_voice,
                tts_base_url=base_url,
                conversation_id=conversation_id,
                **tts_kwargs
            )

            if success:
                config = {
                    'base_url': base_url,
                    'provider': provider_type,
                    'voice': selected_voice,
                    'model': selected_model,
                    'endpoint': f"{base_url}/audio/speech",
                    # VM-1901: requested-vs-resolved provenance (design.md §5.3).
                    'voice_requested': resolution.requested,
                    'voice_resolved': resolution.resolved,
                    'voice_via': resolution.via,
                    'is_fallback': is_fallback,
                    'fallback_reason': fallback_reason,
                }
                logger.info(f"TTS(synth) succeeded with {base_url} using voice {selected_voice}")
                return True, samples, sample_rate, metrics, config
            else:
                last_exception = Exception("TTS request failed")

        except Exception as e:
            last_exception = e

        if last_exception:
            error_message = str(last_exception)
            logger.error(f"TTS(synth) failed for {base_url}: {error_message}")

            error_details = None
            if provider_type == "openai":
                error_details = OpenAIErrorParser.parse_error(last_exception, endpoint=f"{base_url}/audio/speech")

            attempted_endpoints.append({
                'endpoint': f"{base_url}/audio/speech",
                'provider': provider_type,
                'voice': selected_voice,
                'model': selected_model,
                'error': error_message,
                'error_details': error_details
            })
            continue

    logger.error(f"All TTS(synth) endpoints failed after {len(attempted_endpoints)} attempts")
    error_config = {
        'error_type': 'all_providers_failed',
        'attempted_endpoints': attempted_endpoints
    }
    return False, None, None, None, error_config


def _is_transient_stt_error(e: Exception) -> bool:
    """Classify an STT transcription exception as transient (retry) or permanent.

    Transient (retry — the failure usually clears on a second try):
      - APITimeoutError / APIConnectionError: read-timeout, connection reset or
        refused. This is the whisper.cpp daily-timeout case (VM-926);
        APITimeoutError is a subclass of APIConnectionError.
      - APIStatusError with status_code >= 500: transient server-side error.

    Permanent (do NOT retry — fail closed, re-raise so failover / error surfaces):
      - APIStatusError with a 4xx status: bad audio (400), auth (401/403), 404,
        422, and 429 RateLimitError (a local whisper.cpp doesn't rate-limit;
        retrying a real 429 just hammers it — treated as permanent per design).
      - Any other / unrecognised exception: we never loop on an error we don't
        understand.
    """
    if isinstance(e, APIConnectionError):
        return True
    if isinstance(e, APIStatusError):
        return e.status_code >= 500
    return False


def _classify_stt_failure(e: Exception) -> Tuple[Optional[int], str]:
    """Classify one STT endpoint's failure as ``(status_code, error_type)`` (VM-2342).

    - HTTP 404 -> ``(404, "model_not_found")``: the server answered and does
      not know the model (mlx-audio's reply to an unknown model id; a wrong
      endpoint path also 404s, and the user-facing message says so).
    - Any other HTTP 4xx -> ``(status, "request_rejected")``: the server
      answered and refused the request (bad audio, auth, rate limit...).
    - Everything else -> ``(status or None, "connection_failed")``: refused,
      timed out, 5xx, or an unrecognised exception, as before VM-2342.
    """
    if isinstance(e, APIStatusError):
        status = getattr(e, "status_code", None)
        if isinstance(status, int) and 400 <= status < 500:
            return status, ("model_not_found" if status == 404 else "request_rejected")
        return (status if isinstance(status, int) else None), "connection_failed"
    return None, "connection_failed"


async def simple_stt_failover(
    audio_file,
    model: Optional[str] = None,
    **kwargs
) -> Optional[Dict[str, Any]]:
    """
    Simple STT failover - try each endpoint in order until one works.

    Returns:
        Dict with transcription result or error information:
        - Success: {"text": "...", "provider": "...", "endpoint": "...", "metrics": {...}}
        - No speech: {"error_type": "no_speech", "provider": "...", "metrics": {...}}
        - All failed: {"error_type": <kind>, "attempted_endpoints": [...]}
          where <kind> classifies the failures (VM-2342):
            * "model_not_found" -- at least one endpoint ANSWERED with HTTP 404
              (mlx-audio does this for a model it does not know, e.g. the
              stock "whisper-1"). Adds top-level "model", "endpoint" and
              "status_code" from the first 404.
            * "request_rejected" -- no 404, but at least one endpoint answered
              with another HTTP 4xx (400/401/403/422/429...). Adds the same
              top-level fields from the first such answer.
            * "connection_failed" -- no endpoint answered with a 4xx: refused,
              timed out, 5xx, or an unrecognised error (unchanged behaviour).
          Rule for a mixed chain: a server's 4xx answer outranks a connection
          error, because it is the actionable fault (the server is up and
          told us why). 404 outranks other 4xx. Every endpoint's own failure
          stays in "attempted_endpoints", each entry carrying "error_type",
          "model" (the id sent, or None) and "status_code" (or None).

        The metrics dict (when present) contains:
        - file_size_bytes: Size of audio file sent
        - request_time_ms: Total time for the API request
        - is_local: Whether the endpoint is local (localhost/LAN)
    """
    import time

    connection_errors = []
    successful_but_empty = False
    successful_provider = None

    # Get file size for metrics
    file_size_bytes = 0
    try:
        # Save current position, seek to end to get size, restore position
        start_pos = audio_file.tell()
        audio_file.seek(0, 2)  # Seek to end
        file_size_bytes = audio_file.tell()
        audio_file.seek(start_pos)  # Restore position
        # Ensure we got an integer
        if not isinstance(file_size_bytes, int):
            file_size_bytes = 0
    except Exception as e:
        logger.debug(f"Could not get file size: {e}")
        file_size_bytes = 0

    # Log STT request details
    logger.info("STT: Starting speech-to-text conversion")
    logger.info(f"  Available endpoints: {STT_BASE_URLS}")
    if file_size_bytes > 0:
        logger.info(f"  Audio file size: {file_size_bytes / 1024:.1f}KB")

    # Try each STT endpoint in order
    for i, base_url in enumerate(STT_BASE_URLS):
        resolved_model = None  # recorded in the failure entry if we fail early
        try:
            # Detect provider type for logging
            provider_type = detect_provider_type(base_url)

            if i == 0:
                logger.info(f"STT: Attempting primary endpoint: {base_url} ({provider_type})")
            else:
                logger.warning(f"STT: Primary failed, attempting fallback #{i}: {base_url} ({provider_type})")

            # Create client for this endpoint
            api_key = OPENAI_API_KEY if provider_type == "openai" else (OPENAI_API_KEY or "dummy-key-for-local")

            # Local endpoints keep the SDK client's own retries at 0; transient
            # retries for local STT are handled by the explicit backoff loop
            # around the transcription call below (VM-926) so we can classify
            # transient vs permanent and log each attempt. Remote endpoints keep
            # 2 SDK-level retries.
            max_retries = 0 if is_local_provider(base_url) else 2
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=60.0,  # Allow time for slower transcriptions
                max_retries=max_retries
            )

            # Resolve the per-endpoint STT model: OpenAI override -> caller-passed
            # -> positional STT_MODELS -> global STT_MODEL.
            endpoint_info = EndpointInfo(
                base_url=base_url,
                models=[],
                voices=[],
                provider_type=provider_type,
            )
            resolved_model = _select_stt_model_for_endpoint(endpoint_info, model)

            # Try STT with this endpoint - track timing
            request_start = time.perf_counter()
            # Build transcription kwargs with optional prompt for vocabulary biasing
            transcription_kwargs = {
                "model": resolved_model,
                "file": audio_file,
                "response_format": "text"
            }
            if STT_PROMPT:
                transcription_kwargs["prompt"] = STT_PROMPT

            # Handle language parameter based on provider
            # - whisper.cpp: needs "auto" explicitly (default is "en")
            # - OpenAI API: omit for auto-detect (doesn't accept "auto")
            # - mlx-audio: omit for auto-detect (VM-2342). It does not treat
            #   "auto" as a language: 0.5.7 maps it to <|endoftext|> and skips
            #   detection; only an unset language detects (VM-2334).
            if WHISPER_LANGUAGE and WHISPER_LANGUAGE != "auto":
                # Explicit language set - pass to all providers
                transcription_kwargs["language"] = WHISPER_LANGUAGE
            elif is_local_provider(base_url) and provider_type != "mlx-audio":
                # Local whisper.cpp with auto mode - must pass "auto" explicitly
                transcription_kwargs["language"] = "auto"
            # For OpenAI / mlx-audio with "auto" - don't pass the parameter

            # Bounded, transient-only retry with backoff for LOCAL STT (VM-926).
            # Local whisper.cpp does time out transiently and usually recovers on
            # a retry milliseconds later; retry the same endpoint a few times
            # before falling through to the outer `except` (next-endpoint
            # failover / final failure). This loop is the single retry mechanism
            # for local (the client above uses max_retries=0, so no double-retry).
            # Remote endpoints get retries=0 here and keep their SDK max_retries=2,
            # so remote behaviour is unchanged.
            retries = STT_RETRY_ATTEMPTS if is_local_provider(base_url) else 0
            attempt = 0

            # ElevenLabs STT uses a proprietary endpoint (/v1/speech-to-text)
            # with xi-api-key auth — bypass the OpenAI client path entirely.
            if provider_type == "elevenlabs":
                from . import elevenlabs_stt
                audio_file.seek(0)
                audio_data = audio_file.read()
                filename = getattr(audio_file, "name", "audio.mp3")
                language_arg = None
                if WHISPER_LANGUAGE and WHISPER_LANGUAGE != "auto":
                    language_arg = WHISPER_LANGUAGE
                text = await elevenlabs_stt.transcribe(
                    audio_data=audio_data,
                    filename=os.path.basename(filename) if filename else "audio.mp3",
                    model=resolved_model,
                    language=language_arg,
                )
                request_time_ms = (time.perf_counter() - request_start) * 1000
                logger.info(
                    f"STT: ElevenLabs transcribed in {request_time_ms:.0f}ms: '{text[:50]}'"
                )
            else:
                while True:
                    try:
                        transcription = await client.audio.transcriptions.create(**transcription_kwargs)
                        break
                    except Exception as e:
                        if attempt < retries and _is_transient_stt_error(e):
                            delay = min(STT_RETRY_BACKOFF * (2 ** attempt), STT_RETRY_BACKOFF_MAX)
                            logger.warning(
                                f"STT transient failure on {base_url} "
                                f"(try {attempt + 1}/{retries + 1}): {e}; retry in {delay:.1f}s"
                            )
                            await asyncio.sleep(delay)
                            attempt += 1
                            continue
                        # Permanent error or retries exhausted: re-raise to the outer
                        # except, which records the failure and advances to the next
                        # endpoint (or returns connection_failed).
                        raise
                request_time_ms = (time.perf_counter() - request_start) * 1000
                text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()

            # Build metrics dict
            is_local = is_local_provider(base_url)
            metrics = {
                "file_size_bytes": file_size_bytes,
                "request_time_ms": round(request_time_ms, 1),
                "is_local": is_local,
            }

            if text:
                logger.info(f"✓ STT succeeded with {provider_type} at {base_url}")
                logger.info(f"  Transcribed: {text[:100]}{'...' if len(text) > 100 else ''}")
                logger.info(f"  Request time: {request_time_ms:.0f}ms, File size: {file_size_bytes/1024:.1f}KB")
                # Return both text and provider info for display, plus metrics
                return {"text": text, "provider": provider_type, "endpoint": base_url, "metrics": metrics}
            else:
                # Successful connection but no speech detected
                logger.warning(f"STT returned empty result from {base_url} ({provider_type})")
                successful_but_empty = True
                successful_provider = provider_type
                # Store metrics for potential no_speech return
                successful_metrics = metrics

        except Exception as e:
            error_str = str(e)
            provider_type = detect_provider_type(base_url)

            # Parse OpenAI errors for better user feedback
            error_details = None
            if provider_type == "openai":
                full_endpoint = f"{base_url}/audio/transcriptions" if not base_url.endswith("/v1") else f"{base_url}/audio/transcriptions"
                error_details = OpenAIErrorParser.parse_error(e, endpoint=full_endpoint)
                # Log the user-friendly error message
                if error_details.get('title'):
                    logger.error(f"  {error_details['title']}: {error_details.get('message', '')}")
                    if error_details.get('suggestion'):
                        logger.info(f"  💡 {error_details['suggestion']}")

            # Track the failure, classified (VM-2342): an HTTP 4xx means the
            # server ANSWERED, which is not a connection failure.
            full_endpoint = f"{base_url}/audio/transcriptions" if not base_url.endswith("/v1") else f"{base_url}/audio/transcriptions"
            status_code, endpoint_error_type = _classify_stt_failure(e)
            connection_errors.append({
                "endpoint": full_endpoint,
                "provider": provider_type,
                "error": error_str,
                "error_details": error_details,  # Include parsed error details
                "error_type": endpoint_error_type,
                "model": resolved_model,
                "status_code": status_code,
            })

            # Log failure with appropriate level based on whether we have fallbacks
            if i < len(STT_BASE_URLS) - 1:
                logger.warning(f"STT failed for {base_url} ({provider_type}): {e}")
                logger.info("  Will try next endpoint...")
            else:
                logger.error(f"STT failed for final endpoint {base_url} ({provider_type}): {e}")

            # Continue to next endpoint
            continue

    # Determine what to return based on results
    if successful_but_empty:
        # At least one endpoint connected successfully but returned no speech
        logger.info("STT: No speech detected (successful connection)")
        result = {"error_type": "no_speech", "provider": successful_provider}
        # Include metrics if we captured them
        if 'successful_metrics' in locals():
            result["metrics"] = successful_metrics
        return result
    elif connection_errors:
        # All endpoints failed. Report a server's 4xx answer as what it is
        # (VM-2342); see the docstring for the mixed-chain rule.
        logger.error(f"✗ All STT endpoints failed after {len(STT_BASE_URLS)} attempts")
        for kind in ("model_not_found", "request_rejected"):
            answered = next((a for a in connection_errors if a["error_type"] == kind), None)
            if answered is not None:
                logger.error(
                    f"  {kind}: model {answered['model']!r} at {answered['endpoint']} "
                    f"(HTTP {answered['status_code']})"
                )
                return {
                    "error_type": kind,
                    "model": answered["model"],
                    "endpoint": answered["endpoint"],
                    "status_code": answered["status_code"],
                    "attempted_endpoints": connection_errors,
                }
        return {"error_type": "connection_failed", "attempted_endpoints": connection_errors}
    else:
        # Should not reach here, but handle it gracefully
        logger.error("STT: Unexpected state - no successful connections and no errors tracked")
        return None