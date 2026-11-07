---
name: conch
description: Sharing one voice channel between agents; the floor lock (the conch), holding it across turns, queueing for it, and handing a conversation to another agent.
---
One agent speaks at a time. The conch is the floor lock: taken as you speak, kept with hold_conch, queued for with wait_for_conch.

# The conch: one channel, several agents

Every `converse` call takes the conch (the floor) before speaking and lets it go after. In a session with several voice agents that is what stops two of them talking over each other.

- **Continuing a thread**: `hold_conch=true` when your next call follows this one (a question you will answer, several turns in a row). The hold is a short, refreshed TTL: each held call re-stamps it, a call with `hold_conch=false` releases it, and if you stop calling it lapses and the next queued agent is promoted. `conch_hold_timeout` sets that TTL for one hold, in seconds, when the next turn needs longer (heavy tool use between turns).
- **Stepping away but keeping the floor**: `pause_conversation(seconds, message)` holds the conch through a pause for background work; your next call resumes.
- **Someone else is speaking**: by default your call returns a status naming the holder instead of speaking. `wait_for_conch=true` joins the FIFO queue and blocks until the floor is yours (a number waits at most that many seconds); background the tool call if you do not want to block on it. `skip_conch=true` speaks regardless: for a stuck holder, never a habit.
- **Who holds it**: `voicemode conch status` shows the holder and the queue. The holder's voice is recorded in the lock, so pick a different one and the handoff is audible.

## Handing a conversation to another agent

1. Say so first: `converse("Handing you to the project agent.", wait_for_response=false)`.
2. Brief the receiving agent (why the user is coming, which voice to use), then go quiet.
3. Hand back the same way: announce, then stop conversing.

One speaker at a time, distinct voices, always announce. With agents in separate tmux panes, `VOICEMODE_AUTO_FOCUS_PANE=true` in `~/.voicemode/voicemode.env` makes tmux follow the speaker; focus moves after the conch is acquired, so waiters never steal it, and it honours the `~/.voicemode/focus-hold` sentinel show-me writes. Routing patterns in depth: `docs/guides/agents/call-routing/`.
