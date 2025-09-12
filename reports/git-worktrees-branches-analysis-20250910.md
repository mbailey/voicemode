# Git Worktrees and Branches Analysis Report
**Project**: VoiceMode  
**Location**: /Users/admin/Code/github.com/mbailey/voicemode  
**Date**: 2025-09-10  
**Current Branch**: feat/mcp-registry-submission  

## Executive Summary

The VoiceMode repository currently has 7 git worktrees across multiple locations, 37 local branches, and 1 file with uncommitted changes. Several branches have been merged to master and can be safely deleted, and multiple worktrees can be removed as their branches are already merged. The repository shows signs of experimental work with abandoned branches that need cleanup.

## Current Worktrees Status

### Active Worktrees
| Location | Branch | Commit | Status |
|----------|--------|--------|--------|
| /Users/admin/Code/github.com/mbailey/voicemode | feat/mcp-registry-submission | fddbd37 | **ACTIVE** - Has uncommitted changes |
| /Users/admin/Code/github.com/ai-cora/cora/git/worktrees/voicemode_feat_integrate-sound-fonts | feat/integrate-sound-fonts | 8666a4d | Clean - Already merged to master |
| /Users/admin/Code/github.com/ai-cora/cora/git/worktrees/voicemode_feat_think-out-loud-mode | feat/think-out-loud-mode | 597cd66 | Clean - Already merged to master |
| /Users/admin/Code/github.com/ai-cora/cora/git/worktrees/voicemode_feat_timing-hooks | experimental/singing-manager | 514c710 | Clean - Not merged |
| /Users/admin/Code/github.com/ai-cora/cora/git/worktrees/voicemode_feat_word-timestamps | feat/word-timestamps | 961f773 | Clean - Already merged to master |
| /Users/admin/Code/github.com/mbailey/voicemode-refactor-prune | refactor/prune | b528504 | Clean - Already merged to master |
| /Users/admin/Code/github.com/worktrees/voicemode_tool-descriptions | refactor/tool-descriptions-to-files | 0de4c90 | Clean - Already merged to master |

### Worktree Health Status
- All worktree directories exist and are accessible
- No orphaned worktrees detected
- Most worktrees are for branches already merged to master

## Uncommitted Changes

### Main Worktree (/Users/admin/Code/github.com/mbailey/voicemode)
- **Branch**: feat/mcp-registry-submission
- **Uncommitted Files**:
  - `.github/workflows/publish-pypi-and-mcp.yml` (untracked)

### All Other Worktrees
- All other worktrees are clean with no uncommitted changes

## Branch Analysis

### Branches Already Merged to Master (Can be Deleted)
These branches have been fully merged and can be safely deleted:
- 20250903-aborted-attempt-to-include-soundfont-pack-in-package
- dev
- feat/integrate-sound-fonts *(has worktree)*
- feat/pronunciation-middleware
- feat/selective-tool-loading
- feat/test-coverage-reporting
- feat/think-out-loud
- feat/think-out-loud-mode *(has worktree)*
- feat/word-timestamps *(has worktree)*
- refactor/project-config-files
- refactor/prune *(has worktree)*
- refactor/tool-descriptions-to-files *(has worktree)*
- release

### Branches Not Merged to Master
These branches contain unmerged work:
- 20250901-papa-broke-it
- broken
- broken-20250906
- experimental/singing-manager *(has worktree)*
- feat/audio-device-hotswap
- feat/integrate-sound-fonts-papa-bear-broke-2025-09-01
- feat/mcp-registry-submission *(current branch with uncommitted changes)*
- feat/timing-hooks
- feat/web-dashboard
- feat/web-dashboard-clean
- feature/conversation-browser-library-broken
- fix/cli-help-text
- fix/registry-health-removal
- fix/whisper-installer-enable
- next
- perf/whisper-coreml-optimization
- refactor/config-system
- refactor/install-script-rename
- safety-commit-2025-01-09

### Branches Without Remote Tracking
These local branches have no remote tracking branch:
- 20250901-papa-broke-it
- 20250903-aborted-attempt-to-include-soundfont-pack-in-package
- broken
- broken-20250906
- dev
- experimental/singing-manager
- feat/integrate-sound-fonts
- feat/integrate-sound-fonts-papa-bear-broke-2025-09-01
- feat/mcp-registry-submission
- feat/selective-tool-loading
- feat/test-coverage-reporting
- feat/think-out-loud
- feat/timing-hooks
- feat/web-dashboard
- feat/word-timestamps
- fix/registry-health-removal
- next
- perf/whisper-coreml-optimization
- refactor/prune
- refactor/tool-descriptions-to-files
- release
- safety-commit-2025-01-09

