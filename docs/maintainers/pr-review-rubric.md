# PR review rubric

A lightweight, VoiceMode-specific checklist for triaging an incoming pull
request. Run it top to bottom; it produces a **disposition** (merge / rebase /
rework / close). It's written so a human maintainer *or* an AI agent can apply
it consistently — the goal is that the queue never silently piles up.

> Born from the June 2026 queue audit: 28 open PRs triaged in one pass. The
> checks below are the failure modes that actually recurred — not generic
> advice. Where a check cites a PR, that's the real case it came from.

## Step 0 — Is it already done? (do this first)

The single highest-value, most-skipped check. A cold reviewer can't know our
history; **you can**. Before reading the diff in depth, confirm the change
isn't already shipped or deliberately removed:

- [ ] `git grep` the feature's functions / flags / tool names on `master`.
- [ ] Scan `CHANGELOG.md` `[Unreleased]` and recent releases.
- [ ] `git log --oneline -50` (and search closed PRs) for related work.
- [ ] Check the task tracker for a matching task that shipped via another PR,
      or a decision to *remove* the feature.

In the June audit, **5 of 28 PRs were already on master or intentionally
deleted** (e.g. a conch-holdership PR we'd shipped *with the contributor
credited in the changelog*; a history-search module we'd removed on purpose).
Catching these first saves everyone a deep review of dead work.

→ If superseded: **close** with thanks + a pointer to the shipped work / the
removal decision (see *Closing well* below).

## Step 1 — Voice-pipeline red lines (VoiceMode-specific)

These are the ways a PR can pass tests and still break voice. Treat any hit as
**rework**, not merge.

- [ ] **Never write to stdout.** The MCP server speaks JSON-RPC over **stdio**
      (`server.py` runs `mcp.run(transport="stdio")`). *Anything* printed to
      stdout — a progress bar, a Rich `Console`/`Live`, a stray `print()` —
      corrupts the protocol stream and breaks converse for the default install.
      Output goes to **stderr**, and ideally only when attached to a real TTY.
      *(From #105: a default-on Rich visualizer writing to stdout.)*
- [ ] **New behaviour on the default path is opt-in.** Anything touching the
      default converse / STT / TTS flow must be **gated behind an env flag,
      default off** — not on-by-default. Unconditional changes to the converse
      **system prompt** are a special case of this: gate them or keep them out
      of the always-on prompt. *(From #105 default-on; #328 unconditional
      prompt edits.)*
- [ ] **It composes with recent work.** A months-old branch may silently revert
      or collide with shipped features. Check it still cooperates with:
      conch holdership (`hold_conch`, VM-1433), trigger words (VM-291), and the
      impressions passthrough (`ref_text` / `clone_profile` / `tts_kwargs` in
      `simple_failover.py`, VM-1174). A rebase must **preserve** these, not
      overwrite the block.
- [ ] **Provider integrations: prefer the base-URL mechanism.** VoiceMode
      discovers TTS/STT providers from OpenAI-compatible endpoints in
      `VOICEMODE_*_BASE_URLS`. A new provider that *already* exposes an
      OpenAI-compatible endpoint usually needs **no merge at all** — the user
      just adds its URL. Only bundle an installer/backend when the maintenance
      cost is clearly justified. *(From #261: a kokoro-onnx server that was
      already usable via base-URL; the PR's value was a bundled installer = a
      third TTS backend to maintain.)*
- [ ] **If it must fork the core path, gate by provider and preserve the
      else-branch verbatim.** A non-OpenAI-compatible provider may need a fork
      in `text_to_speech` / the STT path. Done right, every fork is
      `if provider == "X": <new> else: <original code, unchanged>`, so users
      who haven't configured X get byte-identical behaviour. *(The Cartesia PR
      #368 is the reference example of doing this correctly.)*

## Step 2 — Health checks

- [ ] **CHANGELOG entry present.** Every user-facing PR adds a `[Unreleased]`
      entry (the changelog *is* the release notes — kept continuous). Add it at
      merge if the contributor didn't. *(Many June PRs merged without one and
      needed a catch-up.)*
- [ ] **Tests don't mock away the thing under test.** Green CI ≠ correct. Look
      for a passing suite that mocks the exact function that's broken or
      missing. *(From #261: the install referenced an undefined function; tests
      passed only because they mocked it.)*
- [ ] **Reuses existing utilities.** New helper that duplicates one we already
      have? Point it at the existing one. *(From #320: a new inline `is_wsl2()`
      instead of the existing `detect_platform()`.)*
- [ ] **One feature per PR.** A PR bundling several independent features is hard
      to review and risky to land — ask for a split. *(From #328: four
      unrelated features — PTT, polyglot TTS, retry, a notify CLI — in one PR.)*
- [ ] **Rebased, not stacked on an unmerged PR.** Confirm the base is current
      `master`, not another open PR's branch. *(From #281: built on top of an
      unmerged barge-in branch — it carried the whole feature plus a fix, so it
      *superseded* the original rather than complementing it.)*
- [ ] **New runtime dependency justified.** A new third-party dep is a long-term
      cost. Is it arm64/platform-gated and opt-in so it can't affect installs
      that don't want it?

## Step 3 — Disposition

Assign exactly one:

| Disposition | When |
|---|---|
| **Merge** | Correct, valuable, mergeable as-is, CI green. |
| **Rebase → merge** | Good change, just conflicts with `master`. Rebase, re-run tests, add the changelog, then merge. |
| **Rework** | Valuable idea, needs changes first. Say *exactly* what, kindly. |
| **Close** | Superseded, obsolete, wrong approach, or abandoned. |

## Closing well

Closing a contribution is a relationship, not a delete. Every close gets:

- **Genuine thanks** + one specific thing that was good about the work.
- **The real reason**, with a concrete pointer (commit, PR, or task) — e.g.
  "shipped as VM-XXXX", "removed in VM-YYYY", "the capability is already
  available via `VOICEMODE_*_BASE_URLS`".
- **Credit** where their work shipped in another form (name them in the
  changelog; link their PR).

## Dependabot

- Merge the **grouped** bump first (e.g. the `python` group). Individual bumps
  for packages already in the group become redundant and can be closed as
  *already-applied*; check the resulting `uv.lock` version before closing.
- Bumps to the same lockfile conflict with each other — merge one, the rest
  need a rebase (`@dependabot rebase`) or auto-close.
- A bump failing CI on a **pre-existing/unrelated** test (not the upgrade
  itself) and weeks behind `master` is usually a **close** — dependabot will
  raise a fresh, current one.

---

See also: [CONTRIBUTING.md](../../CONTRIBUTING.md) (contributor setup, tests,
code style) · [docs/concepts/architecture.md](../concepts/architecture.md).
