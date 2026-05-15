from src.models import (
    DrConfig, RepoStatus, MirrorStatus, AlertLevel,
    HealthPayload, GiteaHealth, GitLabHealth,
)


class TestModels:
    def test_dr_config_defaults(self) -> None:
        config = DrConfig()
        assert config.gitlab.url == "https://gitlab.com"
        assert config.gitea.url == "http://gitea:3000"
        assert config.mirror.sync_interval_hours == 1
        assert config.alerts.lag_commit_threshold == 3

    def test_dr_config_from_dict(self) -> None:
        data = {
            "gitlab": {"token": "gl-abc"},
            "gitea": {"token": "gt-xyz"},
            "webhook": {"url": "https://hooks.example.com/dr"},
        }
        config = DrConfig(**data)
        assert config.gitlab.token == "gl-abc"
        assert config.gitea.token == "gt-xyz"
        assert config.webhook.url == "https://hooks.example.com/dr"

    def test_repo_status_defaults(self) -> None:
        r = RepoStatus(name="org/repo")
        assert r.name == "org/repo"
        assert r.mirror_status == MirrorStatus.UNKNOWN
        assert r.lag_commits == 0

    def test_health_payload_defaults(self) -> None:
        p = HealthPayload(timestamp="2026-01-01T00:00:00Z")
        assert p.status == AlertLevel.HEALTHY
        assert p.summary["total_repos"] == 0
        assert p.gitea.status == "up"

    def test_alert_level_values(self) -> None:
        assert AlertLevel.HEALTHY.value == "healthy"
        assert AlertLevel.DEGRADED.value == "degraded"
        assert AlertLevel.CRITICAL.value == "critical"

    def test_health_payload_with_repos(self) -> None:
        repos = [
            RepoStatus(name="org/alpha", mirror_status=MirrorStatus.SYNCED),
            RepoStatus(name="org/beta", mirror_status=MirrorStatus.LAGGING, lag_commits=5),
        ]
        p = HealthPayload(
            timestamp="2026-01-01T00:00:00Z",
            status=AlertLevel.DEGRADED,
            repos=repos,
            alerts=["repo org/beta is lagging"],
        )
        assert len(p.repos) == 2
        assert p.status == AlertLevel.DEGRADED
        assert len(p.alerts) == 1

    def test_mirror_status_enum(self) -> None:
        assert MirrorStatus.SYNCED.value == "synced"
        assert MirrorStatus.LAGGING.value == "lagging"
        assert MirrorStatus.NEVER_SYNCED.value == "never_synced"

    def test_gitea_health_down(self) -> None:
        h = GiteaHealth(status="down", error="Connection refused")
        assert h.status == "down"
        assert h.error == "Connection refused"

    def test_gitlab_health_not_accessible(self) -> None:
        h = GitLabHealth(accessible=False, latency_ms=5000)
        assert not h.accessible
        assert h.latency_ms == 5000.0
