from __future__ import annotations

from app.dal.repo_mysql import RepoMySQL


class MovementsService:
    def __init__(self, repo: RepoMySQL):
        self.repo = repo

    def list_recent(self, limit: int):
        return self.repo.list_recent_movements(limit)
