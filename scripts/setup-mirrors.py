#!/usr/bin/env python3
"""One-time bootstrap: read all GitLab projects, create pull mirrors in Gitea."""

import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gitlab_client import GitLabClient
from src.gitea_client import GiteaClient
from src.mirror_manager import MirrorManager
from src.models import DrConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("setup-mirrors")


def load_config() -> DrConfig:
    config_path = Path(__file__).resolve().parent.parent / "config" / "dr-config.yml"
    if not config_path.exists():
        config_path = Path(os.environ.get("DR_CONFIG", "/app/config/dr-config.yml"))
    raw = config_path.read_text()
    resolved = os.path.expandvars(raw)
    data = yaml.safe_load(resolved)
    return DrConfig(**data)


async def main() -> None:
    config = load_config()
    gitlab = GitLabClient(config.gitlab)
    gitea = GiteaClient(config.gitea)
    manager = MirrorManager(config, gitlab, gitea)

    logger.info("Fetching GitLab projects...")
    projects = await gitlab.list_projects()
    logger.info("Found %d projects on GitLab", len(projects))

    logger.info("Reconciling mirrors with Gitea...")
    results = await manager.reconcile_mirrors()

    created = [r for r in results if r.mirror_status.value == "never_synced"]
    existing = [r for r in results if r.mirror_status.value != "never_synced"]
    failed = [r for r in results if r.error]

    logger.info("Done: %d created, %d existing, %d failed", len(created), len(existing), len(failed))
    for r in created:
        logger.info("  + %s", r.name)
    for r in failed:
        logger.warning("  ! %s: %s", r.name, r.error)

    await gitlab.close()
    await gitea.close()


if __name__ == "__main__":
    asyncio.run(main())
