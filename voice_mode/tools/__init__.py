"""Auto-import all tools for registration with FastMCP."""
import os
import importlib
from pathlib import Path
import logging

logger = logging.getLogger("voicemode")

# Get the directory containing this file
tools_dir = Path(__file__).parent

def get_all_available_tools() -> set[str]:
    """
    Get all available tool names from the filesystem.

    Returns:
        Set of tool module names (without .py extension)
    """
    available_tools = set()

    # Get tools from main directory
    for file in tools_dir.glob("*.py"):
        if file.name != "__init__.py" and not file.name.startswith("_"):
            available_tools.add(file.stem)

    # Get tools from all subdirectories
    for subdir in tools_dir.iterdir():
        if subdir.is_dir() and not subdir.name.startswith("_") and not subdir.name.startswith("."):
            for file in subdir.glob("*.py"):
                if file.name != "__init__.py" and not file.name.startswith("_") and file.name != "helpers.py" and file.name != "types.py":
                    # Use flattened naming: subdir_toolname
                    tool_name = f"{subdir.name}_{file.stem}"
                    available_tools.add(tool_name)

    return available_tools

def parse_tool_list(tool_string: str) -> set[str]:
    """
    Parse comma-separated tool list into a set of tool names.

    Args:
        tool_string: Comma-separated string of tool names

    Returns:
        Set of trimmed tool names
    """
    if not tool_string:
        return set()
    return {t.strip() for t in tool_string.split(",") if t.strip()}

def determine_tools_to_load() -> tuple[set[str], str]:
    """
    Determine which tools should be loaded based on environment variables.

    Returns:
        Tuple of (tools_to_load, mode_description)
    """
    # Check for new environment variables
    enabled_tools = os.environ.get("VOICEMODE_TOOLS_ENABLED", "").strip()
    disabled_tools = os.environ.get("VOICEMODE_TOOLS_DISABLED", "").strip()

    # Check for legacy variable
    legacy_tools = os.environ.get("VOICEMODE_TOOLS", "").strip()

    # Get all available tools
    all_tools = get_all_available_tools()

    # Determine which tools to load
    if enabled_tools:
        # Whitelist mode - only load specified tools
        requested = parse_tool_list(enabled_tools)
        tools_to_load = requested & all_tools  # Only load tools that exist
        invalid = requested - all_tools

        if invalid:
            logger.warning(f"Requested tools not found: {', '.join(sorted(invalid))}")

        return tools_to_load, f"whitelist mode ({len(tools_to_load)} tools)"

    elif disabled_tools:
        # Blacklist mode - load all except specified
        excluded = parse_tool_list(disabled_tools)
        tools_to_load = all_tools - excluded

        # Log if any excluded tools don't exist (informational)
        nonexistent = excluded - all_tools
        if nonexistent:
            logger.debug(f"Excluded tools not found (ignoring): {', '.join(sorted(nonexistent))}")

        return tools_to_load, f"blacklist mode (excluding {len(excluded & all_tools)} tools)"

    elif legacy_tools:
        # Legacy support with deprecation warning
        logger.warning(
            "VOICEMODE_TOOLS is deprecated and will be removed in v5.0. "
            "Please use VOICEMODE_TOOLS_ENABLED or VOICEMODE_TOOLS_DISABLED instead."
        )
        requested = parse_tool_list(legacy_tools)
        tools_to_load = requested & all_tools
        invalid = requested - all_tools

        if invalid:
            logger.warning(f"Requested tools not found: {', '.join(sorted(invalid))}")

        return tools_to_load, f"legacy mode ({len(tools_to_load)} tools)"

    else:
        # Default - load essential tools only (converse, service)
        # This provides basic voice interaction and service management
        # while significantly reducing token usage in Claude Code
        default_tools = {"converse", "service"}
        tools_to_load = default_tools & all_tools  # Only load tools that exist
        return tools_to_load, f"default mode ({len(tools_to_load)} tools)"

def load_tool(tool_name: str) -> bool:
    """
    Load a single tool by name.

    Args:
        tool_name: Name of the tool to load

    Returns:
        True if successfully loaded, False otherwise
    """
    try:
        # First check if it exists as a regular tool in the main directory
        tool_file = tools_dir / f"{tool_name}.py"
        if tool_file.exists():
            logger.debug(f"Loading tool: {tool_name}")
            importlib.import_module(f".{tool_name}", package=__name__)
            return True

        # If not found and contains underscore, try as a subdirectory tool
        if "_" in tool_name:
            # Special case for sound_fonts directory (has underscore in name)
            if tool_name.startswith("sound_fonts_"):
                tool_file = tool_name.replace("sound_fonts_", "")
                module_path = f".sound_fonts.{tool_file}"
                try:
                    logger.debug(f"Loading sound_fonts tool: {tool_name}")
                    importlib.import_module(module_path, package=__name__)
                    return True
                except ImportError:
                    pass

            # Standard subdirectory pattern
            parts = tool_name.split("_", 1)
            if len(parts) == 2:
                subdir_name, tool_file = parts
                module_path = f".{subdir_name}.{tool_file}"
                try:
                    logger.debug(f"Loading subdirectory tool: {tool_name}")
                    importlib.import_module(module_path, package=__name__)
                    return True
                except ImportError:
                    pass

        logger.warning(f"Tool not found: {tool_name}")
        return False

    except ImportError as e:
        logger.error(f"Failed to import tool {tool_name}: {e}")
        return False

# Main loading logic
tools_to_load, mode = determine_tools_to_load()

if tools_to_load:
    logger.info(f"Tool loading: {mode} - loading {len(tools_to_load)} tools")

    # Sort for consistent loading order
    for tool_name in sorted(tools_to_load):
        load_tool(tool_name)
else:
    logger.warning("No tools to load based on current configuration")