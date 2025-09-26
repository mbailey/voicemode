# Refactor: Flatten Services Directory Structure

## Problem
The current tool organization has an unnecessary `services/` intermediate directory that complicates tool loading logic and causes ambiguity in tool naming patterns. This structure led to the configuration_management loading issue where tools with underscores were misinterpreted.

## Current Structure
```
voice_mode/tools/
├── configuration_management.py    # Regular tool with underscore
├── voice_registry.py              # Regular tool with underscore
├── services/                      # Unnecessary intermediate directory
│   ├── kokoro/
│   │   ├── install.py
│   │   └── uninstall.py
│   ├── whisper/
│   │   ├── install.py
│   │   └── ...
│   └── livekit/
│       ├── install.py
│       └── ...
├── sound_fonts/                   # Direct subdirectory (good pattern)
└── transcription/                 # Direct subdirectory (good pattern)
```

## Proposed Structure
```
voice_mode/tools/
├── configuration_management.py    # Regular tool
├── voice_registry.py              # Regular tool
├── kokoro/                        # Service tools at same level as other subdirs
│   ├── install.py                 # Loaded as kokoro_install
│   └── uninstall.py               # Loaded as kokoro_uninstall
├── whisper/                       # Service tools at same level
│   ├── install.py                 # Loaded as whisper_install
│   └── ...
├── livekit/                       # Service tools at same level
│   ├── install.py                 # Loaded as livekit_install
│   └── ...
├── sound_fonts/                   # Existing pattern unchanged
└── transcription/                 # Existing pattern unchanged
```

## Benefits
1. **Consistency**: All subdirectories treated uniformly
2. **Simplicity**: Single pattern for all subdirectory tools
3. **No ambiguity**: Clear distinction between regular and subdirectory tools
4. **Easier discovery**: Simpler mental model and file navigation

## Loading Logic Simplification

### Current (complex)
```python
# Must handle special case for services/
if file in tools/:
    load as regular tool
elif file in services/{service}/:
    load as {service}_{tool}
elif file in other_subdir/:
    load as {subdir}_{tool}
```

### Proposed (simple)
```python
# Uniform handling for all subdirectories
if file in tools/:
    load as regular tool
elif file in {any_subdir}/:
    load as {subdir}_{tool}
```

## Migration Requirements

### 1. File System Changes
- Move `tools/services/kokoro/` → `tools/kokoro/`
- Move `tools/services/whisper/` → `tools/whisper/`
- Move `tools/services/livekit/` → `tools/livekit/`
- Handle `services/list_versions.py` and `services/version_info.py`

### 2. Import Updates
- Update any imports from `voice_mode.tools.services.{service}` to `voice_mode.tools.{service}`
- Update load_tool() function to use simplified logic
- Update get_all_available_tools() to scan all subdirectories uniformly

### 3. Documentation Updates
- Update tool loading architecture documentation
- Update any references to services directory
- Update examples in code comments

### 4. Testing Updates
- Update test paths that reference services/
- Add tests for the new structure
- Ensure backward compatibility during transition

## Implementation Plan

### Phase 1: Setup and Preparation (5 minutes)

#### 1.1 Create Feature Branch
```bash
cd /Users/admin/Code/github.com/mbailey/voicemode
git checkout master
git pull origin master  # Ensure up to date
git checkout -b refactor/flatten-services-directory
```

#### 1.2 Initial Commit - Document the Plan
```bash
# Copy this README to the codebase for documentation
cp /Users/admin/tasks/voicemode/refactor_flatten-services-directory/README.md \
   docs/architecture/refactoring-services-flatten.md
git add docs/architecture/refactoring-services-flatten.md
git commit -m "docs: Add refactoring plan for flattening services directory

Document the plan to flatten the services/ intermediate directory
to simplify tool loading logic and eliminate ambiguity."
```

### Phase 2: Handle Special Files (10 minutes)

#### 2.1 Analyze Dependencies on version_info.py and list_versions.py
These files are currently in `services/` but are imported by:
- `voice_mode/tools/service.py` (imports `get_kokoro_version` from version_info)

**Decision**: Move to `voice_mode/utils/services/` to keep them as utilities rather than tools.

#### 2.2 Move Version Files
```bash
# Create utils/services directory if it doesn't exist
mkdir -p voice_mode/utils/services

# Move version files to utils
git mv voice_mode/tools/services/version_info.py voice_mode/utils/services/
git mv voice_mode/tools/services/list_versions.py voice_mode/utils/services/

# Update imports in service.py
# Change: from voice_mode.tools.services.version_info import get_kokoro_version
# To: from voice_mode.utils.services.version_info import get_kokoro_version
```

#### 2.3 Commit Version Files Move
```bash
git add -A
git commit -m "refactor: Move version utilities from tools to utils

Move version_info.py and list_versions.py to utils/services/ as they
are utilities rather than MCP tools."
```

