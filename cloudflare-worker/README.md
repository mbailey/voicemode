# VoiceMode Telemetry Cloudflare Worker

This directory contains the Cloudflare Worker implementation for VoiceMode's telemetry endpoint. The worker receives, validates, rate-limits, and stores telemetry events from VoiceMode clients.

## Features

- **Payload Validation**: Strict JSON schema validation for all incoming events
- **Rate Limiting**:
  - Per anonymous ID: 10 events/hour
  - Per IP address: 100 events/hour
- **Idempotency**: Duplicate event_id submissions return success without re-storing
- **Privacy**: IP addresses are SHA-256 hashed before storage
- **Automatic Cleanup**: Daily cron job removes events older than 90 days
- **CORS Support**: Allows cross-origin requests from VoiceMode clients

## Architecture

```
┌─────────────────┐
│ VoiceMode Client│
│  (Python)       │
└────────┬────────┘
         │ POST /telemetry
         │ {event_id, telemetry_id, timestamp, environment, usage}
         ▼
┌─────────────────────────────────┐
│  Cloudflare Worker              │
│  ├─ Validate payload            │
│  ├─ Check idempotency (D1)      │
│  ├─ Check rate limits (KV)      │
│  ├─ Store event (D1)            │
│  └─ Increment rate counters (KV)│
└─────────────────────────────────┘
         │
         ├────────────┬────────────┐
         ▼            ▼            ▼
     ┌──────┐    ┌──────┐    ┌──────────┐
     │  D1  │    │  KV  │    │Analytics │
     │ (DB) │    │(Rate)│    │ (Future) │
     └──────┘    └──────┘    └──────────┘
```

## Prerequisites

1. **Cloudflare Account**
   - Sign up at https://dash.cloudflare.com/sign-up
   - Free tier is sufficient for MVP (< 1000 users)

2. **Node.js and npm**
   - Install from https://nodejs.org/ (v18+ recommended)

3. **Wrangler CLI**
   - Install: `npm install -g wrangler`
   - Documentation: https://developers.cloudflare.com/workers/wrangler/

## Setup Instructions

### 1. Install Wrangler

```bash
npm install -g wrangler
```

### 2. Authenticate with Cloudflare

```bash
wrangler login
```

This will open a browser window to authorize Wrangler with your Cloudflare account.

### 3. Get Your Account ID

1. Go to https://dash.cloudflare.com/
2. Select your account
3. Copy the **Account ID** from the right sidebar
4. Edit `wrangler.toml` and replace `YOUR_ACCOUNT_ID_HERE` with your Account ID

### 4. Create KV Namespace (for rate limiting)

```bash
wrangler kv:namespace create "RATE_LIMITS"
```

Copy the `id` from the output and update `wrangler.toml`:

```toml
[[kv_namespaces]]
binding = "KV"
id = "your_kv_namespace_id_here"  # Replace with actual ID
```

### 5. Create D1 Database (for telemetry events)

```bash
wrangler d1 create voicemode-telemetry
```

Copy the `database_id` from the output and update `wrangler.toml`:

```toml
[[d1_databases]]
binding = "DB"
database_name = "voicemode-telemetry"
database_id = "your_d1_database_id_here"  # Replace with actual ID
```

### 6. Initialize Database Schema

```bash
wrangler d1 execute voicemode-telemetry --file=schema.sql
```

This creates the `events` table and necessary indexes.

### 7. Deploy the Worker

```bash
wrangler deploy
```

The command will output your worker URL, something like:
```
https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev
```

**Save this URL** - you'll need it for the VoiceMode configuration.

## Configuration in VoiceMode

Once deployed, configure VoiceMode to use your telemetry endpoint:

```bash
# Set the telemetry endpoint URL
voicemode config set VOICEMODE_TELEMETRY_ENDPOINT https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry

# Enable telemetry (user must opt-in)
voicemode config set VOICEMODE_TELEMETRY true
```

Or add to `~/.voicemode/voicemode.env`:

```bash
VOICEMODE_TELEMETRY=true
VOICEMODE_TELEMETRY_ENDPOINT=https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry
```

## Testing the Endpoint

### Manual Test with curl

```bash
curl -X POST https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "test123",
    "telemetry_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2024-12-14T10:30:00Z",
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
  }'
```

