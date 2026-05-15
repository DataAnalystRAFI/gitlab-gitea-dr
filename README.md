# GitLab → Gitea DR Solution

Disaster recovery for GitLab.com repositories using pull mirroring to a self-hosted Gitea instance, with automated health checks and webhook notifications.

## Architecture

```
GitLab.com ──pull mirror──▶ Gitea (self-hosted) ──health check──▶ Webhook URL
                                                                    (Slack, Teams,
                                                                     custom endpoint)
```

- **GitLab.com** is the primary (SaaS, read-only via API)
- **Gitea** pulls mirrors from GitLab on a configurable interval (default 1h)
- **DR Agent** runs health checks every 15 minutes, sends alerts when repos lag or services are down
- **Webhook** receives health summaries (daily) and alerts (on degradation)

## Quick Start

### Prerequisites

- Docker & Docker Compose
- GitLab Personal Access Token (`read_api` scope)
- Gitea admin account (created on first run)
- Webhook endpoint URL

### Setup

```bash
# 1. Clone this project
cd gitlab-gitea-dr

# 2. Set required environment variables
export GITLAB_TOKEN="glpat-..."
export GITEA_TOKEN="<create-via-gitea-ui-after-deploy>"
export WEBHOOK_URL="https://hooks.example.com/dr-summary"
export GITEA_DB_PASSWORD="change-me"

# 3. Start Gitea + Postgres
make up

# 4. Create Gitea admin token:
#    Gitea UI → Settings → Applications → Generate Token → export GITEA_TOKEN

# 5. Create mirrors for all GitLab projects
make setup-mirrors

# 6. Verify
make check
```

### Configuration

Edit `config/dr-config.yml`:

| Setting | Description | Default |
|---------|-------------|---------|
| `gitlab.token` | GitLab PAT | `${GITLAB_TOKEN}` |
| `gitlab.per_page` | API page size | 100 |
| `gitea.url` | Gitea API URL | `http://gitea:3000` |
| `mirror.sync_interval_hours` | Mirror sync frequency | 1 |
| `mirror.stale_threshold_hours` | Alert if not synced for N hours | 24 |
| `webhook.url` | Notification endpoint | `${WEBHOOK_URL}` |
| `alerts.lag_commit_threshold` | Min lag commits to alert | 3 |

### Make Targets

| Command | Description |
|---------|-------------|
| `make build` | Build Docker images |
| `make up` | Start all services |
| `make down` | Stop all services |
| `make logs` | Follow container logs |
| `make check` | Run a single health check |
| `make summary` | Force a full summary webhook |
| `make setup-mirrors` | Bootstrap all GitLab → Gitea mirrors |
| `make restore REPO=name DEST=./path` | Clone repo from Gitea for DR |

## Webhook Payload

```json
{
  "event": "health_summary",
  "timestamp": "2026-05-15T10:00:00Z",
  "status": "healthy|degraded|critical",
  "summary": {
    "total_repos": 25,
    "synced": 24,
    "lagging": 1,
    "failed": 0
  },
  "gitea": { "status": "up", "version": "1.22", "disk_usage_pct": 45 },
  "gitlab": { "accessible": true, "latency_ms": 130 },
  "repos": [
    {
      "name": "myorg/my-repo",
      "mirror_status": "synced",
      "gitlab_latest_commit": "abc123",
      "gitea_latest_commit": "abc123",
      "lag_commits": 0,
      "last_synced_ago_secs": 300
    }
  ],
  "alerts": ["repo myorg/stale-repo is lagging by 5+ commits"]
}
```

## DR Restore Procedure

When GitLab.com is unavailable:

```bash
# Clone any mirrored repo from Gitea
make restore REPO=my-project DEST=./restored-repo

# Or use the script directly
python scripts/restore-from-gitea.py --repo my-project --dest ./restored-repo
```

## Development

```bash
# Unit tests
make test

# Lint
pip install ruff
ruff check src/ tests/

# Type check
pip install mypy
mypy src/
```