### Phase 3: Update Tool Loading Logic First (15 minutes)

#### 3.1 Simplify tools/__init__.py
Update the tool loading to handle all subdirectories uniformly:
- Remove special handling for `services/` directory
- Treat all subdirectories the same way
- Simplify `load_tool()` function

#### 3.2 Test Loading Logic
```bash
# Run tests to ensure logic changes work
uv run pytest tests/test_tool_loading.py -v  # If exists
```

#### 3.3 Commit Loading Logic Changes
```bash
git add voice_mode/tools/__init__.py
git commit -m "refactor: Simplify tool loading logic for uniform subdirectory handling

Remove special case for services/ directory and treat all subdirectories
uniformly. This prepares for the directory structure flattening."
```

### Phase 4: Move Service Directories (20 minutes)

#### 4.1 Move Whisper Service
```bash
# Move whisper directory up one level
git mv voice_mode/tools/services/whisper voice_mode/tools/

# Update all whisper imports
# Use sed or manual updates for all files importing from services.whisper
```

#### 4.2 Update Whisper Imports
Files to update (based on grep results):
- `voice_mode/cli.py` (8 imports)
- `voice_mode/tools/services/whisper/__init__.py` (7 imports - now at tools/whisper/)
- `voice_mode/tools/services/whisper/model_*.py` files (4 files)
- Tests: none directly import whisper

#### 4.3 Test Whisper Tools
```bash
# Test whisper functionality
uv run pytest tests/ -k whisper -v
```

#### 4.4 Commit Whisper Move
```bash
git add -A
git commit -m "refactor: Move whisper service tools up one directory level

Move tools/services/whisper/ to tools/whisper/ and update all imports."
```

#### 4.5 Move Kokoro Service
```bash
# Move kokoro directory
git mv voice_mode/tools/services/kokoro voice_mode/tools/

# Update kokoro imports in cli.py (2 imports)
```

#### 4.6 Commit Kokoro Move
```bash
git add -A
git commit -m "refactor: Move kokoro service tools up one directory level

Move tools/services/kokoro/ to tools/kokoro/ and update imports."
```

#### 4.7 Move LiveKit Service
```bash
# Move livekit directory
git mv voice_mode/tools/services/livekit voice_mode/tools/

# Update livekit imports in:
# - cli.py (10 imports)
# - service.py (1 import)
# - tests/test_livekit_service.py (3 imports)
# - tests/test_livekit_mcp_tools.py (2 imports)
```

#### 4.8 Commit LiveKit Move
```bash
git add -A
git commit -m "refactor: Move livekit service tools up one directory level

Move tools/services/livekit/ to tools/livekit/ and update all imports."
```

### Phase 5: Cleanup and Remove Services Directory (5 minutes)

#### 5.1 Remove Empty Services Directory
```bash
# Verify services directory is empty
ls -la voice_mode/tools/services/
# Should only show . and .. (empty)

# Remove the directory
rmdir voice_mode/tools/services
```

#### 5.2 Final Verification
```bash
# Verify structure
tree voice_mode/tools -d -L 1

# Should show:
# voice_mode/tools
# ├── kokoro
# ├── livekit
# ├── sound_fonts
# ├── transcription
# └── whisper
```

#### 5.3 Commit Cleanup
```bash
git add -A
git commit -m "refactor: Remove empty services directory

Complete the flattening by removing the now-empty services directory."
```

### Phase 6: Update Documentation (10 minutes)

#### 6.1 Update Tool Loading Architecture Doc
Update `docs/reference/tool-loading-architecture.md` to reflect new structure.

#### 6.2 Update CLAUDE.md
Update the architecture overview if it mentions services structure.

#### 6.3 Commit Documentation Updates
```bash
git add docs/
git add CLAUDE.md  # if modified
git commit -m "docs: Update documentation to reflect flattened tool structure

Update architecture docs and CLAUDE.md to describe the simplified
tool organization without the services/ intermediate directory."
```

### Phase 7: Testing and Validation (15 minutes)

#### 7.1 Run Full Test Suite
```bash
# Run all tests
make test

# Or directly
uv run pytest tests/ -v --tb=short
```

#### 7.2 Test MCP Server
```bash
# Test that MCP server starts and loads tools correctly
voicemode server --debug 2>&1 | head -50
```

#### 7.3 Test Individual Service Commands
```bash
# Test CLI commands still work
voicemode whisper models
voicemode kokoro --help
voicemode livekit --help
```

#### 7.4 Fix Any Issues
If tests fail, create fix commits with clear messages.

### Phase 8: Final Review and Merge (10 minutes)

#### 8.1 Review Changes
```bash
# Review all changes
git log --oneline -10
git diff master...HEAD --stat

# Detailed diff for key files
git diff master...HEAD -- voice_mode/tools/__init__.py
```

#### 8.2 Push Feature Branch
```bash
git push -u origin refactor/flatten-services-directory
```