Expected response:
```json
{
  "status": "ok",
  "event_id": "test123"
}
```

### Test Idempotency

Send the same request again - should return:
```json
{
  "status": "ok",
  "message": "Event already recorded"
}
```

### Test Rate Limiting

Send 11 requests with the same `telemetry_id` within an hour:
```json
{
  "error": "Rate limit exceeded for telemetry ID",
  "retry_after": 3600
}
```

### Test Invalid Payload

```bash
curl -X POST https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry \
  -H "Content-Type: application/json" \
  -d '{"invalid": "data"}'
```

Expected response:
```json
{
  "error": "Invalid or missing event_id"
}
```

## Monitoring and Debugging

### View Worker Logs

```bash
wrangler tail
```

This streams real-time logs from your worker. Keep this running while testing.

### Query D1 Database

```bash
# Count total events
wrangler d1 execute voicemode-telemetry --command "SELECT COUNT(*) as total FROM events"

# View recent events
wrangler d1 execute voicemode-telemetry --command "SELECT event_id, telemetry_id, timestamp FROM events ORDER BY created_at DESC LIMIT 10"

# Daily active users
wrangler d1 execute voicemode-telemetry --command "SELECT COUNT(DISTINCT telemetry_id) as dau FROM events WHERE DATE(timestamp) = DATE('now')"
```

### Check KV Namespace (rate limits)

```bash
# List all keys
wrangler kv:key list --namespace-id=YOUR_KV_NAMESPACE_ID

# Get a specific rate limit counter
wrangler kv:key get "rate:id:550e8400-e29b-41d4-a716-446655440000" --namespace-id=YOUR_KV_NAMESPACE_ID
```

### View Worker Metrics

Go to: https://dash.cloudflare.com/ → Workers & Pages → voicemode-telemetry → Metrics

Metrics include:
- Requests per second
- Error rate
- CPU time usage
- Success/error status codes

## Querying Telemetry Data

### Example SQL Queries

#### Daily Active Users (DAU)

```sql
SELECT COUNT(DISTINCT telemetry_id) as dau
FROM events
WHERE DATE(timestamp) = DATE('now');
```

#### Weekly Active Users (WAU)

```sql
SELECT COUNT(DISTINCT telemetry_id) as wau
FROM events
WHERE timestamp >= datetime('now', '-7 days');
```

#### Sessions by Operating System

```sql
SELECT
  json_extract(environment, '$.os') as os,
  SUM(json_extract(usage, '$.total_sessions')) as total_sessions
FROM events
GROUP BY os
ORDER BY total_sessions DESC;
```

#### TTS Provider Usage

```sql
SELECT
  DATE(timestamp) as date,
  json_extract(usage, '$.provider_usage.tts') as tts_providers
FROM events
WHERE timestamp >= datetime('now', '-30 days')
ORDER BY date DESC;
```

#### 7-Day Retention

```sql
WITH first_seen AS (
  SELECT telemetry_id, MIN(DATE(timestamp)) as first_date
  FROM events
  GROUP BY telemetry_id
)
SELECT
  COUNT(DISTINCT e.telemetry_id) as retained_users,
  COUNT(DISTINCT f.telemetry_id) as cohort_size,
  ROUND(100.0 * COUNT(DISTINCT e.telemetry_id) / COUNT(DISTINCT f.telemetry_id), 2) as retention_pct
FROM first_seen f
LEFT JOIN events e ON e.telemetry_id = f.telemetry_id
  AND DATE(e.timestamp) = DATE(f.first_date, '+7 days')
WHERE f.first_date = DATE('now', '-7 days');
```

#### Average Sessions Per User

```sql
SELECT
  AVG(total) as avg_sessions_per_user
FROM (
  SELECT
    telemetry_id,
    SUM(json_extract(usage, '$.total_sessions')) as total
  FROM events
  GROUP BY telemetry_id
);
```

### Run Queries via Wrangler

```bash
wrangler d1 execute voicemode-telemetry --command "YOUR_SQL_QUERY_HERE"
```

### Export Data

```bash
# Export to JSON
wrangler d1 export voicemode-telemetry --output=telemetry-export.sql

# Query and save to file
wrangler d1 execute voicemode-telemetry \
  --command "SELECT * FROM events WHERE timestamp >= datetime('now', '-7 days')" \
  --json > last-7-days.json
```

