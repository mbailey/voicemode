# `voice://voices` Resource Reference

Structured TTS voice discovery for MCP clients. Apps and agents read
this resource — typically over streamable HTTP — to populate voice
pickers and route `converse` calls to a real voice without hardcoding
per-provider lists or scraping prose from the `voice_registry` tool.

The matching `voice_registry` MCP tool stays in place for the LLM
mid-conversation; both surfaces share the same enumerator
(`voice_mode/voices.py::enumerate_voices`) so they never drift.

## Quick Reference

| URI                              | Returns                                        |
| -------------------------------- | ---------------------------------------------- |
| `voice://voices`                 | Full voice list                                |
| `voice://voices/{provider}`      | Same envelope, filtered to one provider        |

- MIME type: `application/json` (advertised on `resources/list`)
- Read with: `resources/read voice://voices` (and `voice://voices/{provider}`)
- Available over both stdio and streamable HTTP transports

## URIs

### `voice://voices`

Returns the full voice list the connected server can produce — every
configured TTS endpoint that responded plus, for local callers, any
impressions/clones from `VOICES_DIR`.

### `voice://voices/{provider}`

Same envelope, with `voices[]` narrowed to entries whose `provider`
field matches the path segment. The envelope is well-formed even when
the provider is unknown (the list is just empty). Useful for clients
that already know which backend they want to draw voices from (e.g.
`voice://voices/kokoro` for the local Kokoro picker).

> **Picking a valid `{provider}` value.** Read `voice://voices` first
> and collect the distinct `voices[].provider` strings. The current set
> is `openai`, `kokoro`, `mlx-audio`, `local`, `unknown` — but the
> resource is the source of truth for what your specific server is
> actually configured for.

## JSON Schema

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-10T16:42:00Z",
  "voices": [
    {
      "id": "kokoro:af_river",
      "voice": "af_river",
      "name": "af_river",
      "provider": "kokoro",
      "language": null,
      "gender": null,
      "preview_url": null
    }
  ]
}
```

### Envelope

| Field            | Type    | Notes                                                                                            |
| ---------------- | ------- | ------------------------------------------------------------------------------------------------ |
| `schema_version` | integer | `1` in v1. Bumped on a breaking schema change.                                                   |
| `generated_at`   | string  | ISO 8601 UTC with `Z` suffix. Computed at call time, not cache-fill time. See [Freshness](#freshness-and-cadence). |
| `voices`         | array   | Voice entries. May be empty.                                                                     |

### Voice entry

| Field         | Type             | Notes                                                                                                |
| ------------- | ---------------- | ---------------------------------------------------------------------------------------------------- |
| `id`          | string           | Globally unique, scoped as `{provider}:{voice}`. Stable across reads with unchanged server config.   |
| `voice`       | string           | Raw value to pass to `converse(voice=...)`.                                                          |
| `name`        | string           | Human-readable display label. In v1 this falls back to `voice` when no friendlier label is known.    |
| `provider`    | string           | Opaque short name (`openai`, `kokoro`, `mlx-audio`, `local`, `unknown`). **Never a URL** (AC4).      |
| `language`    | string \| null   | BCP-47 where known; `null` if not tracked.                                                           |
| `gender`      | string \| null   | `"male"` \| `"female"` \| `"neutral"` \| `null`.                                                     |
| `preview_url` | null             | Reserved for future use. Always `null` in v1.                                                        |

**No `provider_url`, no `base_url`, no endpoint URLs anywhere in the
body.** Server-internal endpoints (`http://127.0.0.1:8880/v1`) leak
deployment topology and are useless to a remote client. Endpoint
diagnostics live in the `voice_registry` tool's prose output, which is
the right surface for the LLM mid-conversation.

## Example Responses

### Stdio caller (impressions visible)

