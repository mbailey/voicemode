#!/bin/bash
# Sync VoiceMode telemetry from Cloudflare D1 to local SQLite database
#
# Usage: ./sync-telemetry-local.sh [output-path]
#
# Default output: ~/.voicemode/telemetry/telemetry.db

set -e

# Configuration
D1_DATABASE="voicemode-telemetry"
DEFAULT_OUTPUT_DIR="${HOME}/.voicemode/telemetry"
DEFAULT_OUTPUT_FILE="${DEFAULT_OUTPUT_DIR}/telemetry.db"

# Use custom path if provided, otherwise use default
OUTPUT_FILE="${1:-$DEFAULT_OUTPUT_FILE}"
OUTPUT_DIR="$(dirname "$OUTPUT_FILE")"

# Create output directory if needed
mkdir -p "$OUTPUT_DIR"

# Temporary file for SQL export
TEMP_SQL=$(mktemp)
trap "rm -f $TEMP_SQL" EXIT

echo "🔄 Syncing telemetry from Cloudflare D1..."
echo "   Database: $D1_DATABASE"
echo "   Output: $OUTPUT_FILE"

# Check if wrangler is installed
if ! command -v wrangler &> /dev/null; then
    echo "❌ Error: wrangler CLI not found"
    echo "   Install with: npm install -g wrangler"
    exit 1
fi

# Export from D1
echo "📥 Exporting from D1..."
wrangler d1 export "$D1_DATABASE" --remote --output="$TEMP_SQL" 2>&1 | grep -v "^⛅️\|^─\|^$"

# Check if export succeeded
if [ ! -s "$TEMP_SQL" ]; then
    echo "❌ Error: Export failed or produced empty file"
    exit 1
fi

# Import into local SQLite
echo "📦 Creating local SQLite database..."
rm -f "$OUTPUT_FILE"
sqlite3 "$OUTPUT_FILE" < "$TEMP_SQL"

# Verify
EVENT_COUNT=$(sqlite3 "$OUTPUT_FILE" "SELECT COUNT(*) FROM events;")
echo "✅ Sync complete!"
echo "   Events synced: $EVENT_COUNT"
echo "   Database: $OUTPUT_FILE"

# Show latest event
echo ""
echo "📊 Latest event:"
sqlite3 "$OUTPUT_FILE" "SELECT datetime(created_at) as synced, telemetry_id, json_extract(usage, '$.total_sessions') as sessions FROM events ORDER BY created_at DESC LIMIT 1;"
