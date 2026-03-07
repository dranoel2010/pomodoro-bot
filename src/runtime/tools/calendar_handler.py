"""Domain handler for calendar tool commands."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from llm.types import JSONObject

from .calendar import handle_calendar_tool_call

if TYPE_CHECKING:
    from app_config import AppConfig
    from oracle.service import OracleContextService


class CalendarToolHandler:
    """Executes calendar tool calls via Oracle-backed runtime services."""

    def __init__(
        self,
        *,
        logger: logging.Logger,
        app_config: "AppConfig",
        oracle_service: "OracleContextService" | None,
    ) -> None:
        self._logger = logger
        self._app_config = app_config
        self._oracle_service = oracle_service

    def handle(self, tool_name: str, arguments: JSONObject) -> str:
        return handle_calendar_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            oracle_service=self._oracle_service,
            app_config=self._app_config,
            logger=self._logger,
        )
