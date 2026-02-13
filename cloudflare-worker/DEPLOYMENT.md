# Deployment Checklist for VoiceMode Telemetry Worker

This checklist guides you through deploying the VoiceMode telemetry endpoint to Cloudflare Workers.

## Prerequisites

- [ ] Cloudflare account (free tier is sufficient)
- [ ] Node.js 18+ installed
- [ ] Git (for version control of worker code)

## One-Time Setup

### 1. Install Wrangler CLI

```bash
npm install -g wrangler
```

**Verify installation:**
```bash
wrangler --version
```

### 2. Authenticate with Cloudflare

```bash
wrangler login
```

This opens a browser window to authorize Wrangler with your Cloudflare account.

### 3. Get Your Account ID

1. Go to https://dash.cloudflare.com/
2. Select your account from the dropdown
3. Copy the **Account ID** from the right sidebar
4. Save this ID - you'll need it in the next step

### 4. Configure wrangler.toml

Edit `wrangler.toml` and replace the placeholder:

```toml
account_id = "YOUR_ACCOUNT_ID_HERE"  # Replace with your actual Account ID
```

### 5. Create KV Namespace

```bash
wrangler kv:namespace create "RATE_LIMITS"
```

**Expected output:**
```
Created namespace with title "voicemode-telemetry-RATE_LIMITS"
Add the following to your wrangler.toml:
{ binding = "KV", id = "abc123..." }
```

Copy the `id` value and update `wrangler.toml`:

```toml
[[kv_namespaces]]
binding = "KV"
id = "abc123..."  # Replace with the ID from the command output
```

### 6. Create D1 Database

```bash
wrangler d1 create voicemode-telemetry
```

**Expected output:**
```
Created database voicemode-telemetry
database_id = "xyz789..."
```

Copy the `database_id` value and update `wrangler.toml`:

```toml
[[d1_databases]]
binding = "DB"
database_name = "voicemode-telemetry"
database_id = "xyz789..."  # Replace with the ID from the command output
```

### 7. Initialize Database Schema

```bash
wrangler d1 execute voicemode-telemetry --file=schema.sql
```

**Expected output:**
```
🌀 Executing on remote database voicemode-telemetry (xyz789...):
🌀 To execute on your local development database, pass the --local flag.
🚣 Executed 5 commands in 0.234ms
```

Verify the table was created:

```bash
wrangler d1 execute voicemode-telemetry --command "SELECT name FROM sqlite_master WHERE type='table'"
```

Should show: `events`

### 8. Deploy the Worker

```bash
wrangler deploy
```

**Expected output:**
```
Total Upload: XX.XX KiB / gzip: XX.XX KiB
Uploaded voicemode-telemetry (X.XX sec)
Published voicemode-telemetry (X.XX sec)
  https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev
```

**Save the worker URL!** You'll need it for VoiceMode configuration.

## Testing Deployment

### 1. Test with curl

```bash
export WORKER_URL="https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry"

curl -X POST $WORKER_URL \
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
      "total_sessions": 1,
      "duration_distribution": {},
      "transport_usage": {},
      "provider_usage": {}
    }
  }'
```

**Expected response:**
```json
{"status":"ok","event_id":"test_..."}
```

### 2. Run Test Suite

```bash
./test-endpoint.sh $WORKER_URL
```

All tests should pass (PASSED in green).

### 3. Verify Database

```bash
wrangler d1 execute voicemode-telemetry --command \
  "SELECT COUNT(*) as total_events FROM events"
```

Should show the test events you just created.

### 4. Monitor Worker Logs

In a separate terminal, run:

```bash
wrangler tail
```

Then send another test request and watch the logs appear in real-time.

## Configure VoiceMode

Once deployment is successful, configure VoiceMode to use your telemetry endpoint:

### Option 1: Via CLI

```bash
voicemode config set VOICEMODE_TELEMETRY_ENDPOINT https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry
```

### Option 2: Manual Edit

Edit `~/.voicemode/voicemode.env`:

```bash
# Telemetry configuration
VOICEMODE_TELEMETRY=true
VOICEMODE_TELEMETRY_ENDPOINT=https://voicemode-telemetry.YOUR_SUBDOMAIN.workers.dev/telemetry
```

## Verify End-to-End

### 1. Use VoiceMode

Use VoiceMode normally (have some voice conversations).

### 2. Check for Telemetry Events

```bash
# In the cloudflare-worker directory
wrangler d1 execute voicemode-telemetry --command \
  "SELECT event_id, telemetry_id, timestamp FROM events ORDER BY created_at DESC LIMIT 5"
```

