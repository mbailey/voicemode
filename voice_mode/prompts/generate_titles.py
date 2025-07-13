"""Prompt for generating conversation titles."""

from ..server import mcp

GENERATE_TITLES_PROMPT = """
Generate meaningful titles for voice conversations based on their content.

This command analyzes your voice conversations and generates descriptive titles 
to replace the default text previews. You can also generate summaries and tags.

## Basic Usage

```
/generate-titles
```
Generates titles for today's untitled conversations

## Options

```
/generate-titles --yesterday
```
Generate titles for yesterday's conversations

```
/generate-titles --week  
```
Generate titles for the last 7 days

```
/generate-titles --date 2025-07-13
```
Generate titles for a specific date

```
/generate-titles --all
```
Process ALL conversations, not just untitled ones

```
/generate-titles --summary
```
Also generate brief summaries for each conversation

```
/generate-titles --conversation conv_20250713_153306_6u3vqj
```
Generate title for a specific conversation

## Examples

### Generate titles for today's new conversations:
```
/generate-titles
```

### Process last week with summaries:
```
/generate-titles --week --summary
```

### Update all conversations from a specific date:
```
/generate-titles --date 2025-07-13 --all
```

## What it does

1. Reads conversation content
2. Analyzes the main topics discussed
3. Generates a concise, descriptive title
4. Optionally creates a summary
5. Saves the metadata for use in conversation listings

## Tips

- Run this regularly to keep your conversations organized
- Use `voice-mode-cli conversations` to see the titles
- Mark important conversations as favorites with the update_conversation_metadata tool
- Add tags for better organization
"""


@mcp.prompt(
    name="generate-titles",
    description="Generate titles for voice conversations using AI analysis"
)
async def generate_titles_prompt(command: str = "/generate-titles") -> str:
    """
    Prompt for generating conversation titles.
    
    This prompt helps users generate meaningful titles for their voice conversations
    based on the content discussed. It includes various options for date ranges
    and processing preferences.
    """
    # Parse command options
    parts = command.strip().split()
    
    # Default values
    date_range = "today"
    include_summary = False
    only_untagged = True
    conversation_ids = []
    
    # Parse options
    i = 1
    while i < len(parts):
        if parts[i] == "--yesterday":
            date_range = "yesterday"
        elif parts[i] == "--week":
            date_range = "week"
        elif parts[i] == "--date" and i + 1 < len(parts):
            date_range = parts[i + 1]
            i += 1
        elif parts[i] == "--all":
            only_untagged = False
        elif parts[i] == "--summary":
            include_summary = True
        elif parts[i] == "--conversation" and i + 1 < len(parts):
            conversation_ids.append(parts[i + 1])
            i += 1
        i += 1
    
    # Build the tool call instruction
    if conversation_ids:
        instruction = f"""
Use the generate_conversation_titles tool with these parameters:
- conversation_ids: {conversation_ids}
- include_summary: {include_summary}

This will generate titles for the specific conversations: {', '.join(conversation_ids)}
"""
    else:
        instruction = f"""
Use the generate_conversation_titles tool with these parameters:
- date_range: "{date_range}"
- include_summary: {include_summary}
- only_untagged: {only_untagged}

This will generate titles for {date_range}'s conversations.
{"It will process ALL conversations, not just untitled ones." if not only_untagged else "It will only process conversations that don't already have titles."}
{"It will also generate brief summaries for each conversation." if include_summary else ""}
"""
    
    return f"""
# Generate Conversation Titles

{instruction}

After generating titles, you can:
1. View the updated conversations with `voice-mode-cli conversations`
2. Mark favorites with the update_conversation_metadata tool
3. Add tags for better organization
4. View the results in the conversations resources

The titles will help you quickly identify conversations in listings and make your conversation history more searchable.
"""