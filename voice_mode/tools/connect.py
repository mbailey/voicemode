"""VoiceMode Connect — no MCP tools exposed.

Connect management is done via CLI commands:
  voicemode connect up/down/status
  voicemode connect user add/list/remove

Agents use bash to call CLI tools, guided by the voicemode-connect skill.
No MCP tools are needed — the CLI is the common interface for humans and agents.
"""
