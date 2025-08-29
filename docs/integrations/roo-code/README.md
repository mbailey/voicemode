# Voice Mode Integration: Roo Code

> 🔗 **Official Website**: [RooCode.com](https://roocode.com/)  
> 📦 **Install**: Search "Roo Code" in VS Code Extensions  
> 🏷️ **Version Requirements**: VS Code 1.80+, Roo Code extension

## Overview

Roo Code (formerly Roo Cline) is an AI-powered VS Code extension that gives you a whole dev team of AI agents in your editor. Voice Mode enhances Roo Code by adding natural voice conversation capabilities through MCP.

## Prerequisites

- [ ] VS Code installed
- [ ] Python 3.10 or higher
- [ ] [uv](https://github.com/astral-sh/uv) package manager (`curl -LsSf https://astral.sh/uv/install | sh`)
- [ ] OpenAI API key (or compatible service)
- [ ] System audio dependencies installed ([see main README](../../../README.md#system-dependencies))

## Quick Start

```bash
# Set your OpenAI API key
export OPENAI_API_KEY="your-openai-key"

# Roo Code will use uvx to run Voice Mode on-demand
# No separate installation needed!
```

## Installation Steps

### 1. Install Roo Code

1. Open VS Code
2. Go to Extensions (Ctrl/Cmd + Shift + X)
3. Search for "Roo Code"
4. Click Install
5. Reload VS Code when prompted

### 2. Configure Roo Code for Voice Mode

#### Method 1: Using the MCP Interface (Recommended)

1. **Open Roo Code Panel**
   - Click the Roo Code icon in VS Code's sidebar (rocket icon 🚀)
   - Wait for Roo Code to fully load

2. **Access MCP Settings**
   - Look for the row of icons at the top of the Roo Code panel
   - Click the **gear/settings icon** (usually one of the rightmost icons)
   - Select "MCP Servers" from the menu (or it may open directly)

3. **Configure Voice Mode**
   - Ensure ✅ "Enable MCP Servers" toggle is ON (checked)
   - Click the **"Edit Global MCP"** button at the bottom
   - This opens the `cline_mcp_settings.json` file
   - Add Voice Mode to the `mcpServers` section:

#### Method 2: Direct File Edit

1. **Locate Configuration File**
   - **Windows**: `%APPDATA%\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\cline_mcp_settings.json`
   - **macOS/Linux**: `~/Library/Application Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`
   
2. **Add Voice Mode Configuration**

```json
{
  "mcpServers": {
    "voice-mode": {
      "command": "uvx",
      "args": ["voice-mode"],
      "env": {
        "OPENAI_API_KEY": "your-openai-key"
      }
    }
  }
}
```

**Note:** Using `uvx` means Voice Mode will be downloaded and run on-demand. No separate installation required!

### 3. Apply Configuration

1. **Save the configuration file** (`Ctrl/Cmd + S`)
2. **Return to the MCP Servers view** in Roo Code
3. **Click "Refresh MCP Servers"** button at the bottom
   - This reloads all server configurations
   - You should see "voice-mode" appear in the server list
4. **If the server doesn't appear**, restart VS Code completely

### 4. Verify Setup

1. **Check MCP Servers View**
   - Return to the MCP Servers view
   - You should see "voice-mode" listed with:
     - A "global" tag indicating it's a global configuration
     - A 🟢 green status dot when active
     - An enabled toggle switch (blue/active)

2. **Confirm Server is Running**
   - If you see a red dot or error:
     - Click the 🔄 restart button next to voice-mode
     - Check that `uvx` is installed: `which uvx`
     - Verify your OpenAI API key is set correctly

3. **Test in Chat**
   - Return to the Roo Code chat interface
   - The tools from voice-mode are now available to Roo

## Testing Voice Mode

1. **Initial Test:**
   - In Roo Code chat, type: "Let's have a voice conversation"
   - You should hear Roo speak and wait for your response
   - Try saying: "Hello, can you help me with this code?"

2. **Check Available Tools:**
   - Type: "What voice tools do you have available?"
   - Roo should list tools like `converse`, `check_audio_devices`, etc.

3. **Audio Device Check:**
   - Type: "Check my audio devices"
   - Roo will list available microphones and speakers

## Usage Examples

### Voice-Enabled Code Review
```
"Review this function and tell me what could be improved"
"Can you explain what this code does?"
"Help me refactor this to be more efficient"
```

### Voice Debugging Sessions
```
"This test is failing, can you help me debug it?"
"What might be causing this error?"
"Walk me through fixing this bug"
```

### Architecture Discussions
```
"Should I use a factory pattern here?"
"What's the best way to structure this module?"
"Let's discuss the architecture of this feature"
```

## Environment Variables

You can configure Voice Mode behavior with these environment variables:

**Option 1: Set in Roo Code config (shown above)**

**Option 2: Inherit from system**
```json
{
  "mcpServers": {
    "voice-mode": {
      "command": "uvx",
      "args": ["voice-mode"]
      // No env section - inherits from system
    }
  }
}
```

### Advanced Configuration

```bash
# Use multiple TTS providers with fallback
export VOICEMODE_TTS_BASE_URLS="http://127.0.0.1:8880/v1,https://api.openai.com/v1"

# Prefer specific voices
export VOICEMODE_TTS_VOICES="af_sky,nova,alloy"

# Enable debug logging
export VOICEMODE_DEBUG="true"
```

## Troubleshooting

### MCP Icon Not Visible
- Ensure Roo Code extension is fully loaded (wait for rocket icon to appear)
- Try reloading VS Code window: `Ctrl/Cmd + R`
- Check that you have the latest version of Roo Code

### Voice Mode Server Not Appearing
1. **Check Configuration File Location**
   - Verify the file exists at the correct path
   - Ensure JSON syntax is valid (no trailing commas, proper quotes)

2. **MCP Settings Issues**
   - Make sure "Enable MCP Servers" toggle is ON
   - Check for error messages in the MCP settings view
   - Look for red indicators next to the server name

3. **Server Start Failures**
   - Click the restart button next to the voice-mode server
   - Check VS Code Output panel → "Roo Code" for error logs
   - Verify `uvx` is in PATH: run `which uvx` in terminal

### Voice Mode Not Responding
1. **Audio Permissions**
   - **macOS**: System Settings → Privacy & Security → Microphone → Enable for Code
   - **Windows**: Settings → Privacy → Microphone → Allow apps to access
   - **Linux**: Check PulseAudio/PipeWire permissions

2. **OpenAI API Issues**
   - Verify API key is correct and has sufficient credits
   - Check for typos in the environment variable name
   - Test API key directly: `curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models`

3. **Debug Mode**
   - Add to your MCP configuration:
   ```json
   "env": {
     "OPENAI_API_KEY": "your-key",
     "VOICEMODE_DEBUG": "true"
   }
   ```
   - Check debug output in VS Code Output panel

### MCP Button Actions Not Working
- If clicking "Edit Global MCP" doesn't open the file:
  - Manually navigate to the configuration file path
  - Create the directory structure if it doesn't exist
- If server toggles don't respond:
  - Save any pending changes in the configuration file
  - Restart VS Code completely

### Common Configuration Mistakes
1. **Wrong JSON Structure**
   ```json
   // ❌ Wrong - don't use rooCode prefix
   {
     "rooCode.mcpServers": { ... }
   }
   
   // ✅ Correct
   {
     "mcpServers": { ... }
   }
   ```

2. **Missing Required Fields**
   ```json
   // ❌ Wrong - missing command
   {
     "mcpServers": {
       "voice-mode": {
         "args": ["voice-mode"]
       }
     }
   }
   
   // ✅ Correct - includes command
   {
     "mcpServers": {
       "voice-mode": {
         "command": "uvx",
         "args": ["voice-mode"]
       }
     }
   }
   ```

## Platform-Specific Notes

### macOS
- Grant microphone permissions: System Settings → Privacy & Security → Microphone → Code
- May need to restart VS Code after granting permissions

### Windows
- Best experience with WSL2
- Native Windows may require additional audio configuration

### Linux
- Ensure PulseAudio or PipeWire is running
- May need: `sudo usermod -a -G audio $USER`

## Visual Guide to MCP Interface

### MCP Servers View

When you click the MCP icon in Roo Code, you'll see:

1. **Main Settings Toggles**
   - ✅ **Enable MCP Servers**: Turn this ON to let Roo use tools from connected MCP servers
   - ✅ **Enable MCP Server Creation**: Enable this to have Roo help you build new custom MCP servers

2. **Server List**
   - Shows all configured servers (e.g., "voice-mode" with "global" tag)
   - Status indicators:
     - 🟢 Green dot = Server is active and running
     - 🔴 Red dot = Server has errors or is not running
     - Toggle switch to enable/disable each server

3. **Action Buttons** (at the bottom)
   - 📝 **Edit Global MCP**: Opens the global configuration file
   - 📝 **Edit Project MCP**: Opens project-specific configuration (if exists)
   - 🔄 **Refresh MCP Servers**: Reload all server configurations
   - 🔗 **Learn more about editing MCP settings files**: Link to documentation

4. **Server Controls** (for each server)
   - 🗑️ **Delete button**: Remove the server configuration
   - 🔄 **Restart button**: Restart the server if it's having issues
   - 🔵/⚪ **Enable toggle**: Turn the server on/off without deleting

## Advanced Configuration

### Project-Specific Configuration

Create a `.roo/mcp.json` file in your project root for project-specific settings:

```json
{
  "mcpServers": {
    "voice-mode": {
      "command": "uvx",
      "args": ["voice-mode"],
      "env": {
        "OPENAI_API_KEY": "project-specific-key",
        "VOICEMODE_TTS_VOICE": "nova"
      }
    }
  }
}
```

**Note**: Project settings override global settings for the same server name.

### Using Local STT/TTS Services

For complete privacy, use local services:

```json
{
  "mcpServers": {
    "voice-mode": {
      "command": "uvx",
      "args": ["voice-mode"],
      "env": {
        "VOICEMODE_TTS_BASE_URLS": "http://127.0.0.1:8880/v1,https://api.openai.com/v1",
        "VOICEMODE_STT_BASE_URLS": "http://127.0.0.1:2022/v1,https://api.openai.com/v1"
      }
    }
  }
}
```

### Using Different AI Models

Roo Code supports multiple AI models. Configure your preferred model in Roo Code settings, and Voice Mode will work with any model you choose.

## See Also

- 📚 [Voice Mode Documentation](../../../README.md)
- 🔧 [Configuration Reference](../../configuration.md)
- 🎤 [Local STT/TTS Setup](../../kokoro.md)
- 💬 [Roo Code GitHub](https://github.com/RooCodeInc/Roo-Code)
- 🐛 [Troubleshooting Guide](../../troubleshooting/README.md)
- 🚀 [Roo Code Documentation](https://roocode.com/docs)

---

**Need Help?** Join our [Discord community](https://discord.gg/Hm7dF3uCfG) or check [Roo Code issues](https://github.com/RooCodeInc/Roo-Code/issues)