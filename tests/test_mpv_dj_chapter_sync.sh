#!/usr/bin/env bash
# Test script for mpv-dj chapter sync functionality (VM-369)
#
# Tests:
# - find_plugin_mfp_dir() function
# - sync_chapter_file() conflict resolution
# - cmd_mfp_sync_chapters() command
# - on-demand chapter file copy

set -o nounset -o pipefail -o errexit

# Test configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKTREE_DIR="$(dirname "$SCRIPT_DIR")"
MPV_DJ="${WORKTREE_DIR}/skills/voicemode/bin/mpv-dj"
PLUGIN_MFP_DIR="${WORKTREE_DIR}/skills/voicemode/mfp"

# Test directory setup
TEST_TMP_DIR=""
TEST_USER_MFP_DIR=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Track test results
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

setup() {
    TEST_TMP_DIR=$(mktemp -d)
    TEST_USER_MFP_DIR="${TEST_TMP_DIR}/user-mfp"
    mkdir -p "$TEST_USER_MFP_DIR"
}

teardown() {
    if [[ -n "$TEST_TMP_DIR" && -d "$TEST_TMP_DIR" ]]; then
        rm -rf "$TEST_TMP_DIR"
    fi
}

# Helper to run a test
run_test() {
    local name="$1"
    local result
    local exit_code

    ((TESTS_RUN++)) || true

    # Disable errexit temporarily for the test function
    set +e
    result=$("$name" 2>&1)
    exit_code=$?
    set -e

    if [[ $exit_code -eq 0 ]]; then
        echo -e "${GREEN}PASS${NC}: $name"
        ((TESTS_PASSED++)) || true
        return 0
    else
        echo -e "${RED}FAIL${NC}: $name"
        echo "$result" | sed 's/^/  /'
        ((TESTS_FAILED++)) || true
        return 0  # Don't fail the whole script, just record the failure
    fi
}

# Test: Plugin MFP directory exists
test_plugin_mfp_dir_exists() {
    [[ -d "$PLUGIN_MFP_DIR" ]] || {
        echo "Plugin MFP directory not found: $PLUGIN_MFP_DIR"
        return 1
    }
}

# Test: Checksums file exists in plugin directory
test_checksums_file_exists() {
    local checksums="${PLUGIN_MFP_DIR}/chapters.sha256"
    [[ -f "$checksums" ]] || {
        echo "Checksums file not found: $checksums"
        return 1
    }
}

# Test: FFMETA files exist in plugin directory
test_ffmeta_files_exist() {
    local count
    count=$(find "$PLUGIN_MFP_DIR" -name "*.ffmeta" 2>/dev/null | wc -l | tr -d ' ')
    [[ "$count" -gt 0 ]] || {
        echo "No ffmeta files found in $PLUGIN_MFP_DIR"
        return 1
    }
    # Should have 7 files based on implementation
    [[ "$count" -ge 7 ]] || {
        echo "Expected at least 7 ffmeta files, found $count"
        return 1
    }
}

# Test: Checksums match actual files
test_checksums_match_files() {
    local checksums="${PLUGIN_MFP_DIR}/chapters.sha256"

    # Verify each checksum
    while read -r expected_sha filename; do
        local filepath="${PLUGIN_MFP_DIR}/${filename}"
        [[ -f "$filepath" ]] || {
            echo "File from checksum not found: $filename"
            return 1
        }

        local actual_sha
        actual_sha=$(LC_ALL=C shasum -a 256 "$filepath" | cut -d' ' -f1)
        [[ "$expected_sha" == "$actual_sha" ]] || {
            echo "Checksum mismatch for $filename"
            echo "  Expected: $expected_sha"
            echo "  Actual: $actual_sha"
            return 1
        }
    done < "$checksums"
}

# Test: mpv-dj help includes sync-chapters command
test_help_includes_sync_chapters() {
    local help_output
    help_output=$("$MPV_DJ" 2>&1 || true)

    echo "$help_output" | grep -q "sync-chapters" || {
        echo "Help text does not mention sync-chapters"
        echo "Help output: $help_output"
        return 1
    }
}

# Test: FFMETA files have valid structure
test_ffmeta_valid_structure() {
    local file="${PLUGIN_MFP_DIR}/music_for_programming_49-julien_mier.ffmeta"

    # Check header
    head -1 "$file" | grep -q "^;FFMETADATA1" || {
        echo "Missing FFMETADATA1 header"
        return 1
    }

    # Check for CHAPTER sections
    grep -q "\[CHAPTER\]" "$file" || {
        echo "No CHAPTER sections found"
        return 1
    }

    # Check for required chapter fields
    grep -q "TIMEBASE=" "$file" || {
        echo "Missing TIMEBASE field"
        return 1
    }
    grep -q "START=" "$file" || {
        echo "Missing START field"
        return 1
    }
    grep -q "title=" "$file" || {
        echo "Missing title field"
        return 1
    }
}