`resources/read voice://voices` from a local stdio caller with
`TTS_BASE_URLS=https://api.openai.com/v1,http://127.0.0.1:8880/v1`
and one impression `samantha` under `~/.voicemode/voices/`:

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-10T16:42:00Z",
  "voices": [
    { "id": "openai:alloy",   "voice": "alloy",   "name": "alloy",   "provider": "openai", "language": null, "gender": null, "preview_url": null },
    { "id": "openai:ash",     "voice": "ash",     "name": "ash",     "provider": "openai", "language": null, "gender": null, "preview_url": null },
    { "id": "openai:ballad",  "voice": "ballad",  "name": "ballad",  "provider": "openai", "language": null, "gender": null, "preview_url": null },
    { "id": "openai:coral",   "voice": "coral",   "name": "coral",   "provider": "openai", "language": null, "gender": null, "preview_url": null },
    { "id": "openai:echo",    "voice": "echo",    "name": "echo",    "provider": "openai", "language": null, "gender": null, "preview_url": null },
    { "id": "openai:fable",   "voice": "fable",   "name": "fable",   "provider": "openai", "language": null, "gender": null, "preview_url": null },
    { "id": "openai:nova",    "voice": "nova",    "name": "nova",    "provider": "openai", "language": null, "gender": null, "preview_url": null },
    { "id": "openai:onyx",    "voice": "onyx",    "name": "onyx",    "provider": "openai", "language": null, "gender": null, "preview_url": null },
    { "id": "openai:sage",    "voice": "sage",    "name": "sage",    "provider": "openai", "language": null, "gender": null, "preview_url": null },
    { "id": "openai:shimmer", "voice": "shimmer", "name": "shimmer", "provider": "openai", "language": null, "gender": null, "preview_url": null },
    { "id": "openai:verse",   "voice": "verse",   "name": "verse",   "provider": "openai", "language": null, "gender": null, "preview_url": null },
    { "id": "kokoro:af_river", "voice": "af_river", "name": "af_river", "provider": "kokoro", "language": null, "gender": null, "preview_url": null },
    { "id": "mlx-audio:samantha", "voice": "samantha", "name": "samantha", "provider": "mlx-audio", "language": null, "gender": null, "preview_url": null }
  ]
}
```

### Remote streamable HTTP caller (impressions hidden)

Same server, same configuration, but the caller is a remote client over
streamable HTTP. The impression is filtered out (see [Privacy](#privacy)):

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-10T16:42:01Z",
  "voices": [
    { "id": "openai:alloy", "voice": "alloy", "name": "alloy", "provider": "openai", "language": null, "gender": null, "preview_url": null }
    // ... other openai + kokoro voices, no mlx-audio:samantha
  ]
}
```

### Per-provider filter