### Branches That Need to be Pushed
- **feat/mcp-registry-submission**: Has 1 unpushed commit (fddbd37 - "feat: add MCP registry support with server.json and mcp-name")

## Remote Branches Without Local Counterparts
These remote branches exist but have no local branch:
- origin/add-voice-chat-prompt
- origin/feat/audio-device-enhancement
- origin/feat/configurable-pip-delays
- origin/feat/install-logging-error-reporting
- origin/feature/exchange-logging-improvements
- origin/feature/wake-word-detection
- origin/fix-ffmpeg-detection
- origin/fix/coreml-torch-dependency
- origin/fix/stt-audio-saving-simple-failover
- origin/refactor/docs-structure

## Problematic Situations

### Duplicate/Similar Branches
- **broken** and **broken-20250906**: Both point to the same commit (f1b74e2)
- **feat/integrate-sound-fonts** and **feat/integrate-sound-fonts-papa-bear-broke-2025-09-01**: Appear to be related work
- Multiple experimental branches without clear purpose (broken, papa-broke-it)

### Worktree/Branch Naming Mismatch
- Worktree `voicemode_feat_timing-hooks` contains branch `experimental/singing-manager` (naming mismatch)

### Abandoned Work
- Several "broken" and "papa-broke-it" branches suggest interrupted or failed work
- safety-commit-2025-01-09 appears to be a backup branch

## Recommendations

### Immediate Actions

1. **Commit or stash changes in main worktree**:
   ```bash
   cd /Users/admin/Code/github.com/mbailey/voicemode
   git add .github/workflows/publish-pypi-and-mcp.yml
   git commit -m "feat: add GitHub workflow for PyPI and MCP publishing"
   # OR
   git stash push -m "WIP: GitHub workflow for publishing"
   ```

2. **Push feat/mcp-registry-submission to remote**:
   ```bash
   git push -u origin feat/mcp-registry-submission
   ```

### Worktree Cleanup
Remove worktrees for already-merged branches:
```bash
# Remove merged worktrees
git worktree remove /Users/admin/Code/github.com/ai-cora/cora/git/worktrees/voicemode_feat_integrate-sound-fonts
git worktree remove /Users/admin/Code/github.com/ai-cora/cora/git/worktrees/voicemode_feat_think-out-loud-mode
git worktree remove /Users/admin/Code/github.com/ai-cora/cora/git/worktrees/voicemode_feat_word-timestamps
git worktree remove /Users/admin/Code/github.com/mbailey/voicemode-refactor-prune
git worktree remove /Users/admin/Code/github.com/worktrees/voicemode_tool-descriptions
```

### Branch Cleanup
Delete local branches that are already merged:
```bash
# Delete merged branches (excluding those with worktrees until worktrees are removed)
git branch -d 20250903-aborted-attempt-to-include-soundfont-pack-in-package
git branch -d dev
git branch -d feat/pronunciation-middleware
git branch -d feat/selective-tool-loading
git branch -d feat/test-coverage-reporting
git branch -d feat/think-out-loud
git branch -d refactor/project-config-files
git branch -d release

# After removing worktrees, also delete:
git branch -d feat/integrate-sound-fonts
git branch -d feat/think-out-loud-mode
git branch -d feat/word-timestamps
git branch -d refactor/prune
git branch -d refactor/tool-descriptions-to-files
```

### Branch Review Needed
Review and potentially delete these questionable branches:
```bash
# Review broken/abandoned branches
git log --oneline -5 broken
git log --oneline -5 broken-20250906
git log --oneline -5 20250901-papa-broke-it
git log --oneline -5 safety-commit-2025-01-09

# If no longer needed, force delete:
git branch -D broken
git branch -D broken-20250906
git branch -D 20250901-papa-broke-it
```

### Long-term Maintenance

1. **Establish branch naming conventions**:
   - Use consistent prefixes (feat/, fix/, refactor/, etc.)
   - Avoid temporary names like "broken" or personal references
   - Document experimental work properly

2. **Regular cleanup routine**:
   - Remove merged branches weekly
   - Clean up worktrees when branches are merged
   - Push or delete local-only branches regularly

3. **Worktree organization**:
   - Keep worktrees in a consistent location
   - Name worktree directories to match branch names
   - Document active worktrees in project README

## Summary Statistics

- **Total Worktrees**: 7
- **Worktrees to Remove**: 5 (already merged)
- **Total Local Branches**: 37
- **Branches to Delete**: 13 (already merged)
- **Branches Without Remote**: 24
- **Branches Needing Push**: 1 (feat/mcp-registry-submission)
- **Uncommitted Changes**: 1 file in main worktree

## Notes

- A deprecation warning for Python's `audioop` module appears in Python 3.11, which will be removed in Python 3.13
- The repository structure suggests active development with multiple experimental features
- Most work appears to be feature development rather than bug fixes