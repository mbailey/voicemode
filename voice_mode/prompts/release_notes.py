"""Release notes prompt for displaying recent CHANGELOG entries."""

from voice_mode.server import mcp


@mcp.prompt(name="release-notes")
def release_notes_prompt(versions: str = "5") -> str:
    """View recent release notes from Voice Mode's CHANGELOG."""
    # Lazy import to break a circular import:
    #
    #   voice_mode/resources/changelog.py
    #     -> imports voice_mode/server.py
    #       -> auto-imports voice_mode/prompts/ (this package)
    #         -> loads release_notes.py (this module)
    #
    # Under pytest 9's stricter collection, importing changelog at
    # module load time fails with "cannot import name 'changelog_resource'
    # from partially initialized module". Deferring to call time breaks
    # the cycle because server/prompts finish initializing first.
    from voice_mode.resources.changelog import changelog_resource

    # Handle empty string from Claude Code
    if not versions or versions == "":
        versions = "5"

    # Get the changelog content from the resource
    # Resources decorated with @mcp.resource need to access the fn attribute
    if hasattr(changelog_resource, 'fn'):
        changelog_content = changelog_resource.fn()
    else:
        changelog_content = changelog_resource()
    
    # If we got an error message, return it
    if changelog_content.startswith("Error") or changelog_content.startswith("CHANGELOG.md not found"):
        return changelog_content
    
    # Parse the changelog content
    lines = changelog_content.split('\n')
    versions_found = []
    current_version = None
    current_content = []
    
    for line in lines:
        # Skip the header and empty lines at the beginning
        if line.startswith('# Changelog') or (not line.strip() and not current_version):
            continue
            
        # Check for version header (## [x.y.z] - date)
        if line.startswith('## [') and '] - ' in line:
            # Save previous version if exists
            if current_version and current_content:
                versions_found.append({
                    'header': current_version,
                    'content': '\n'.join(current_content).strip()
                })
                
            # Start new version
            current_version = line
            current_content = []
            
            # Stop if we have enough versions
            if len(versions_found) >= int(versions):
                break
        elif current_version:
            # Add content to current version
            current_content.append(line)
    
    # Don't forget the last version
    if current_version and current_content and len(versions_found) < int(versions):
        versions_found.append({
            'header': current_version,
            'content': '\n'.join(current_content).strip()
        })
    
    # Reverse to show oldest first (newest last)
    versions_found.reverse()
    
    # Format the output
    output = []
    for version in versions_found:
        output.append(version['header'])
        output.append(version['content'])
        output.append('')  # Empty line between versions
    
    result = '\n'.join(output).strip()
    
    # Return just the changelog entries without header/footer
    # to match Claude Code's clean output format
    return result