#### 8.3 Create Pull Request
```bash
# Using gh CLI
gh pr create --title "Refactor: Flatten services directory structure" \
  --body "$(cat <<'EOF'
## Summary
- Removes unnecessary `services/` intermediate directory
- Simplifies tool loading logic by treating all subdirectories uniformly
- Fixes ambiguity issues with underscore-named tools

## Changes
- Moved `tools/services/whisper/` → `tools/whisper/`
- Moved `tools/services/kokoro/` → `tools/kokoro/`
- Moved `tools/services/livekit/` → `tools/livekit/`
- Moved version utilities to `utils/services/`
- Updated all imports throughout the codebase
- Simplified tool loading logic in `tools/__init__.py`

## Benefits
- Consistent directory structure
- Simpler mental model for tool organization
- Eliminates special-case handling in tool loader
- Prevents future confusion with underscore-named tools

## Testing
- All tests pass
- MCP server loads tools correctly
- CLI commands work as expected
- Tool names exposed to MCP remain unchanged

Fixes the issue where `configuration_management` and `voice_registry` were
being incorrectly interpreted as service tools.
EOF
)"
```

#### 8.4 Merge Strategy
After PR review and approval:
```bash
# Merge using squash or merge commit
gh pr merge --merge  # or --squash
```

## Import Update Commands

### Batch Update Commands for Each Service

#### Whisper Import Updates
```bash
# Update CLI imports
sed -i '' 's/from voice_mode\.tools\.services\.whisper/from voice_mode.tools.whisper/g' voice_mode/cli.py

# Update internal whisper imports
find voice_mode/tools/whisper -name "*.py" -exec \
  sed -i '' 's/from voice_mode\.tools\.services\.whisper/from voice_mode.tools.whisper/g' {} \;
```

#### Kokoro Import Updates
```bash
# Update CLI imports
sed -i '' 's/from voice_mode\.tools\.services\.kokoro/from voice_mode.tools.kokoro/g' voice_mode/cli.py

# Update service.py import
sed -i '' 's/from voice_mode\.tools\.services\.version_info/from voice_mode.utils.services.version_info/g' voice_mode/tools/service.py
```

#### LiveKit Import Updates
```bash
# Update CLI imports
sed -i '' 's/from voice_mode\.tools\.services\.livekit/from voice_mode.tools.livekit/g' voice_mode/cli.py

# Update service.py import
sed -i '' 's/from voice_mode\.tools\.services\.livekit/from voice_mode.tools.livekit/g' voice_mode/tools/service.py

# Update test imports
sed -i '' 's/from voice_mode\.tools\.services\.livekit/from voice_mode.tools.livekit/g' tests/test_livekit_*.py
```

## Rollback Plan

If issues are discovered after starting:

### Quick Rollback (if not pushed)
```bash
# Discard all changes and return to master
git reset --hard master
git clean -fd
```

### Rollback After Push
```bash
# Create a revert branch
git checkout master
git checkout -b revert/flatten-services

# Revert the merge commit (if merged)
git revert -m 1 <merge-commit-sha>

# Or revert individual commits in reverse order
git revert <commit-n>
git revert <commit-n-1>
# ... continue for all commits

# Push and create revert PR
git push -u origin revert/flatten-services
gh pr create --title "Revert: Undo services directory flattening"
```

## Risk Mitigation

1. **Test at each phase**: Run tests after each major change
2. **Atomic commits**: Each commit should be self-contained and functional
3. **Import verification**: Use grep to verify all imports are updated
4. **Tool loading verification**: Check MCP server debug output shows all tools loading
5. **Keep backup**: Before starting, create a backup branch: `git branch backup/pre-flatten`

## Estimated Timeline

- **Phase 1**: Setup and Preparation - 5 minutes
- **Phase 2**: Handle Special Files - 10 minutes
- **Phase 3**: Update Tool Loading Logic - 15 minutes
- **Phase 4**: Move Service Directories - 20 minutes
- **Phase 5**: Cleanup - 5 minutes
- **Phase 6**: Documentation - 10 minutes
- **Phase 7**: Testing - 15 minutes
- **Phase 8**: Review and Merge - 10 minutes

**Total Estimated Time**: 90 minutes (1.5 hours)

## Success Criteria

1. ✅ All tools load correctly with new structure
2. ✅ No services/ directory remains
3. ✅ Loading logic is simplified and more maintainable
4. ✅ All tests pass
5. ✅ Documentation reflects new structure
6. ✅ Tool names exposed to MCP remain unchanged (e.g., `whisper_install`, `kokoro_install`)
7. ✅ No breaking changes for end users

## Notes

- The refactoring is purely internal - MCP tool names remain the same
- This fixes the root cause of the configuration_management loading issue
- Future subdirectories can be added without special handling
- The pattern now matches what's already working for `sound_fonts/` and `transcription/`