You should see events from your VoiceMode usage.

### 3. Query DAU

```bash
wrangler d1 execute voicemode-telemetry --command \
  "SELECT COUNT(DISTINCT telemetry_id) as dau FROM events WHERE DATE(timestamp) = DATE('now')"
```

## Post-Deployment Tasks

- [ ] Save your worker URL in a secure location (password manager, docs)
- [ ] Document the deployment in your team wiki/docs
- [ ] Set up monitoring alerts (optional - Cloudflare dashboard)
- [ ] Schedule regular checks of telemetry data (weekly/monthly)
- [ ] Add worker URL to VoiceMode production configuration
- [ ] Consider setting up a custom domain (see README.md)

## Updating the Worker

When you make changes to `worker.js`:

```bash
# Test locally first (optional)
wrangler dev

# Deploy changes
wrangler deploy
```

Changes take effect immediately (no downtime).

## Rollback Procedure

If something goes wrong after deployment:

```bash
# View deployment history
wrangler deployments list

# Rollback to previous version
wrangler rollback
```

## Monitoring Checklist

### Daily (Automated)
- [ ] Cron job runs successfully (check logs at 2am UTC)
- [ ] No error spikes in Cloudflare dashboard

### Weekly
- [ ] Review error logs: `wrangler tail --format=json | grep error`
- [ ] Check database size: `wrangler d1 execute voicemode-telemetry --command "SELECT COUNT(*) FROM events"`
- [ ] Verify rate limits are working (check for 429 responses)

### Monthly
- [ ] Export telemetry data for analysis
- [ ] Review costs in Cloudflare billing dashboard
- [ ] Clean up old queued events in VoiceMode clients
- [ ] Update worker dependencies: `npm update wrangler`

## Troubleshooting

### Worker returns 500 errors after deployment

1. Check logs: `wrangler tail`
2. Verify database schema: `wrangler d1 execute voicemode-telemetry --command "PRAGMA table_info(events)"`
3. Check KV binding: `wrangler kv:namespace list`

### Rate limits not working

1. Verify KV namespace is bound: Check `wrangler.toml`
2. Test manually: Send 11 requests rapidly to same telemetry_id
3. Check KV keys: `wrangler kv:key list --namespace-id=YOUR_KV_ID`

### Database queries slow

1. Check indexes: `wrangler d1 execute voicemode-telemetry --command "SELECT * FROM sqlite_master WHERE type='index'"`
2. Vacuum database: `wrangler d1 execute voicemode-telemetry --command "VACUUM"`
3. Consider archiving old data

## Security Notes

- **Never commit `.env` files** (already in `.gitignore`)
- **Rotate secrets annually** (KV namespace IDs, database IDs)
- **Monitor for abuse** (check for unusual traffic patterns)
- **Keep wrangler.toml private** if it contains sensitive IDs

## Cost Management

### Monitor Costs

1. Go to: https://dash.cloudflare.com/ → Account Home → Billing
2. Review Workers usage under "Workers Paid" or "Workers Free"
3. Set up billing alerts (optional)

### Stay Within Free Tier

- **Workers:** 100,000 requests/day
- **KV:** 1,000 writes/day (may need paid tier)
- **D1:** 100,000 writes/day

If approaching limits, consider:
- Reducing telemetry frequency in VoiceMode
- Upgrading to Workers Paid ($5/month)
- Implementing client-side sampling (send 10% of events)

## Success Criteria

✅ Deployment is successful when:

1. Worker URL returns 200 OK for valid requests
2. Test suite passes all 6 tests
3. Events appear in D1 database
4. Rate limiting triggers on 11th request
5. VoiceMode clients can send telemetry
6. No errors in `wrangler tail` logs

## Support

- **Cloudflare Discord:** https://discord.gg/cloudflaredev
- **Workers Documentation:** https://developers.cloudflare.com/workers/
- **D1 Documentation:** https://developers.cloudflare.com/d1/
- **VoiceMode Issues:** https://github.com/mbailey/voicemode/issues

## Next Steps After Deployment

1. **Analytics:** Set up regular queries to understand usage patterns
2. **Dashboards:** Build Grafana/Metabase dashboards for visualization
3. **Alerts:** Configure alerts for error rate spikes
4. **Optimization:** Monitor performance and optimize queries
5. **Documentation:** Update VoiceMode docs with telemetry information

---

**Deployment Date:** _______________
**Deployed By:** _______________
**Worker URL:** _______________
**Account ID:** _______________
**Database ID:** _______________
**KV Namespace ID:** _______________
