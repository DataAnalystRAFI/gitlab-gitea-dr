from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.gitlab_client import GitLabClient
from src.gitea_client import GiteaClient
from src.health_checker import HealthChecker
from src.mirror_manager import MirrorManager
from src.webhook_sender import WebhookSender
from src.models import DrConfig, RepoStatus, MirrorStatus, EventType, HealthPayload

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("/app/config/dr-config.yml")
ARTIFACTS_DIR = Path("/app/artifacts")
STATE_FILE = ARTIFACTS_DIR / "dr_state.json"


def load_config(path: Path | str) -> DrConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    raw = path.read_text()
    resolved = os.path.expandvars(raw)
    data = yaml.safe_load(resolved)
    return DrConfig(**data)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {"repos": [], "last_check": None, "last_summary": None}


def save_state(state: dict) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


async def run_check(config: DrConfig, force_summary: bool = False) -> HealthPayload | None:
    gitlab = GitLabClient(config.gitlab)
    gitea = GiteaClient(config.gitea)
    state = load_state()

    try:
        manager = MirrorManager(config, gitlab, gitea)
        checker = HealthChecker(config, gitlab, gitea)
        webhook = WebhookSender(config.webhook)

        existing = [RepoStatus(**r) for r in state.get("repos", [])]

        if not existing:
            logger.info("No cached repo state — reconciling mirrors")
            existing = await manager.reconcile_mirrors()
        else:
            repo_sync_interval = config.scheduling.repo_sync_interval_secs
            last_sync = state.get("last_repo_sync")
            if last_sync:
                last = datetime.fromisoformat(last_sync)
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                if elapsed > repo_sync_interval:
                    logger.info("Repo sync interval elapsed — reconciling")
                    existing = await manager.reconcile_mirrors()

        checked = await manager.check_sync_status(existing)
        state["repos"] = [r.model_dump(mode="json") for r in checked]
        state["last_check"] = datetime.now(timezone.utc).isoformat()
        save_state(state)

        payload = await checker.run_full_check(checked)

        now = datetime.now(timezone.utc)
        last_summary_str = state.get("last_summary")
        should_summary = force_summary

        if not should_summary and last_summary_str:
            last_summary = datetime.fromisoformat(last_summary_str)
            elapsed = (now - last_summary).total_seconds()
            if elapsed >= config.scheduling.summary_interval_secs:
                should_summary = True

        if should_summary or payload.alerts:
            sent = await webhook.send(payload)
            if sent:
                payload.event = EventType.HEALTH_SUMMARY
                state["last_summary"] = now.isoformat()
                save_state(state)

        status_counts = {
            "total": len(checked),
            "synced": sum(1 for r in checked if r.mirror_status == MirrorStatus.SYNCED),
            "lagging": sum(1 for r in checked if r.mirror_status == MirrorStatus.LAGGING),
            "failed": sum(1 for r in checked if r.mirror_status in (
                MirrorStatus.NEVER_SYNCED, MirrorStatus.UNKNOWN
            )),
        }
        logger.info(
            "Check complete: status=%s repos=%(total)d synced=%(synced)d lagging=%(lagging)d failed=%(failed)d alerts=%(alerts)d",
            payload.status.value,
            {**status_counts, "alerts": len(payload.alerts)},
        )

        save_check_artifact(payload)
        return payload

    finally:
        await gitlab.close()
        await gitea.close()


def save_check_artifact(payload: HealthPayload) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = ARTIFACTS_DIR / f"check_{ts}.json"
    path.write_text(payload.model_dump_json(indent=2))
    latest = ARTIFACTS_DIR / "latest_check.json"
    latest.write_text(payload.model_dump_json(indent=2))


async def run_daemon(config: DrConfig) -> None:
    logger.info("Starting DR agent daemon (check every %ds)", config.scheduling.check_interval_secs)
    while True:
        try:
            await run_check(config)
        except Exception as e:
            logger.exception("Check cycle failed: %s", e)
        await asyncio.sleep(config.scheduling.check_interval_secs)


def main() -> None:
    parser = argparse.ArgumentParser(description="GitLab → Gitea DR Agent")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to dr-config.yml")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument("--daemon", action="store_true", help="Run in continuous loop")
    parser.add_argument("--check", action="store_true", help="Run single health check")
    parser.add_argument("--summary", action="store_true", help="Force full summary webhook")

    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        logger.error("Config error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.exception("Failed to load config: %s", e)
        sys.exit(1)

    if args.daemon:
        asyncio.run(run_daemon(config))
    elif args.check or args.summary:
        asyncio.run(run_check(config, force_summary=args.summary))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