## Cost Estimation

### Free Tier (Sufficient for MVP)

**Workers:**
- 100,000 requests/day
- 10ms CPU time per request
- 128MB memory

**KV:**
- 100,000 reads/day
- 1,000 writes/day
- 1GB storage

**D1:**
- 5 million row reads/day
- 100,000 row writes/day
- 5GB storage

### Expected Usage (1,000 users, 10 events/day)

- Requests: ~10,000/day (well within 100k limit)
- KV writes: ~20,000/day (rate limit counters) - **exceeds free tier**
- D1 writes: ~10,000/day (within limit)
- Storage: ~100MB for 90 days of events (within limit)

**Recommendation:** Start with free tier. If KV writes exceed limits, upgrade to Workers Paid ($5/month base) which includes unlimited requests and higher KV limits.

### Paid Tier (if needed)

**Workers Paid ($5/month + usage):**
- Unlimited requests
- 50ms CPU time per request
- 10 million KV reads/day (included)
- 1 million KV writes/day (included)
- Additional requests: $0.50 per million

At 1,000 users: Approximately **$5-8/month**

## Maintenance

### Daily Automatic Cleanup

The worker includes a scheduled task (cron) that runs daily at 2am UTC to delete events older than 90 days. This prevents unbounded database growth.

View cron trigger status:
```bash
wrangler deployments list
```

### Manual Cleanup

```bash
# Delete events older than 90 days
wrangler d1 execute voicemode-telemetry --command \
  "DELETE FROM events WHERE created_at < datetime('now', '-90 days')"

# Vacuum database to reclaim space
wrangler d1 execute voicemode-telemetry --command "VACUUM"
```

### Update Worker Code

After making changes to `worker.js`:

```bash
wrangler deploy
```

No downtime - Cloudflare deploys atomically.

## Troubleshooting

### "Error: No account_id found"

Edit `wrangler.toml` and add your Account ID from the Cloudflare dashboard.

### "Error: KV namespace not found"

Run `wrangler kv:namespace create "RATE_LIMITS"` and update the `id` in `wrangler.toml`.

### "Error: D1 database not found"

Run `wrangler d1 create voicemode-telemetry` and update the `database_id` in `wrangler.toml`.

### "Error: table events does not exist"

Initialize the database schema:
```bash
wrangler d1 execute voicemode-telemetry --file=schema.sql
```

### Worker returns 500 errors

Check logs:
```bash
wrangler tail
```

Common issues:
- Database not initialized (run schema.sql)
- KV namespace not bound (check wrangler.toml)
- JSON parsing error (check request payload)

### Rate limits triggering unexpectedly

Check KV values:
```bash
wrangler kv:key list --namespace-id=YOUR_KV_NAMESPACE_ID
```

Reset a rate limit manually:
```bash
wrangler kv:key delete "rate:id:TELEMETRY_ID" --namespace-id=YOUR_KV_NAMESPACE_ID
```

## Security Considerations

1. **IP Anonymization**: IP addresses are SHA-256 hashed before storage
2. **No PII**: Only anonymous UUIDs are collected, no user names or emails
3. **Rate Limiting**: Prevents abuse and resource exhaustion
4. **CORS**: Configured to accept requests from any origin (required for CLI tool)
5. **Payload Validation**: Strict schema validation prevents malformed data
6. **Data Retention**: Automatic cleanup after 90 days

## Custom Domain (Optional)

To use a custom domain instead of `workers.dev`:

1. Add a domain to Cloudflare
2. Add a route in `wrangler.toml`:

```toml
routes = [
  { pattern = "telemetry.yourdomain.com", custom_domain = true }
]
```

3. Deploy:

```bash
wrangler deploy
```

## Next Steps

1. **Deploy the worker** following the setup instructions
2. **Test with curl** to verify it's working
3. **Configure VoiceMode** with the endpoint URL
4. **Monitor metrics** in Cloudflare dashboard
5. **Query data** to analyze usage patterns

## Support

- Cloudflare Workers Docs: https://developers.cloudflare.com/workers/
- D1 Database Docs: https://developers.cloudflare.com/d1/
- Wrangler CLI Docs: https://developers.cloudflare.com/workers/wrangler/
- VoiceMode Issues: https://github.com/mbailey/voicemode/issues

## License

This code is part of the VoiceMode project and shares the same license.
