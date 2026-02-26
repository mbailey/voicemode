# VoiceMode Telemetry Architecture

## Request Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. VoiceMode Client (Python)                                           │
│    - Collects usage data from logs                                     │
│    - Generates event_id (SHA-256 hash)                                 │
│    - Sends POST /telemetry                                             │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         │ HTTP POST
                         │ Content-Type: application/json
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. Cloudflare Edge Network                                             │
│    - DDoS protection                                                    │
│    - TLS termination                                                    │
│    - Routes to nearest worker instance                                 │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. Worker: Validate Payload                                            │
│    ┌─────────────────────────────────────────────────────────────┐    │
│    │ ✓ Check event_id exists and is string                       │    │
│    │ ✓ Check telemetry_id is valid UUID                          │    │
│    │ ✓ Check timestamp is ISO 8601 and within 90 days            │    │
│    │ ✓ Check environment object exists                           │    │
│    │ ✓ Check usage object exists                                 │    │
│    └─────────────────────────────────────────────────────────────┘    │
│                         │                                               │
│                         ├─── Invalid? ──────┐                          │
│                         │                    ▼                          │
│                         │          ┌──────────────────┐                │
│                         │          │ Return 400       │                │
│                         │          │ {error: "..."}   │                │
│                         │          └──────────────────┘                │
│                         │                                               │
│                         ▼ Valid                                         │
└─────────────────────────┬───────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. Worker: Check Idempotency (D1 Database)                             │
│    ┌─────────────────────────────────────────────────────────────┐    │
│    │ SELECT event_id FROM events WHERE event_id = ?              │    │
│    └─────────────────────────────────────────────────────────────┘    │
│                         │                                               │
│                         ├─── Exists? ───────┐                          │
│                         │                    ▼                          │
│                         │          ┌──────────────────┐                │
│                         │          │ Return 200       │                │
│                         │          │ {status: "ok",   │                │
│                         │          │  message: "..." }│                │
│                         │          └──────────────────┘                │
│                         │                                               │
│                         ▼ New Event                                     │
└─────────────────────────┬───────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. Worker: Check Rate Limits (KV Store)                                │
│    ┌─────────────────────────────────────────────────────────────┐    │
│    │ A. Check telemetry_id rate limit                            │    │
│    │    Key: rate:id:{telemetry_id}                              │    │
│    │    Limit: 10 events/hour                                    │    │
│    │    TTL: 3600 seconds                                        │    │
│    └─────────────────────────────────────────────────────────────┘    │
│                         │                                               │
│                         ├─── Exceeded? ─────┐                          │
│                         │                    ▼                          │
│                         │          ┌──────────────────┐                │
│                         │          │ Return 429       │                │
│                         │          │ {error: "...",   │                │
│                         │          │  retry_after:    │                │
│                         │          │  3600}           │                │
│                         │          └──────────────────┘                │
│                         │                                               │
│                         ▼ OK                                            │
│    ┌─────────────────────────────────────────────────────────────┐    │
│    │ B. Check IP rate limit                                      │    │
│    │    Key: rate:ip:{hashed_ip}                                 │    │
│    │    Limit: 100 events/hour                                   │    │
│    │    TTL: 3600 seconds                                        │    │
│    └─────────────────────────────────────────────────────────────┘    │
│                         │                                               │
│                         ├─── Exceeded? ─────┐                          │
│                         │                    ▼                          │
│                         │          ┌──────────────────┐                │
│                         │          │ Return 429       │                │
│                         │          │ (same as above)  │                │
│                         │          └──────────────────┘                │
│                         │                                               │
│                         ▼ OK                                            │
└─────────────────────────┬───────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 6. Worker: Hash IP Address                                             │
│    ┌─────────────────────────────────────────────────────────────┐    │
│    │ client_ip = request.headers.get('CF-Connecting-IP')         │    │
│    │ hashed_ip = SHA256(client_ip).substring(0, 16)              │    │
│    └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 7. Worker: Store Event (D1 Database)                                   │
│    ┌─────────────────────────────────────────────────────────────┐    │
│    │ INSERT INTO events (                                        │    │
│    │   event_id,                                                 │    │
│    │   telemetry_id,                                             │    │
│    │   timestamp,                                                │    │
│    │   environment,     -- JSON string                           │    │
│    │   usage,           -- JSON string                           │    │
│    │   client_ip_hash,  -- SHA-256 hash                          │    │
│    │   created_at       -- Server timestamp                      │    │
│    │ ) VALUES (?, ?, ?, ?, ?, ?, ?)                              │    │
│    └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 8. Worker: Increment Rate Limit Counters (KV Store)                    │
│    ┌─────────────────────────────────────────────────────────────┐    │
│    │ A. Increment telemetry_id counter                           │    │
│    │    rate:id:{telemetry_id} += 1 (TTL: 3600s)                 │    │
│    │                                                              │    │
│    │ B. Increment IP counter                                     │    │
│    │    rate:ip:{hashed_ip} += 1 (TTL: 3600s)                    │    │
│    └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 9. Worker: Return Success                                              │
│    ┌─────────────────────────────────────────────────────────────┐    │
│    │ HTTP 200 OK                                                  │    │
│    │ Content-Type: application/json                               │    │
│    │ Access-Control-Allow-Origin: *                               │    │
│    │                                                              │    │
│    │ {                                                            │    │
│    │   "status": "ok",                                            │    │
│    │   "event_id": "abc123..."                                    │    │
│    │ }                                                            │    │
│    └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 10. VoiceMode Client Receives Response                                 │
│     - 200 OK: Success, event recorded                                  │
│     - 429 Too Many Requests: Rate limited, retry after X seconds       │
│     - 400 Bad Request: Invalid payload, don't retry                    │
│     - 500 Internal Server Error: Server issue, retry with backoff      │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Storage

