import pytest
from src.health_checker import HealthChecker
from src.models import (
    DrConfig, RepoStatus, MirrorStatus,
    GiteaHealth, GitLabHealth, AlertLevel,
)


@pytest.fixture
def config() -> DrConfig:
    return DrConfig()


@pytest.fixture
def checker(config: DrConfig) -> HealthChecker:
    return HealthChecker(config, None, None)


class TestHealthChecker:
    def test_disk_usage_returns_float(self, checker: HealthChecker) -> None:
        usage = checker._get_disk_usage("/")
        assert isinstance(usage, float)
        assert 0 <= usage <= 100

    @pytest.mark.asyncio
    async def test_compute_healthy(self, checker: HealthChecker) -> None:
        gitea = GiteaHealth(status="up")
        gitlab = GitLabHealth(accessible=True)
        repos: list[RepoStatus] = [
            RepoStatus(name="org/a", mirror_status=MirrorStatus.SYNCED),
            RepoStatus(name="org/b", mirror_status=MirrorStatus.SYNCED),
        ]
        status = await checker.compute_overall_status(gitea, gitlab, repos)
        assert status == AlertLevel.HEALTHY

    @pytest.mark.asyncio
    async def test_compute_critical_gitea_down(self, checker: HealthChecker) -> None:
        gitea = GiteaHealth(status="down", error="Down")
        gitlab = GitLabHealth(accessible=True)
        repos: list[RepoStatus] = [
            RepoStatus(name="org/a", mirror_status=MirrorStatus.SYNCED),
        ]
        status = await checker.compute_overall_status(gitea, gitlab, repos)
        assert status == AlertLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_compute_degraded_gitlab_down(self, checker: HealthChecker) -> None:
        gitea = GiteaHealth(status="up")
        gitlab = GitLabHealth(accessible=False)
        repos: list[RepoStatus] = [
            RepoStatus(name="org/a", mirror_status=MirrorStatus.SYNCED),
        ]
        status = await checker.compute_overall_status(gitea, gitlab, repos)
        assert status == AlertLevel.DEGRADED

    @pytest.mark.asyncio
    async def test_compute_degraded_lagging(self, checker: HealthChecker) -> None:
        gitea = GiteaHealth(status="up")
        gitlab = GitLabHealth(accessible=True)
        repos: list[RepoStatus] = [
            RepoStatus(name="org/a", mirror_status=MirrorStatus.SYNCED),
            RepoStatus(name="org/b", mirror_status=MirrorStatus.LAGGING, lag_commits=5),
        ]
        status = await checker.compute_overall_status(gitea, gitlab, repos)
        assert status == AlertLevel.DEGRADED

    @pytest.mark.asyncio
    async def test_compute_critical_never_synced(self, checker: HealthChecker) -> None:
        gitea = GiteaHealth(status="up")
        gitlab = GitLabHealth(accessible=True)
        repos: list[RepoStatus] = [
            RepoStatus(name="org/a", mirror_status=MirrorStatus.NEVER_SYNCED),
        ]
        status = await checker.compute_overall_status(gitea, gitlab, repos)
        assert status == AlertLevel.CRITICAL

    def test_build_alerts_empty_when_healthy(self, checker: HealthChecker) -> None:
        gitea = GiteaHealth(status="up")
        gitlab = GitLabHealth(accessible=True)
        repos: list[RepoStatus] = [
            RepoStatus(name="org/a", mirror_status=MirrorStatus.SYNCED),
        ]
        alerts = checker.build_alerts(gitea, gitlab, repos)
        assert alerts == []

    def test_build_alerts_gitea_down(self, checker: HealthChecker) -> None:
        gitea = GiteaHealth(status="down", error="Connection refused")
        gitlab = GitLabHealth(accessible=True)
        alerts = checker.build_alerts(gitea, gitlab, [])
        assert any("Gitea is DOWN" in a for a in alerts)

    def test_build_alerts_gitlab_down(self, checker: HealthChecker) -> None:
        gitea = GiteaHealth(status="up")
        gitlab = GitLabHealth(accessible=False, error="Timeout")
        alerts = checker.build_alerts(gitea, gitlab, [])
        assert any("GitLab is unreachable" in a for a in alerts)

    def test_build_alerts_lagging_above_threshold(self, config: DrConfig) -> None:
        config.alerts.lag_commit_threshold = 2
        checker = HealthChecker(config, None, None)
        gitea = GiteaHealth(status="up")
        gitlab = GitLabHealth(accessible=True)
        repos = [
            RepoStatus(name="org/a", mirror_status=MirrorStatus.LAGGING, lag_commits=3),
            RepoStatus(name="org/b", mirror_status=MirrorStatus.LAGGING, lag_commits=1),
        ]
        alerts = checker.build_alerts(gitea, gitlab, repos)
        assert len(alerts) == 1
        assert "org/a" in alerts[0]

    def test_build_alerts_disabled(self, config: DrConfig) -> None:
        config.alerts.on_lagging_repos = False
        config.alerts.on_gitea_down = False
        config.alerts.on_gitlab_down = False
        checker = HealthChecker(config, None, None)
        gitea = GiteaHealth(status="down")
        gitlab = GitLabHealth(accessible=False)
        repos = [
            RepoStatus(name="org/a", mirror_status=MirrorStatus.LAGGING, lag_commits=10),
        ]
        alerts = checker.build_alerts(gitea, gitlab, repos)
        assert alerts == []
