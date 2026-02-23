# OpenAI Status Monitor

Real-time OpenAI service status monitoring. Polls the incident.io API every 5 seconds, detects changes via Redis caching, and logs alerts to stdout.

## How It Works

1. Fetch OpenAI service statuses from incident.io API every 5 seconds
2. Compare response against Redis-cached previous state
3. If status changed, extract product name and status, print formatted alert
4. If no change, skip (efficient, no duplicate alerts)
5. Update cache for next comparison cycle

## Quick Start

### Prerequisites

- Python 3.12+
- Redis running locally (`redis-server`)
- Pipenv (`pip install pipenv`)

### Setup

```bash
# Install dependencies
pipenv install

# Create environment config
cp .env.example .env

# Run poller
pipenv run python poller.py
```

### Environment Variables

Create a `.env` file:

```env
REDIS_URL=redis://localhost:6379
POLL_INTERVAL=5
LOG_LEVEL=INFO
```

## Example Output

```txt
[2026-02-23 20:36:03] INFO     ✓ Connected to Redis
[2026-02-23 20:36:03] INFO     ✓ HTTP session initialized
[2026-02-23 20:36:03] INFO     🚀 Starting poller (interval=5s)
[2026-02-23 20:36:03] INFO     📍 Monitoring: https://status.openai.com/api/v2/components.json
[2026-02-23 20:36:03] DEBUG    → Starting poll cycle
[2026-02-23 20:36:03] DEBUG    ← No changes detected
[2026-02-23 20:36:08] DEBUG    → Starting poll cycle
[2026-02-23 20:36:08] DEBUG    ← No changes detected
```

## Design Rationale

- ✅ Meets "close to real-time" requirement (0-5s latency)
- ✅ Straightforward to implement and debug
- ✅ Works immediately for OpenAI without negotiation
- ✅ Scales horizontally with multiple instances
- ⚠️ Trade-off accepted: Rate limiting requires monitoring and negotiation at 100+ page scale

**Future Evolution Path:**

1. **Phase 1 (MVP):** 5sec polling, single instance, monitor for rate limits
2. **Phase 2 (Scale):** Add multi-instance setup with jitter + backoff
