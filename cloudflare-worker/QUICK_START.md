# Quick Start: Deploy VoiceMode Telemetry Endpoint

This is a condensed guide to get your telemetry endpoint deployed quickly. For detailed information, see [DEPLOYMENT.md](DEPLOYMENT.md) and [README.md](README.md).

## TL;DR - 5 Minute Setup

```bash
# 1. Install Wrangler
npm install -g wrangler

# 2. Login to Cloudflare
wrangler login

# 3. Get your Account ID from https://dash.cloudflare.com/ and edit wrangler.toml

# 4. Create resources
wrangler kv:namespace create "RATE_LIMITS"
# Copy the ID and update wrangler.toml [[kv_namespaces]] section

wrangler d1 create voicemode-telemetry
# Copy the database_id and update wrangler.toml [[d1_databases]] section

# 5. Initialize database
wrangler d1 execute voicemode-telemetry --file=schema.sql

# 6. Deploy
wrangler deploy

# 7. Test
./test-endpoint.sh https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry

# 8. Configure VoiceMode
voicemode config set VOICEMODE_TELEMETRY_ENDPOINT https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry
```

## What You Get

- **Endpoint:** `https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry`
- **Rate Limiting:** 10 events/hour per user, 100 events/hour per IP
- **Privacy:** IP addresses hashed, no PII collected
- **Cost:** Free tier covers < 1000 users (~$0/month)
- **Idempotency:** Duplicate events handled gracefully
- **Automatic Cleanup:** Events older than 90 days removed daily

## Files Created

```
cloudflare-worker/
├── worker.js              # Main Worker code (370 lines)
├── wrangler.toml          # Cloudflare configuration
├── schema.sql             # D1 database schema
├── README.md              # Comprehensive documentation
├── DEPLOYMENT.md          # Step-by-step deployment guide
├── test-endpoint.sh       # Automated test suite
├── package.json           # npm scripts
├── .gitignore             # Git ignore rules
├── .env.example           # Environment template
└── QUICK_START.md         # This file
```

## Required Configuration

Edit `wrangler.toml` with your values:

```toml
account_id = "YOUR_ACCOUNT_ID_HERE"          # From Cloudflare dashboard

[[kv_namespaces]]
binding = "KV"
id = "YOUR_KV_NAMESPACE_ID_HERE"             # From: wrangler kv:namespace create

[[d1_databases]]
binding = "DB"
database_name = "voicemode-telemetry"
database_id = "YOUR_D1_DATABASE_ID_HERE"     # From: wrangler d1 create
```

## Verify Deployment

### 1. Test Endpoint

```bash
curl -X POST https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "test123",
    "telemetry_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2024-12-14T10:00:00Z",
    "environment": {"os": "Linux", "version": "1.0.0"},
    "usage": {"total_sessions": 1}
  }'
```

Expected: `{"status":"ok","event_id":"test123"}`

### 2. Check Database

```bash
wrangler d1 execute voicemode-telemetry --command \
  "SELECT COUNT(*) FROM events"
```

Expected: `1` (from test above)

### 3. Run Full Test Suite

```bash
./test-endpoint.sh https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry
```

All tests should show `✓ PASSED` in green.

## Usage in VoiceMode

After deployment, configure VoiceMode:

```bash
# Option 1: Via CLI
voicemode config set VOICEMODE_TELEMETRY_ENDPOINT https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry

# Option 2: Edit ~/.voicemode/voicemode.env
echo "VOICEMODE_TELEMETRY_ENDPOINT=https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry" >> ~/.voicemode/voicemode.env
```

Telemetry will start flowing automatically (if user has opted in).

## Monitoring

### View Live Logs

```bash
wrangler tail
```

### Query Telemetry Data

```bash
# Daily Active Users
wrangler d1 execute voicemode-telemetry --command \
  "SELECT COUNT(DISTINCT telemetry_id) as dau FROM events WHERE DATE(timestamp) = DATE('now')"

# Total events
wrangler d1 execute voicemode-telemetry --command \
  "SELECT COUNT(*) as total FROM events"

# Recent events
wrangler d1 execute voicemode-telemetry --command \
  "SELECT * FROM events ORDER BY created_at DESC LIMIT 5"
```

### Cloudflare Dashboard

View metrics at: https://dash.cloudflare.com/ → Workers & Pages → voicemode-telemetry

## Cost Estimate

| Users | Events/Month | Cost |
|-------|--------------|------|
| < 100 | ~30,000 | $0 (free tier) |
| 100-1000 | ~300,000 | $0-5 |
| 1000-10000 | ~3,000,000 | $5-15 |

Free tier limits:
- Workers: 100,000 requests/day
- D1: 100,000 writes/day, 5 million reads/day
- KV: 1,000 writes/day (may hit limit - upgrade to $5/month plan)

## Troubleshooting

### Worker returns 500

```bash
# Check logs
wrangler tail

# Verify schema
wrangler d1 execute voicemode-telemetry --command "PRAGMA table_info(events)"
```

### Rate limit not working

```bash
# Check KV keys
wrangler kv:key list --namespace-id=YOUR_KV_NAMESPACE_ID
```

### Need to reset everything

```bash
# Delete database (WARNING: destroys all data)
wrangler d1 delete voicemode-telemetry

# Delete KV namespace
wrangler kv:namespace delete --namespace-id=YOUR_KV_NAMESPACE_ID

# Then recreate from step 4 above
```

## Next Steps

1. ✅ Deploy worker (you just did this!)
2. ✅ Test endpoint
3. ✅ Configure VoiceMode
4. 📊 Set up analytics queries (see README.md)
5. 📈 Monitor usage in Cloudflare dashboard
6. 🔔 Set up alerts (optional)
7. 📝 Document your worker URL for team

## Support

- **Detailed Docs:** [README.md](README.md)
- **Deployment Guide:** [DEPLOYMENT.md](DEPLOYMENT.md)
- **Cloudflare Docs:** https://developers.cloudflare.com/workers/
- **VoiceMode Issues:** https://github.com/mbailey/voicemode/issues

---

**Deployment complete!** Your telemetry endpoint is now ready to collect privacy-preserving usage data from VoiceMode clients.
