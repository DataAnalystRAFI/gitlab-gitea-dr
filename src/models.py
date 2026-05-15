from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class AlertLevel(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class MirrorStatus(str, Enum):
    SYNCED = "synced"
    LAGGING = "lagging"
    NEVER_SYNCED = "never_synced"
    FAILED = "failed"
    UNKNOWN = "unknown"


class EventType(str, Enum):
    HEALTH_SUMMARY = "health_summary"
    HEALTH_ALERT = "health_alert"
    MIRROR_SETUP = "mirror_setup"


class GitLabConfig(BaseModel):
    url: str = "https://gitlab.com"
    token: str = ""
    per_page: int = 100
    request_timeout_secs: int = 30


class GiteaConfig(BaseModel):
    url: str = "http://gitea:3000"
    token: str = ""
    request_timeout_secs: int = 30


class WebhookConfig(BaseModel):
    url: str = ""
    retry_count: int = 3
    timeout_secs: int = 10
    retry_delay_secs: int = 5


class MirrorConfig(BaseModel):
    sync_interval_hours: int = 1
    stale_threshold_hours: int = 24
    default_branch_only: bool = True


class SchedulingConfig(BaseModel):
    check_interval_secs: int = 900
    summary_interval_secs: int = 86400
    repo_sync_interval_secs: int = 21600


class AlertsConfig(BaseModel):
    on_lagging_repos: bool = True
    on_gitea_down: bool = True
    on_gitlab_down: bool = True
    lag_commit_threshold: int = 3


class DrConfig(BaseModel):
    gitlab: GitLabConfig = GitLabConfig()
    gitea: GiteaConfig = GiteaConfig()
    webhook: WebhookConfig = WebhookConfig()
    mirror: MirrorConfig = MirrorConfig()
    scheduling: SchedulingConfig = SchedulingConfig()
    alerts: AlertsConfig = AlertsConfig()


class RepoStatus(BaseModel):
    name: str
    gitlab_id: int | None = None
    mirror_status: MirrorStatus = MirrorStatus.UNKNOWN
    gitlab_latest_commit: str | None = None
    gitea_latest_commit: str | None = None
    lag_commits: int = 0
    last_synced_ago_secs: float | None = None
    mirror_url: str | None = None
    error: str | None = None


class GiteaHealth(BaseModel):
    status: Literal["up", "down"] = "up"
    version: str | None = None
    disk_usage_pct: float = 0.0
    uptime_seconds: float | None = None
    error: str | None = None


class GitLabHealth(BaseModel):
    accessible: bool = True
    latency_ms: float = 0.0
    error: str | None = None


class HealthPayload(BaseModel):
    event: EventType = EventType.HEALTH_SUMMARY
    timestamp: str = ""
    status: AlertLevel = AlertLevel.HEALTHY
    summary: dict = Field(default_factory=lambda: {
        "total_repos": 0, "synced": 0, "lagging": 0, "failed": 0
    })
    gitea: GiteaHealth = GiteaHealth()
    gitlab: GitLabHealth = GitLabHealth()
    repos: list[RepoStatus] = []
    alerts: list[str] = []


class GitLabProject(BaseModel):
    id: int
    name: str
    name_with_namespace: str
    path_with_namespace: str
    http_url_to_repo: str
    default_branch: str | None = None
    last_activity_at: str | None = None


class GiteaMirror(BaseModel):
    id: int
    name: str
    full_name: str
    clone_addr: str
    mirror: bool = False
    description: str = ""