### D1 Database (SQLite)

```sql
events
├── event_id (TEXT PRIMARY KEY)           -- Idempotency key
├── telemetry_id (TEXT NOT NULL)          -- Anonymous user ID (UUID)
├── timestamp (TEXT NOT NULL)             -- Event time (ISO 8601)
├── created_at (TEXT NOT NULL)            -- Server receipt time (ISO 8601)
├── environment (TEXT NOT NULL)           -- JSON blob
│   └── {
│       "os": "Linux",
│       "version": "1.0.0",
│       "installation_method": "uv",
│       "mcp_host": "claude-code",
│       "execution_source": "mcp"
│   }
├── usage (TEXT NOT NULL)                 -- JSON blob
│   └── {
│       "total_sessions": 5,
│       "duration_distribution": {...},
│       "transport_usage": {...},
│       "provider_usage": {...},
│       "success_rate": {...},
│       "error_types": {...}
│   }
└── client_ip_hash (TEXT NOT NULL)        -- SHA-256(IP)[0:16]

Indexes:
- idx_events_telemetry_id (telemetry_id)
- idx_events_timestamp (timestamp)
- idx_events_created_at (created_at)
- idx_events_telemetry_timestamp (telemetry_id, timestamp)
```

### KV Store (Key-Value)

```
Rate Limiting Keys:
├── rate:id:{telemetry_id}
│   ├── Value: Integer (event count)
│   ├── TTL: 3600 seconds (1 hour)
│   └── Limit: 10
│
└── rate:ip:{hashed_ip}
    ├── Value: Integer (event count)
    ├── TTL: 3600 seconds (1 hour)
    └── Limit: 100
```

## Scheduled Tasks

### Daily Cleanup (Cron: 0 2 * * *)

```
┌─────────────────────────────────────────┐
│ Runs at 2:00 AM UTC daily               │
│                                         │
│ DELETE FROM events                      │
│ WHERE created_at < datetime('now',      │
│   '-90 days')                           │
│                                         │
│ Purpose: Prevent unbounded growth       │
│ Retention: 90 days                      │
└─────────────────────────────────────────┘
```

## Privacy Protections

```
┌──────────────────────────────────────────────────────────────┐
│ 1. IP Address Hashing                                       │
│    Input:  192.168.1.100                                    │
│    Hash:   SHA256(IP)                                       │
│    Store:  ab12cd34ef567890 (first 16 chars)               │
│    Result: Cannot reverse to original IP                    │
│                                                              │
│ 2. Anonymous User ID                                        │
│    - UUID generated by client                               │
│    - No link to user identity                               │
│    - Stored in ~/.voicemode/telemetry_id                    │
│                                                              │
│ 3. No PII Collection                                        │
│    - No names, emails, or user accounts                     │
│    - No file paths (anonymized)                             │
│    - No error messages with sensitive data                  │
│                                                              │
│ 4. Data Minimization                                        │
│    - Only collect what's needed for analytics               │
│    - Aggregate counts, not individual actions               │
│    - Binned durations (not precise timestamps)              │
│                                                              │
│ 5. Automatic Deletion                                       │
│    - Events deleted after 90 days                           │
│    - No long-term storage                                   │
└──────────────────────────────────────────────────────────────┘
```

