# Claude Code Documentation URLs

This file maintains a list of official Claude Code documentation URLs that should be regularly checked for updates.

## Last Updated: 2025-09-10

## Primary Documentation Sources

### Main Documentation
- https://docs.anthropic.com/en/docs/claude-code/claude_code_docs_map.md - Main documentation index
- https://github.com/anthropics/claude-code - Official GitHub repository
- https://github.com/anthropics/claude-code/issues - Issue tracker for updates and changes

### Hooks Documentation
- Check main docs map for hooks section
- Configuration examples and use cases
- Hook types and their inputs/outputs

### Features and Tools
- Built-in tools documentation
- MCP (Model Context Protocol) integration
- Agent system documentation

## Documentation Sync Strategy

1. **Regular Updates**: Check these URLs weekly or when encountering unexpected behavior
2. **Local Cache**: Store fetched documentation with timestamps in `/Users/admin/Code/github.com/mbailey/voicemode/docs/claude-code-cache/`
3. **Subagent Process**: Use a dedicated agent to fetch and process documentation to avoid context pollution
4. **Version Tracking**: Track Claude Code version changes and correlate with documentation updates

## Cache Structure (Proposed)

```
docs/claude-code-cache/
├── metadata.json          # Timestamps and version info
├── hooks/                  # Hook documentation
│   ├── overview.md
│   └── examples.md
├── tools/                  # Built-in tools docs
├── mcp/                    # MCP integration docs
└── agents/                 # Agent system docs
```

## Update Command (To Be Implemented)

```bash
# Future command to update documentation cache
voicemode docs update-claude-code-docs
```

## Notes

- Documentation fetched via WebFetch tool includes real-time data
- HTML content is converted to markdown for easier processing
- Consider implementing automatic freshness checks based on timestamps
- Use a subagent to handle the heavy lifting of fetching and processing to preserve main context