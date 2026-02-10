"""Shared DB-backed service base classes for OpenClaw.

These helpers are intentionally small: they reduce boilerplate (session + logger) across
OpenClaw services without adding new architectural layers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


class OpenClawDBService:
    """Base class for OpenClaw services that require an AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        # Use the concrete subclass module for logger naming.
        self._logger = logging.getLogger(self.__class__.__module__)

    @property
    def session(self) -> AsyncSession:
        return self._session

    @session.setter
    def session(self, value: AsyncSession) -> None:
        self._session = value

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @logger.setter
    def logger(self, value: logging.Logger) -> None:
        self._logger = value

    async def add_commit_refresh(self, model: object) -> None:
        """Persist a model, committing the current transaction and refreshing when supported."""

        self.session.add(model)
        await self.session.commit()
        refresh = getattr(self.session, "refresh", None)
        if callable(refresh):
            await refresh(model)
