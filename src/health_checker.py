from __future__ import annotations

import logging
import shutil
from src.models import (
    DrConfig, GiteaHealth, GitLabHealth, RepoStatus,
    MirrorStatus, AlertLevel, HealthPayload, EventType,
)
from src.gitlab_client import GitLabClient
from src.gitea_client import GiteaClient

logger = logging.getLogger(__name__)


class HealthChecker:
    def __init__(self, config: DrConfig, gitlab: GitLabClient, gitea: GiteaClient) -> None:
        self.config = config
        self.gitlab = gitlab
        self.gitea = gitea

    async def check_gitea(self) -> GiteaHealth:
        ok, version = await self.gitea.check_health()
        if not ok:
            return GiteaHealth(status="down", error="Gitea API unreachable")
        disk = self._get_disk_usage("/data" if shutil.which("df") else "/")
        return GiteaHealth(status="up", version=version, disk_usage_pct=disk)

    async def check_gitlab(self) -> GitLabHealth:
        ok, latency = await self.gitlab.check_accessibility()
        if not ok:
            return GitLabHealth(accessible=False, error="GitLab API unreachable", latency_ms=latency)
        return GitLabHealth(accessible=True, latency_ms=latency)

    async def compute_overall_status(
        self,
        gitea: GiteaHealth,
        gitlab: GitLabHealth,
        repos: list[RepoStatus],
    ) -> AlertLevel:
        if gitea.status == "down":
            return AlertLevel.CRITICAL
        if not gitlab.accessible:
            return AlertLevel.DEGRADED

        threshold = self.config.alerts.lag_commit_threshold
        lagging = sum(
            1 for r in repos
            if r.mirror_status in (MirrorStatus.LAGGING, MirrorStatus.FAILED)
            and r.lag_commits >= threshold
        )
        failed = sum(
            1 for r in repos
            if r.mirror_status == MirrorStatus.NEVER_SYNCED
        )

        if failed > 0:
            return AlertLevel.CRITICAL
        if lagging > 0:
            return AlertLevel.DEGRADED
        return AlertLevel.HEALTHY

    def _get_disk_usage(self, path: str) -> float:
        try:
            total, used, free = shutil.disk_usage(path)
            return round((used / total) * 100, 1)
        except Exception:
            return 0.0

    def build_alerts(
        self,
        gitea: GiteaHealth,
        gitlab: GitLabHealth,
        repos: list[RepoStatus],
    ) -> list[str]:
        alerts: list[str] = []

        if gitea.status == "down" and self.config.alerts.on_gitea_down:
            alerts.append(f"Gitea is DOWN: {gitea.error}")
        if not gitlab.accessible and self.config.alerts.on_gitlab_down:
            alerts.append(f"GitLab is unreachable: {gitlab.error}")

        if self.config.alerts.on_lagging_repos:
            threshold = self.config.alerts.lag_commit_threshold
            for r in repos:
                if r.lag_commits >= threshold:
                    alerts.append(
                        f"repo {r.name} is lagging by {r.lag_commits}+ commits "
                        f"(status: {r.mirror_status.value})"
                    )
        return alerts

    async def run_full_check(self, repos: list[RepoStatus]) -> HealthPayload:
        gitea_health = await self.check_gitea()
        gitlab_health = await self.check_gitlab()

        synced = sum(1 for r in repos if r.mirror_status == MirrorStatus.SYNCED)
        lagging = sum(1 for r in repos if r.mirror_status == MirrorStatus.LAGGING)
        failed = sum(1 for r in repos if r.mirror_status in (
            MirrorStatus.NEVER_SYNCED, MirrorStatus.UNKNOWN
        ))

        overall = await self.compute_overall_status(gitea_health, gitlab_health, repos)
        alerts = self.build_alerts(gitea_health, gitlab_health, repos)

        from datetime import datetime, timezone
        payload = HealthPayload(
            event=EventType.HEALTH_SUMMARY if not alerts else EventType.HEALTH_ALERT,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=overall,
            summary={
                "total_repos": len(repos),
                "synced": synced,
                "lagging": lagging,
                "failed": failed,
            },
            gitea=gitea_health,
            gitlab=gitlab_health,
            repos=repos,
            alerts=alerts,
        )
        return payload
