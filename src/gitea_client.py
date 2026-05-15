from __future__ import annotations

import httpx
from src.models import GiteaConfig, GiteaMirror, GitLabProject


class GiteaClient:
    def __init__(self, config: GiteaConfig) -> None:
        self.config = config
        self.base_url = config.url.rstrip("/")
        self.headers = {
            "Authorization": f"token {config.token}",
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
        params.setdefault("limit", 50)
        params.setdefault("page", 1)

        all_items: list[dict] = []
        while True:
            resp = await client.get(path, params=params)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            all_items.extend(data)
            if len(data) < params.get("limit", 50):
                break
            params["page"] = params["page"] + 1
        return all_items

    async def check_health(self) -> tuple[bool, str | None]:
        client = await self._get_client()
        try:
            resp = await client.get("/api/v1/version")
            if resp.is_success:
                return True, resp.json().get("version")
            return False, None
        except Exception:
            return False, None

    async def create_pull_mirror(self, project: GitLabProject, owner: str) -> GiteaMirror | None:
        client = await self._get_client()
        payload = {
            "clone_addr": project.http_url_to_repo,
            "mirror": True,
            "private": True,
            "uid": 1,
            "repo_name": project.name,
            "repo_owner": owner,
            "description": f"DR mirror of {project.path_with_namespace}",
            "auth_username": "",
            "auth_password": "",
            "auth_token": self.config.token,
        }
        try:
            resp = await client.post("/api/v1/repos/migrate", json=payload)
            if resp.is_success:
                data = resp.json()
                return GiteaMirror(**data)
            if resp.status_code == 409:
                existing = await self.get_mirror(owner, project.name)
                if existing:
                    return existing
            return None
        except Exception:
            return None

    async def get_mirror(self, owner: str, repo: str) -> GiteaMirror | None:
        client = await self._get_client()
        try:
            resp = await client.get(f"/api/v1/repos/{owner}/{repo}")
            if resp.is_success:
                data = resp.json()
                return GiteaMirror(**data)
            return None
        except Exception:
            return None

    async def list_mirrors(self) -> list[GiteaMirror]:
        raw = await self._paginate("/api/v1/repos/search", {"uid": 1})
        return [GiteaMirror(**r) for r in raw]

    async def get_latest_commit(self, owner: str, repo: str, branch: str = "main") -> str | None:
        client = await self._get_client()
        try:
            resp = await client.get(
                f"/api/v1/repos/{owner}/{repo}/branches/{branch}"
            )
            if resp.is_success:
                data = resp.json()
                return data["commit"]["id"]
            return None
        except Exception:
            return None

    async def get_mirror_sync_status(self, owner: str, repo: str) -> dict:
        client = await self._get_client()
        try:
            resp = await client.get(f"/api/v1/repos/{owner}/{repo}")
            if resp.is_success:
                data = resp.json()
                return {
                    "mirror_interval": data.get("mirror_interval"),
                    "mirror_updated": data.get("mirror_updated"),
                }
            return {}
        except Exception:
            return {}