## Rate Limiting Strategy

### Two-Tier Rate Limiting

```
┌────────────────────────────────────────────────────────────────┐
│ Tier 1: Per Telemetry ID (User Device)                        │
│ ├─ Limit: 10 events/hour                                      │
│ ├─ Window: Sliding (TTL-based)                                │
│ ├─ Purpose: Prevent single client abuse                       │
│ └─ Key: rate:id:{telemetry_id}                                │
│                                                                │
│ Tier 2: Per IP Address                                        │
│ ├─ Limit: 100 events/hour                                     │
│ ├─ Window: Sliding (TTL-based)                                │
│ ├─ Purpose: Prevent DoS attacks                               │
│ └─ Key: rate:ip:{hashed_ip}                                   │
│                                                                │
│ Both must pass for request to be accepted                     │
└────────────────────────────────────────────────────────────────┘
```

### Example Scenarios

```
Scenario 1: Normal Usage
├─ User sends 1 event/day
├─ Rate limit: 0/10 (telemetry_id), 0/100 (IP)
└─ Result: ✓ Accepted

Scenario 2: Retry Storm
├─ User sends 15 events rapidly (network retry bug)
├─ Rate limit: 10/10 (telemetry_id), 15/100 (IP)
├─ Events 1-10: ✓ Accepted
├─ Events 11-15: ✗ Rejected (429)
└─ Result: Protects backend from client bugs

Scenario 3: Shared IP (NAT/VPN)
├─ 50 users behind same IP
├─ Each sends 2 events/day
├─ Rate limit: 2/10 per user, 100/100 (IP)
├─ Events 1-100: ✓ Accepted
├─ Events 101+: ✗ Rejected (429)
└─ Result: IP limit protects from shared network abuse

Scenario 4: Attack
├─ Attacker sends 1000 events from different IPs
├─ Same telemetry_id
├─ Rate limit: 10/10 (telemetry_id)
├─ Events 1-10: ✓ Accepted
├─ Events 11-1000: ✗ Rejected (429)
└─ Result: telemetry_id limit stops attack
```

## Error Handling

```
┌────────────────────────────────────────────────────────────────┐
│ HTTP Status Codes                                              │
│                                                                │
│ 200 OK                                                         │
│ ├─ Event successfully stored                                  │
│ ├─ Event already exists (idempotent)                          │
│ └─ Response: {status: "ok", event_id: "..."}                  │
│                                                                │
│ 400 Bad Request                                                │
│ ├─ Invalid JSON payload                                       │
│ ├─ Missing required fields                                    │
│ ├─ Invalid field format (UUID, timestamp)                     │
│ └─ Response: {error: "descriptive error message"}             │
│                                                                │
│ 429 Too Many Requests                                          │
│ ├─ Rate limit exceeded (telemetry_id or IP)                   │
│ ├─ Retry-After header set to 3600 seconds                     │
│ └─ Response: {error: "...", retry_after: 3600}                │
│                                                                │
│ 500 Internal Server Error                                     │
│ ├─ Database error                                             │
│ ├─ KV namespace error                                         │
│ ├─ Unexpected exception                                       │
│ └─ Response: {error: "Internal server error"}                 │
└────────────────────────────────────────────────────────────────┘
```

## Performance Characteristics

```
┌────────────────────────────────────────────────────────────────┐
│ Latency (p50/p95/p99)                                          │
│ ├─ Validation: < 1ms                                           │
│ ├─ D1 lookup (idempotency): 5-10ms / 15-25ms / 30-50ms        │
│ ├─ KV read (rate limit): 1-3ms / 5-10ms / 15-25ms             │
│ ├─ D1 write: 10-20ms / 30-50ms / 50-100ms                     │
│ ├─ KV write: 5-10ms / 15-25ms / 30-50ms                       │
│ └─ Total: ~25ms / ~75ms / ~150ms                              │
│                                                                │
│ Throughput                                                     │
│ ├─ Workers: 1000+ requests/second                             │
│ ├─ D1: 100+ writes/second                                     │
│ ├─ KV: 1000+ reads/second, 100+ writes/second                 │
│ └─ Bottleneck: D1 writes (sufficient for MVP)                 │
│                                                                │
│ Scalability                                                    │
│ ├─ Workers: Auto-scales to millions of requests               │
│ ├─ D1: Scales to billions of rows                             │
│ ├─ KV: Scales to billions of keys                             │
│ └─ Cost scales linearly with usage                            │
└────────────────────────────────────────────────────────────────┘
```

