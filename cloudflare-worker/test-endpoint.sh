#!/bin/bash
#
# Test script for VoiceMode telemetry endpoint
#
# Usage:
#   ./test-endpoint.sh https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Endpoint URL (first argument or default)
ENDPOINT="${1:-https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry}"

if [[ "$ENDPOINT" == *"YOUR_SUBDOMAIN"* ]]; then
    echo -e "${RED}Error: Please provide your worker URL${NC}"
    echo "Usage: $0 <worker-url>"
    echo "Example: $0 https://voicemode-telemetry.my-account.workers.dev/telemetry"
    exit 1
fi

echo -e "${YELLOW}Testing VoiceMode Telemetry Endpoint${NC}"
echo "Endpoint: $ENDPOINT"
echo ""

# Test 1: Valid payload
echo -e "${YELLOW}Test 1: Valid payload${NC}"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "test_'$(date +%s)'",
    "telemetry_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "environment": {
      "os": "Linux",
      "version": "1.0.0",
      "installation_method": "uv",
      "mcp_host": "claude-code",
      "execution_source": "mcp"
    },
    "usage": {
      "total_sessions": 5,
      "duration_distribution": {"1-5min": 3, "5-10min": 2},
      "transport_usage": {"local": 4, "livekit": 1},
      "provider_usage": {
        "tts": {"openai": 3, "kokoro": 2},
        "stt": {"whisper-local": 5}
      }
    }
  }')

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ PASSED${NC} - Status: $HTTP_CODE"
    echo "Response: $BODY"
else
    echo -e "${RED}✗ FAILED${NC} - Expected 200, got $HTTP_CODE"
    echo "Response: $BODY"
fi
echo ""

# Test 2: Idempotency (same event_id)
echo -e "${YELLOW}Test 2: Idempotency (duplicate event_id)${NC}"
EVENT_ID="idempotency_test_$(date +%s)"
TELEMETRY_ID="650e8400-e29b-41d4-a716-446655440001"

# First request
curl -s -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "'$EVENT_ID'",
    "telemetry_id": "'$TELEMETRY_ID'",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "environment": {
      "os": "Linux",
      "version": "1.0.0",
      "installation_method": "dev",
      "mcp_host": "claude-code",
      "execution_source": "mcp"
    },
    "usage": {"total_sessions": 1}
  }' > /dev/null

# Second request (duplicate)
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "'$EVENT_ID'",
    "telemetry_id": "'$TELEMETRY_ID'",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "environment": {
      "os": "Linux",
      "version": "1.0.0",
      "installation_method": "dev",
      "mcp_host": "claude-code",
      "execution_source": "mcp"
    },
    "usage": {"total_sessions": 1}
  }')

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -eq 200 ] && echo "$BODY" | grep -q "already recorded"; then
    echo -e "${GREEN}✓ PASSED${NC} - Status: $HTTP_CODE (idempotent)"
    echo "Response: $BODY"
else
    echo -e "${RED}✗ FAILED${NC} - Expected idempotent response"
    echo "Response: $BODY"
fi
echo ""

# Test 3: Missing required field
echo -e "${YELLOW}Test 3: Invalid payload (missing telemetry_id)${NC}"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "test_invalid",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "environment": {"os": "Linux", "version": "1.0.0"},
    "usage": {"total_sessions": 1}
  }')

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -eq 400 ]; then
    echo -e "${GREEN}✓ PASSED${NC} - Status: $HTTP_CODE"
    echo "Response: $BODY"
else
    echo -e "${RED}✗ FAILED${NC} - Expected 400, got $HTTP_CODE"
    echo "Response: $BODY"
fi
echo ""

# Test 4: Invalid UUID format
echo -e "${YELLOW}Test 4: Invalid telemetry_id format${NC}"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "test_invalid_uuid",
    "telemetry_id": "not-a-valid-uuid",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "environment": {"os": "Linux", "version": "1.0.0"},
    "usage": {"total_sessions": 1}
  }')

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -eq 400 ] && echo "$BODY" | grep -q "UUID"; then
    echo -e "${GREEN}✓ PASSED${NC} - Status: $HTTP_CODE"
    echo "Response: $BODY"
else
    echo -e "${RED}✗ FAILED${NC} - Expected 400 with UUID error"
    echo "Response: $BODY"
fi
echo ""

# Test 5: Rate limiting (requires multiple rapid requests)
echo -e "${YELLOW}Test 5: Rate limiting (11 requests in rapid succession)${NC}"
RATE_LIMIT_ID="750e8400-e29b-41d4-a716-446655440002"
RATE_LIMITED=false

for i in {1..11}; do
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$ENDPOINT" \
      -H "Content-Type: application/json" \
      -d '{
        "event_id": "rate_test_'$i'_'$(date +%s)'",
        "telemetry_id": "'$RATE_LIMIT_ID'",
        "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
        "environment": {"os": "Linux", "version": "1.0.0"},
        "usage": {"total_sessions": 1}
      }')

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    if [ "$HTTP_CODE" -eq 429 ]; then
        RATE_LIMITED=true
        BODY=$(echo "$RESPONSE" | sed '$d')
        echo -e "${GREEN}✓ PASSED${NC} - Rate limit triggered at request $i"
        echo "Response: $BODY"
        break
    fi
done

if [ "$RATE_LIMITED" = false ]; then
    echo -e "${YELLOW}⚠ WARNING${NC} - Rate limit not triggered (may need to wait or adjust limits)"
fi
echo ""

# Test 6: CORS preflight
echo -e "${YELLOW}Test 6: CORS preflight (OPTIONS request)${NC}"
RESPONSE=$(curl -s -w "\n%{http_code}" -X OPTIONS "$ENDPOINT" \
  -H "Origin: http://example.com" \
  -H "Access-Control-Request-Method: POST")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" -eq 204 ]; then
    echo -e "${GREEN}✓ PASSED${NC} - Status: $HTTP_CODE"
else
    echo -e "${RED}✗ FAILED${NC} - Expected 204, got $HTTP_CODE"
fi
echo ""

echo -e "${GREEN}Test suite complete!${NC}"
