"""
DataSight Git Client — handles clone, branch, commit, and PR operations.

Uses GitPython for local operations and the GitHub API for PRs.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from datasight.config.settings import get_settings

logger = logging.getLogger("datasight.git")


class GitClient:
    """Git operations for DataSight patch management."""

    def __init__(self) -> None:
        settings = get_settings()
        self.repo_url = settings.git_repo_url
        self.token = settings.git_token
        self.branch_prefix = settings.git_branch_prefix
        self._repo = None

    def _get_repo(self):
        """Get or initialize the Git repo."""
        if self._repo:
            return self._repo

        try:
            import git

            settings = get_settings()
            dags_folder = settings.dags_folder

            # Check if DAGs folder is already a Git repo
            try:
                self._repo = git.Repo(dags_folder, search_parent_directories=True)
                logger.info("Using existing Git repo at %s", self._repo.working_dir)
            except git.InvalidGitRepositoryError:
                if self.repo_url:
                    clone_dir = "/tmp/datasight/repo"
                    os.makedirs(clone_dir, exist_ok=True)
                    self._repo = git.Repo.clone_from(self.repo_url, clone_dir)
                    logger.info("Cloned repo %s to %s", self.repo_url, clone_dir)
                else:
                    raise ValueError("No Git repo found and no repo URL configured")

            return self._repo

        except ImportError:
            raise ImportError("GitPython not installed. Run: pip install datasight-ai[git]")

    def commit_fix(
        self,
        filepath: str,
        message: str,
        branch: Optional[str] = None,
    ) -> str:
        """
        Commit a fix to a new branch.

        Args:
            filepath: Path to the modified file
            message: Commit message
            branch: Branch name (defaults to auto-generated)

        Returns:
            The commit SHA
        """
        repo = self._get_repo()

        # Create and checkout branch
        if branch:
            try:
                repo.git.checkout("-b", branch)
            except Exception:
                repo.git.checkout(branch)

        # Stage and commit
        repo.index.add([filepath])
        commit = repo.index.commit(message)
        sha = commit.hexsha[:8]

        logger.info("Committed fix: %s on branch %s", sha, branch or "current")

        # Push if remote exists
        try:
            origin = repo.remote("origin")
            origin.push(refspec=f"{branch}:{branch}")
            logger.info("Pushed branch %s to origin", branch)
        except Exception as e:
            logger.warning("Could not push: %s", e)

        return sha
