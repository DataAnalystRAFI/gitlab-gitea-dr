import pytest
from unittest.mock import AsyncMock
from src.mirror_manager import MirrorManager
from src.models import DrConfig, RepoStatus, MirrorStatus


@pytest.fixture
def config() -> DrConfig:
    return DrConfig()


@pytest.fixture
def manager(config: DrConfig) -> MirrorManager:
    gitea_mock = AsyncMock()
    gitea_mock._get_client = AsyncMock()
    gitea_mock.get_mirror_sync_status = AsyncMock(return_value={})
    gitea_mock.get_latest_commit = AsyncMock(return_value=None)
    gitlab_mock = AsyncMock()
    gitlab_mock.get_latest_commit = AsyncMock(return_value=None)
    return MirrorManager(config, gitlab_mock, gitea_mock)


class TestMirrorManager:
    @pytest.mark.asyncio
    async def test_check_sync_handles_empty_list(self, manager: MirrorManager) -> None:
        manager._gitea_owner = "test"
        result = await manager.check_sync_status([])
        assert result == []

    @pytest.mark.asyncio
    async def test_check_sync_returns_all_repos(self, manager: MirrorManager) -> None:
        manager._gitea_owner = "test"
        repos = [RepoStatus(name="org/a"), RepoStatus(name="org/b")]
        result = await manager.check_sync_status(repos)
        assert len(result) == 2
        for r in result:
            assert r.mirror_status == MirrorStatus.UNKNOWN