## Monitoring & Observability

```
┌────────────────────────────────────────────────────────────────┐
│ Cloudflare Dashboard                                           │
│ ├─ Requests/second (time-series graph)                        │
│ ├─ Error rate (4xx, 5xx)                                      │
│ ├─ CPU time (ms per request)                                  │
│ ├─ Success rate (%)                                           │
│ └─ Data egress (bandwidth)                                    │
│                                                                │
│ Wrangler Tail (Real-time Logs)                                │
│ ├─ console.log() statements                                   │
│ ├─ Errors and exceptions                                      │
│ ├─ Request/response details                                   │
│ └─ Performance metrics                                        │
│                                                                │
│ D1 Analytics                                                   │
│ ├─ Query execution time                                       │
│ ├─ Read/write operations                                      │
│ ├─ Database size                                              │
│ └─ Row count                                                  │
│                                                                │
│ KV Analytics                                                   │
│ ├─ Read/write operations                                      │
│ ├─ Key count                                                  │
│ ├─ Storage usage                                              │
│ └─ TTL expirations                                            │
└────────────────────────────────────────────────────────────────┘
```

## Security Model

```
┌────────────────────────────────────────────────────────────────┐
│ Threat Mitigation                                              │
│                                                                │
│ 1. DoS Attack                                                  │
│    ├─ Threat: Overwhelm endpoint with requests                │
│    ├─ Mitigation: IP-based rate limiting (100/hour)           │
│    └─ Additional: Cloudflare DDoS protection                  │
│                                                                │
│ 2. Client Bug (Retry Storm)                                   │
│    ├─ Threat: Client bug causes infinite retry loop           │
│    ├─ Mitigation: telemetry_id rate limiting (10/hour)        │
│    └─ Additional: Idempotency prevents duplicate storage      │
│                                                                │
│ 3. Data Poisoning                                              │
│    ├─ Threat: Submit malicious data to corrupt analytics      │
│    ├─ Mitigation: Strict payload validation                   │
│    └─ Additional: JSON schema enforcement                     │
│                                                                │
│ 4. Privacy Breach                                              │
│    ├─ Threat: Leak user identity or IP address                │
│    ├─ Mitigation: IP hashing, anonymous UUIDs                 │
│    └─ Additional: No PII collection                           │
│                                                                │
│ 5. SQL Injection                                               │
│    ├─ Threat: Inject SQL via payload                          │
│    ├─ Mitigation: Prepared statements with binding            │
│    └─ Additional: D1 SQLite parameterized queries             │
│                                                                │
│ 6. Storage Exhaustion                                          │
│    ├─ Threat: Fill database with events                       │
│    ├─ Mitigation: Rate limiting + automatic cleanup           │
│    └─ Additional: 90-day retention policy                     │
└────────────────────────────────────────────────────────────────┘
```

## Cost Model

```
┌────────────────────────────────────────────────────────────────┐
│ Free Tier Limits (per day)                                    │
│ ├─ Workers: 100,000 requests                                  │
│ ├─ D1 reads: 5,000,000 rows                                   │
│ ├─ D1 writes: 100,000 rows                                    │
│ ├─ KV reads: 100,000 operations                               │
│ ├─ KV writes: 1,000 operations                                │
│ └─ KV storage: 1 GB                                           │
│                                                                │
│ Paid Tier ($5/month + usage)                                  │
│ ├─ Workers: Unlimited requests                                │
│ ├─ D1: Same limits (generous)                                 │
│ ├─ KV reads: 10,000,000/day (included)                        │
│ ├─ KV writes: 1,000,000/day (included)                        │
│ ├─ Additional: $0.50 per million requests                     │
│ └─ KV storage: $0.50/GB/month                                 │
│                                                                │
│ Cost Projection (1000 users, 10 events/day/user)              │
│ ├─ Events: 300,000/month = 10,000/day                         │
│ ├─ Worker requests: 10,000/day (within free tier)             │
│ ├─ D1 writes: 10,000/day (within free tier)                   │
│ ├─ KV writes: 20,000/day (rate limit counters)                │
│ │   └─ Exceeds free tier! Need paid plan                      │
│ ├─ Storage: ~100 MB (within free tier)                        │
│ └─ Total: $5/month (paid tier required for KV writes)         │
└────────────────────────────────────────────────────────────────┘
```
