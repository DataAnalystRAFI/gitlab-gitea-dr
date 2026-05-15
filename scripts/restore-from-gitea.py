#!/usr/bin/env python3
"""DR restore: clone a repo from Gitea mirror when GitLab is unavailable."""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("restore-from-gitea")

GITEA_URL = os.environ.get("GITEA_URL", "http://localhost:3000")


def clone_from_gitea(repo_name: str, dest: str, owner: str = "root", bare: bool = False) -> None:
    clone_url = f"{GITEA_URL}/{owner}/{repo_name}.git"
    dest_path = Path(dest).resolve()

    if dest_path.exists():
        logger.error("Destination %s already exists", dest_path)
        sys.exit(1)

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["git", "clone"]
    if bare:
        cmd.append("--bare")
    cmd.extend([clone_url, str(dest_path)])

    logger.info("Cloning from Gitea mirror: %s", clone_url)
    logger.info("Destination: %s", dest_path)
    logger.info("Command: %s", " ".join(cmd))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info("Clone successful: %s", result.stdout.strip())
    except subprocess.CalledProcessError as e:
        logger.error("Clone failed (exit %d): %s", e.returncode, e.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore repo from Gitea mirror")
    parser.add_argument("--repo", required=True, help="Repository name (e.g. my-project)")
    parser.add_argument("--dest", required=True, help="Destination directory")
    parser.add_argument("--owner", default="root", help="Gitea owner/org (default: root)")
    parser.add_argument("--bare", action="store_true", help="Clone bare repository")
    args = parser.parse_args()

    clone_from_gitea(args.repo, args.dest, args.owner, args.bare)


if __name__ == "__main__":
    main()
