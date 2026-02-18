from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..errors import (
    OracleConfigurationError,
    OracleDependencyError,
    OracleReadError,
)


class GoogleCalendar:
    """Google Calendar wrapper with normalized event payloads."""

    READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
    READ_WRITE_SCOPE = "https://www.googleapis.com/auth/calendar"

    def __init__(
        self,
        calendar_id: str,
        service_account_file: str,
        read_only: bool = True,
        logger: Optional[logging.Logger] = None,
    ):
        if not calendar_id.strip():
            raise OracleConfigurationError("calendar_id cannot be empty")
        if not service_account_file.strip():
            raise OracleConfigurationError("service_account_file cannot be empty")

        account_path = Path(service_account_file)
        if not account_path.exists():
            raise OracleConfigurationError(
                f"Service account file not found: {account_path}"
            )
        if not account_path.is_file():
            raise OracleConfigurationError(
                f"Service account path is not a file: {account_path}"
            )

        self._logger = logger or logging.getLogger(__name__)
        self._calendar_id = calendar_id
        self._read_only = read_only
        self._api = self._build_api(str(account_path))

    def _build_api(self, service_account_file: str):
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as error:  # pragma: no cover - optional dependency
            raise OracleDependencyError(
                "Google Calendar dependencies missing. Install google-auth and "
                "google-api-python-client."
            ) from error

        scope = self.READONLY_SCOPE if self._read_only else self.READ_WRITE_SCOPE
        credentials = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=[scope],
        )
        return build("calendar", "v3", credentials=credentials, cache_discovery=False)

    def get_events(
        self,
        *,
        max_results: int = 10,
        time_min: Optional[dt.datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch upcoming events and return normalized fields."""
        if max_results < 1:
            raise ValueError(f"max_results must be >= 1, got: {max_results}")

        if time_min is None:
            time_min = dt.datetime.now(tz=dt.timezone.utc)
        elif time_min.tzinfo is None:
            time_min = time_min.replace(tzinfo=dt.timezone.utc)

        try:
            result = (
                self._api.events()
                .list(
                    calendarId=self._calendar_id,
                    timeMin=time_min.isoformat().replace("+00:00", "Z"),
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
        except Exception as error:  # pragma: no cover - network/API dependent
            raise OracleReadError(
                f"Failed to fetch Google Calendar events: {error}"
            ) from error

        events = result.get("items", []) or []
        return [self._normalize_event(event) for event in events]

    def add_event(
        self,
        summary: str,
        start: dt.datetime,
        end: dt.datetime,
        *,
        description: Optional[str] = None,
        location: Optional[str] = None,
        timezone: str = "UTC",
    ) -> str:
        self._ensure_write_enabled()
        if end <= start:
            raise ValueError("Event end must be after start.")

        body: Dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end.isoformat(), "timeZone": timezone},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location

        try:
            created = (
                self._api.events()
                .insert(calendarId=self._calendar_id, body=body)
                .execute()
            )
        except Exception as error:  # pragma: no cover - network/API dependent
            raise OracleReadError(
                f"Failed to create Google Calendar event: {error}"
            ) from error

        event_id = created.get("id")
        if not event_id:
            raise OracleReadError("Google Calendar create_event returned no event id.")
        return event_id

    def delete_event(self, event_id: str) -> None:
        self._ensure_write_enabled()
        if not event_id.strip():
            raise ValueError("event_id cannot be empty")
        try:
            self._api.events().delete(
                calendarId=self._calendar_id,
                eventId=event_id,
            ).execute()
        except Exception as error:  # pragma: no cover - network/API dependent
            raise OracleReadError(
                f"Failed to delete Google Calendar event: {error}"
            ) from error

    def update_event(
        self,
        event_id: str,
        *,
        summary: Optional[str] = None,
        start: Optional[dt.datetime] = None,
        end: Optional[dt.datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        timezone: str = "UTC",
    ) -> Dict[str, Any]:
        self._ensure_write_enabled()
        if not event_id.strip():
            raise ValueError("event_id cannot be empty")

        try:
            event = (
                self._api.events()
                .get(calendarId=self._calendar_id, eventId=event_id)
                .execute()
            )
        except Exception as error:  # pragma: no cover - network/API dependent
            raise OracleReadError(
                f"Failed to fetch event for update: {error}"
            ) from error

        if summary is not None:
            event["summary"] = summary
        if description is not None:
            event["description"] = description
        if location is not None:
            event["location"] = location
        if start is not None:
            event["start"] = {"dateTime": start.isoformat(), "timeZone": timezone}
        if end is not None:
            event["end"] = {"dateTime": end.isoformat(), "timeZone": timezone}

        try:
            return (
                self._api.events()
                .update(calendarId=self._calendar_id, eventId=event_id, body=event)
                .execute()
            )
        except Exception as error:  # pragma: no cover - network/API dependent
            raise OracleReadError(
                f"Failed to update Google Calendar event: {error}"
            ) from error

    @staticmethod
    def _normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
        start = (event.get("start") or {}).get("dateTime") or (
            event.get("start") or {}
        ).get("date")
        end = (event.get("end") or {}).get("dateTime") or (event.get("end") or {}).get(
            "date"
        )
        return {
            "id": event.get("id"),
            "summary": event.get("summary", "No Title"),
            "start": start,
            "end": end,
            "location": event.get("location"),
        }

    def _ensure_write_enabled(self) -> None:
        if self._read_only:
            raise OracleConfigurationError(
                "GoogleCalendar was initialized in read-only mode."
            )