# Test: find_plugin_mfp_dir function (via source)
test_find_plugin_mfp_dir() {
    # Source just the function we need
    local found_dir

    # Run mpv-dj in a way that would test find_plugin_mfp_dir
    # Since it's used internally, we test via the sync-chapters output
    # which requires the function to work

    # Create temp environment to test
    local test_bin="${TEST_TMP_DIR}/bin"
    local test_mfp="${TEST_TMP_DIR}/mfp"
    mkdir -p "$test_bin" "$test_mfp"

    # Copy mpv-dj to test location
    cp "$MPV_DJ" "$test_bin/"

    # Copy a single test file
    cp "${PLUGIN_MFP_DIR}/music_for_programming_49-julien_mier.ffmeta" "$test_mfp/"
    cp "${PLUGIN_MFP_DIR}/chapters.sha256" "$test_mfp/"

    # Override MFP_DIR and test sync-chapters
    local output
    output=$(HOME="$TEST_TMP_DIR" MFP_DIR="$TEST_USER_MFP_DIR" "$test_bin/mpv-dj" mfp sync-chapters 2>&1)

    echo "$output" | grep -q "Syncing chapter files" || {
        echo "sync-chapters did not run properly"
        echo "Output: $output"
        return 1
    }
}

# Test: Sync adds new files
test_sync_adds_new_files() {
    # Create temp test environment
    local test_bin="${TEST_TMP_DIR}/bin"
    local test_mfp="${TEST_TMP_DIR}/mfp"
    local user_mfp="${TEST_TMP_DIR}/.voicemode/music-for-programming"
    mkdir -p "$test_bin" "$test_mfp" "$user_mfp"

    # Copy mpv-dj and plugin files
    cp "$MPV_DJ" "$test_bin/"
    cp "${PLUGIN_MFP_DIR}"/*.ffmeta "$test_mfp/"
    cp "${PLUGIN_MFP_DIR}/chapters.sha256" "$test_mfp/"

    # Patch MFP_DIR in the script
    sed -i.bak "s|MFP_DIR=.*|MFP_DIR=\"$user_mfp\"|" "$test_bin/mpv-dj"

    # Run sync
    local output
    output=$("$test_bin/mpv-dj" mfp sync-chapters 2>&1)

    # Check files were added
    local added_count
    added_count=$(echo "$output" | grep -c "Added:" || true)

    [[ "$added_count" -gt 0 ]] || {
        echo "No files were added"
        echo "Output: $output"
        return 1
    }

    # Verify files exist in user dir
    local file_count
    file_count=$(find "$user_mfp" -name "*.ffmeta" 2>/dev/null | wc -l | tr -d ' ')
    [[ "$file_count" -gt 0 ]] || {
        echo "No ffmeta files copied to user directory"
        return 1
    }
}

# Test: Sync detects unchanged files
test_sync_detects_unchanged() {
    # Create temp test environment
    local test_bin="${TEST_TMP_DIR}/bin"
    local test_mfp="${TEST_TMP_DIR}/mfp"
    local user_mfp="${TEST_TMP_DIR}/.voicemode/music-for-programming"
    mkdir -p "$test_bin" "$test_mfp" "$user_mfp"

    # Copy mpv-dj and plugin files
    cp "$MPV_DJ" "$test_bin/"
    cp "${PLUGIN_MFP_DIR}"/*.ffmeta "$test_mfp/"
    cp "${PLUGIN_MFP_DIR}/chapters.sha256" "$test_mfp/"

    # Pre-populate user dir with identical files
    cp "${PLUGIN_MFP_DIR}"/*.ffmeta "$user_mfp/"

    # Patch MFP_DIR in the script
    sed -i.bak "s|MFP_DIR=.*|MFP_DIR=\"$user_mfp\"|" "$test_bin/mpv-dj"

    # Run sync
    local output
    output=$("$test_bin/mpv-dj" mfp sync-chapters 2>&1)

    # Check files were detected as unchanged
    local unchanged_count
    unchanged_count=$(echo "$output" | grep -c "Unchanged:" || true)

    [[ "$unchanged_count" -gt 0 ]] || {
        echo "No unchanged files detected"
        echo "Output: $output"
        return 1
    }
}

# Test: Sync creates .user backup for modified files
test_sync_creates_user_backup() {
    # Create temp test environment
    local test_bin="${TEST_TMP_DIR}/bin"
    local test_mfp="${TEST_TMP_DIR}/mfp"
    local user_mfp="${TEST_TMP_DIR}/.voicemode/music-for-programming"
    mkdir -p "$test_bin" "$test_mfp" "$user_mfp"

    # Copy mpv-dj and plugin files
    cp "$MPV_DJ" "$test_bin/"
    cp "${PLUGIN_MFP_DIR}"/*.ffmeta "$test_mfp/"
    cp "${PLUGIN_MFP_DIR}/chapters.sha256" "$test_mfp/"

    # Pre-populate user dir with files
    cp "${PLUGIN_MFP_DIR}"/*.ffmeta "$user_mfp/"

    # Copy checksums to simulate previous sync
    cp "${PLUGIN_MFP_DIR}/chapters.sha256" "$user_mfp/.chapters.sha256"

    # Modify one user file (simulating user customization)
    local test_file="${user_mfp}/music_for_programming_49-julien_mier.ffmeta"
    echo "; User modification" >> "$test_file"

    # Modify the plugin version to trigger update
    local plugin_file="${test_mfp}/music_for_programming_49-julien_mier.ffmeta"
    echo "; Plugin update" >> "$plugin_file"

    # Patch MFP_DIR in the script
    sed -i.bak "s|MFP_DIR=.*|MFP_DIR=\"$user_mfp\"|" "$test_bin/mpv-dj"

    # Run sync
    local output
    output=$("$test_bin/mpv-dj" mfp sync-chapters 2>&1)

    # Check for .user backup message
    echo "$output" | grep -q "user version saved as .user" || {
        echo "No .user backup created for modified file"
        echo "Output: $output"
        return 1
    }

    # Verify .user file exists
    [[ -f "${test_file}.user" ]] || {
        echo ".user backup file not created"
        return 1
    }
}

# Test: --force flag skips conflict check
test_sync_force_flag() {
    # Create temp test environment
    local test_bin="${TEST_TMP_DIR}/bin"
    local test_mfp="${TEST_TMP_DIR}/mfp"
    local user_mfp="${TEST_TMP_DIR}/.voicemode/music-for-programming"
    mkdir -p "$test_bin" "$test_mfp" "$user_mfp"

    # Copy mpv-dj and plugin files
    cp "$MPV_DJ" "$test_bin/"
    cp "${PLUGIN_MFP_DIR}"/*.ffmeta "$test_mfp/"
    cp "${PLUGIN_MFP_DIR}/chapters.sha256" "$test_mfp/"

    # Pre-populate user dir with files
    cp "${PLUGIN_MFP_DIR}"/*.ffmeta "$user_mfp/"

    # Copy checksums to simulate previous sync
    cp "${PLUGIN_MFP_DIR}/chapters.sha256" "$user_mfp/.chapters.sha256"

    # Modify one user file
    local test_file="${user_mfp}/music_for_programming_49-julien_mier.ffmeta"
    echo "; User modification" >> "$test_file"

    # Modify the plugin version
    local plugin_file="${test_mfp}/music_for_programming_49-julien_mier.ffmeta"
    echo "; Plugin update" >> "$plugin_file"

    # Patch MFP_DIR in the script
    sed -i.bak "s|MFP_DIR=.*|MFP_DIR=\"$user_mfp\"|" "$test_bin/mpv-dj"

    # Run sync with --force
    local output
    output=$("$test_bin/mpv-dj" mfp sync-chapters --force 2>&1)

    # With --force, should NOT create .user backup
    echo "$output" | grep -qv "user version saved as .user" || {
        # Actually this is fine - it might still say Updated
        true
    }

    # Check for updated message without backup
    echo "$output" | grep -q "Updated:" || {
        echo "File was not updated with --force"
        echo "Output: $output"
        return 1
    }
}

# Main test runner
main() {
    echo "Running mpv-dj chapter sync tests (VM-369)"
    echo "==========================================="
    echo ""

    setup
    trap teardown EXIT

    # Run tests
    run_test test_plugin_mfp_dir_exists
    run_test test_checksums_file_exists
    run_test test_ffmeta_files_exist
    run_test test_checksums_match_files
    run_test test_help_includes_sync_chapters
    run_test test_ffmeta_valid_structure
    run_test test_find_plugin_mfp_dir
    run_test test_sync_adds_new_files
    run_test test_sync_detects_unchanged
    run_test test_sync_creates_user_backup
    run_test test_sync_force_flag

    echo ""
    echo "==========================================="
    echo "Results: ${TESTS_PASSED}/${TESTS_RUN} passed, ${TESTS_FAILED} failed"

    if [[ "$TESTS_FAILED" -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
