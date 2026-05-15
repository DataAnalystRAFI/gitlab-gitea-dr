from __future__ import annotations

import time
import httpx
from src.models import GitLabConfig, GitLabProject


class GitLabClient:
    def __init__(self, config: GitLabConfig) -> None:
        self.config = config
        self.base_url = config.url.rstrip("/")
        self.headers = {
            "PRIVATE-TOKEN": config.token,
            "User-Agent": "gitlab-gitea-dr-agent/1.0",
        }
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=self.config.request_timeout_secs,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _paginate(self, path: str, params: dict | None = None) -> list[dict]:
        client = await self._get_client()
        params = dict(params or {})
        params.setdefault("per_page", self.config.per_page)
        params.setdefault("page", 1)

        all_items: list[dict] = []
        while True:
            resp = await client.get(path, params=params)
            resp.raise_for_status()
            all_items.extend(resp.json())
            next_link = resp.headers.get("X-Next-Page", "")
            if not next_link or next_link == params.get("page"):
                break
            params["page"] = int(next_link)
        return all_items

    async def list_projects(self) -> list[GitLabProject]:
        raw = await self._paginate("/api/v4/projects", {
            "visibility": "public",
            "order_by": "last_activity_at",
            "sort": "desc",
            "membership": "true",
        })
        return [GitLabProject(**p) for p in raw]

    async def get_default_branch_commit(self, project_id: int) -> str | None:
        client = await self._get_client()
        try:
            resp = await client.get(f"/api/v4/projects/{project_id}/repository/branches")
            resp.raise_for_status()
            branches = resp.json()
            default = next(
                (b for b in branches if b.get("default", False)),
                branches[0] if branches else None,
            )
            if default:
                return default["commit"]["id"]
            return None
        except Exception:
            return None

    async def check_accessibility(self) -> tuple[bool, float]:
        start = time.monotonic()
        try:
            client = await self._get_client()
            resp = await client.get("/api/v4/version")
            elapsed = (time.monotonic() - start) * 1000
            return resp.is_success, elapsed
        except Exception:
            elapsed = (time.monotonic() - start) * 1000
            return False, elapsed

    async def get_latest_commit(self, repo_path: str, branch: str = "main") -> str | None:
        client = await self._get_client()
        try:
            resp = await client.get(
                f"/api/v4/projects/{repo_path.replace('/', '%2F')}/repository/commits",
                params={"ref_name": branch, "per_page": 1},
            )
            resp.raise_for_status()
            commits = resp.json()
            return commits[0]["id"] if commits else None
        except Exception:
            try:
                resp = await client.get(
                    f"/api/v4/projects/{repo_path.replace('/', '%2F')}/repository/commits",
                    params={"per_page": 1},
                )
                resp.raise_for_status()
                commits = resp.json()
                return commits[0]["id"] if commits else None
            except Exception:
                return None