`resources/read voice://voices/openai`:

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-10T16:42:02Z",
  "voices": [
    { "id": "openai:alloy",   "voice": "alloy",   "name": "alloy",   "provider": "openai", "language": null, "gender": null, "preview_url": null },
    { "id": "openai:ash",     "voice": "ash",     "name": "ash",     "provider": "openai", "language": null, "gender": null, "preview_url": null }
    // ... remaining openai voices only
  ]
}
```

An unknown `{provider}` returns `"voices": []` with the rest of the
envelope intact.

## Privacy

Impressions/clones are personal voice data and are **omitted from
remote responses by default**. The resolution order, hardened against
malformed peer information:

1. `VOICEMODE_EXPOSE_LOCAL_VOICES_REMOTE` truthy → include impressions.
2. No active HTTP request (stdio / in-memory transport) → include
   impressions.
3. HTTP request with a loopback peer (`127/8`, `::1`, IPv4-mapped
   loopback `::ffff:127.0.0.1`) → include impressions.
4. Anything else — `None` client, empty host string, unparseable IP, or
   a public peer → omit impressions (safe default).

The check looks at the connection peer reported by uvicorn via
`fastmcp.server.dependencies.get_http_request()`, not at request
headers, so an HTTP client cannot lie its way into "local". The
predicate is implemented in `voice_mode/resources/voices.py`.

> **`stdio` vs in-memory test transports.** The stdio path is detected
> by the same `RuntimeError` that `FastMCPTransport` (the in-memory
> test transport) raises when it is asked for an HTTP request. So both
> behave identically for the privacy predicate — there is no third
> "local-but-HTTP" branch.

### `VOICEMODE_EXPOSE_LOCAL_VOICES_REMOTE`

| Truthy values             | Falsy values (anything else, including unset) |
| ------------------------- | --------------------------------------------- |
| `1`, `true`, `yes`, `on`  | `0`, `false`, `no`, `off`, `""`, unset        |

Case-insensitive; surrounding whitespace is stripped. When set truthy,
impressions are included for every read regardless of transport or peer
address.

> **When to set this.** Use it when running VoiceMode behind a
> co-located reverse proxy on the same host: every connection arrives
> from `127.0.0.1`, so the loopback test would over-report "local" and
> include impressions to remote callers. Either configure your proxy
> to forward the real peer (uvicorn `--proxy-headers`,
> `X-Forwarded-For` / `Forwarded`) — VoiceMode does not currently honour
> these headers, so the safer alternative is to leave the env var unset
> (or explicitly `false`) and accept that impressions stay hidden. Set
> the env var truthy only when you actively want every caller treated
> as local.

## Freshness and Cadence

The enumerator caches results in-process for **60 seconds**, with two
independent cache slots keyed by whether impressions are included
(`include_local_only=True` for local callers, `False` for remote). Each
read inside the TTL window returns the cached list with a fresh
`generated_at` timestamp computed at call time.

| Provider source                    | Subject to TTL?              | Notes                                                                 |
| ---------------------------------- | ---------------------------- | --------------------------------------------------------------------- |
| OpenAI                             | No (hardcoded constant)      | `OPENAI_TTS_VOICES` lives in `voice_mode/voices.py`. Never network-probed. |
| Kokoro / mlx-audio / local / unknown | Yes (60 s)                  | Live `GET {base_url}/audio/voices` with a 5 s per-endpoint timeout.   |
| Whisper                            | Skipped entirely             | STT-only; not in the TTS enumerator.                                  |
| Impressions (`VOICES_DIR`)         | Yes (60 s, local callers only) | Filesystem scan via `voice_profiles.list_profiles()`.                |

**Implications:**

- A user installing or restarting Kokoro / mlx-audio sees the new voice
  list within ~60 seconds.
- A user adding a new impression sees it within ~60 seconds of the next
  local read (no file-watcher in v1).
- OpenAI voices change only when the maintainer hand-edits
  `OPENAI_TTS_VOICES` (see [Maintenance](#maintenance)).
- Polling more often than once per minute returns cached data; trading
  freshness for snappy picker UX is the explicit design choice.

There is no `cadence_seconds` field on the wire; this section is the
canonical statement of the enumerator's freshness model (per AC7).

### Failure semantics

If a `/audio/voices` probe fails for any reason, the enumerator skips
that endpoint silently and logs a `WARNING` (or `ERROR` for malformed
JSON). The response is always a partial list — one broken endpoint does
not break the picker. Recovery is automatic on the next read after the
TTL expires.

## How `voice_registry` Tool Sources Its Voice List

The `voice_registry` MCP tool — the prose-shaped surface for the LLM
mid-conversation — now sources its voice list via
`enumerate_voices(include_local_only=False)` rather than the legacy
`provider_registry` cache. Same enumerator backing both surfaces means
the JSON resource and the LLM prose can never disagree on the voice
list.

The visible side-effect of the refactor: when an endpoint is offline,
the tool now reports `Voices: none detected` instead of the legacy
67-voice phantom list `provider_registry` shipped as a hardcoded
fallback. This is deliberate — the tool now reflects what the endpoint
can actually produce right now, not what the package once shipped with.

## Maintenance

### OpenAI voice list

`OPENAI_TTS_VOICES` in `voice_mode/voices.py` is hand-maintained.
OpenAI does not expose `/audio/voices`, so there is nothing to probe.
Update the constant and the `Last verified:` comment when OpenAI
publishes a new voice. As of `2026-05-10` the list is:

```
alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer, verse
```

The original six (`alloy`, `echo`, `fable`, `nova`, `onyx`, `shimmer`)
work with `tts-1` and `tts-1-hd`. `ballad` and `verse` were added with
`gpt-4o-mini-tts`.

### Adding a provider

`detect_provider_type()` in `voice_mode/provider_discovery.py`
classifies a `TTS_BASE_URL` into one of `openai`, `kokoro`,
`mlx-audio`, `whisper`, `local`, `unknown`. Anything matching
`local` / `unknown` falls through to a best-effort `GET /audio/voices`
probe. To onboard a new provider with a different voice-list shape,
add a branch to `_voices_for_endpoint()` in `voice_mode/voices.py`.

## See Also

- [Remote Access (serve)](../guides/serve-configuration.md) — How to
  run VoiceMode over streamable HTTP so remote clients can read this
  resource.
- [Selecting Voices](../guides/selecting-voices.md) — Picker UX
  guidance for end users.
- [Architecture](../concepts/architecture.md) — Where the resource fits
  in the broader server architecture.
