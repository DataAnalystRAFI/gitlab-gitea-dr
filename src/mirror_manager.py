from __future__ import annotations

import logging
from src.models import DrConfig, GitLabProject, GiteaMirror, RepoStatus, MirrorStatus
from src.gitlab_client import GitLabClient
from src.gitea_client import GiteaClient

logger = logging.getLogger(__name__)


class MirrorManager:
    def __init__(self, config: DrConfig, gitlab: GitLabClient, gitea: GiteaClient) -> None:
        self.config = config
        self.gitlab = gitlab
        self.gitea = gitea
        self._gitea_owner: str | None = None

    async def _ensure_owner(self) -> str:
        if self._gitea_owner:
            return self._gitea_owner
        client = await self.gitea._get_client()
        resp = await client.get("/api/v1/user")
        if resp.is_success:
            self._gitea_owner = resp.json().get("username", "root")
        else:
            self._gitea_owner = "root"
        return self._gitea_owner

    async def reconcile_mirrors(self) -> list[RepoStatus]:
        owner = await self._ensure_owner()
        logger.info("Reconciling mirrors for owner: %s", owner)

        gitlab_projects = await self.gitlab.list_projects()
        gitea_mirrors = await self.gitea.list_mirrors()

        gitlab_map: dict[str, GitLabProject] = {}
        for p in gitlab_projects:
            key = p.path_with_namespace.lower()
            gitlab_map[key] = p

        gitea_map: dict[str, GiteaMirror] = {}
        for m in gitea_mirrors:
            key = m.full_name.lower()
            gitea_map[key] = m

        results: list[RepoStatus] = []
        created_count = 0

        for path, project in gitlab_map.items():
            gitea_full = f"{owner}/{project.name}"
            existing = gitea_map.get(gitea_full.lower())

            if existing and existing.mirror:
                status = RepoStatus(
                    name=project.path_with_namespace,
                    gitlab_id=project.id,
                    mirror_status=MirrorStatus.UNKNOWN,
                    mirror_url=existing.clone_addr,
                )
                results.append(status)
            elif existing and not existing.mirror:
                status = RepoStatus(
                    name=project.path_with_namespace,
                    gitlab_id=project.id,
                    mirror_status=MirrorStatus.UNKNOWN,
                    error="Repo exists in Gitea but mirroring is not enabled",
                )
                results.append(status)
            else:
                logger.info("Creating mirror for %s", project.path_with_namespace)
                created = await self.gitea.create_pull_mirror(project, owner)
                if created:
                    created_count += 1
                    status = RepoStatus(
                        name=project.path_with_namespace,
                        gitlab_id=project.id,
                        mirror_status=MirrorStatus.NEVER_SYNCED,
                        mirror_url=project.http_url_to_repo,
                    )
                else:
                    status = RepoStatus(
                        name=project.path_with_namespace,
                        gitlab_id=project.id,
                        mirror_status=MirrorStatus.UNKNOWN,
                        error="Failed to create mirror in Gitea",
                    )
                results.append(status)

        if created_count:
            logger.info("Created %d new mirrors", created_count)
        return results

    async def check_sync_status(self, repos: list[RepoStatus]) -> list[RepoStatus]:
        owner = await self._ensure_owner()
        checked: list[RepoStatus] = []
        stale_secs = self.config.mirror.stale_threshold_hours * 3600

        for repo in repos:
            try:
                short_name = repo.name.split("/")[-1]
                gitea_sync = await self.gitea.get_mirror_sync_status(owner, short_name)
                gitea_commit = await self.gitea.get_latest_commit(owner, short_name)
                gitlab_commit = None
                try:
                    gitlab_commit = await self.gitlab.get_latest_commit(repo.name)
                except Exception:
                    pass

                mirror_updated_str = gitea_sync.get("mirror_updated")
                last_synced_ago = None
                if mirror_updated_str:
                    from datetime import datetime, timezone
                    try:
                        updated = datetime.fromisoformat(
                            mirror_updated_str.replace("Z", "+00:00")
                        )
                        last_synced_ago = (
                            datetime.now(timezone.utc) - updated
                        ).total_seconds()
                    except Exception:
                        pass

                if gitlab_commit and gitea_commit:
                    if gitlab_commit == gitea_commit:
                        mirror_status = MirrorStatus.SYNCED
                    else:
                        mirror_status = MirrorStatus.LAGGING
                elif gitlab_commit and not gitea_commit:
                    mirror_status = MirrorStatus.NEVER_SYNCED
                else:
                    mirror_status = MirrorStatus.UNKNOWN

                lag = 0
                if gitlab_commit and gitea_commit and gitlab_commit != gitea_commit:
                    lag = 1

                if last_synced_ago and last_synced_ago > stale_secs:
                    if mirror_status == MirrorStatus.SYNCED:
                        mirror_status = MirrorStatus.LAGGING

                repo.mirror_status = mirror_status
                repo.gitlab_latest_commit = gitlab_commit
                repo.gitea_latest_commit = gitea_commit
                repo.lag_commits = lag
                repo.last_synced_ago_secs = last_synced_ago
                checked.append(repo)
            except Exception as e:
                logger.warning("Failed to check sync for %s: %s", repo.name, e)
                repo.error = str(e)
                repo.mirror_status = MirrorStatus.UNKNOWN
                checked.append(repo)

        return checked
