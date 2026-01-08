"""Tests for the Asana adapter."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from spectryn.adapters.asana import AsanaAdapter
from spectryn.core.exceptions import ResourceNotFoundError
from spectryn.core.ports.config_provider import TrackerConfig


class FakeResponse:
    """Simple fake response object for mocking requests.Session."""

    def __init__(self, status_code: int, data: dict[str, Any]):
        self.status_code = status_code
        self._data = data
        self.text = ""

    def json(self) -> dict[str, Any]:  # pragma: no cover - trivial
        return self._data


@pytest.fixture
def tracker_config() -> TrackerConfig:
    return TrackerConfig(
        url="https://app.asana.com/api/1.0",
        email="user@example.com",
        api_token="token",
        project_key="12345",
    )


def test_test_connection_sets_connected(tracker_config: TrackerConfig) -> None:
    session = MagicMock()
    session.request.return_value = FakeResponse(200, {"data": {"gid": "1", "name": "Me"}})

    adapter = AsanaAdapter(config=tracker_config, session=session)

    assert adapter.test_connection() is True
    assert adapter.is_connected is True


def test_get_issue_parses_fields(tracker_config: TrackerConfig) -> None:
    session = MagicMock()
    session.request.return_value = FakeResponse(
        200,
        {
            "data": {
                "gid": "42",
                "name": "Implement Asana output",
                "notes": "Markdown synced to Asana",
                "completed": False,
                "resource_subtype": "task",
                "assignee": {"gid": "7", "name": "Sky"},
                "custom_fields": [
                    {"name": "Story Points", "number_value": 5},
                ],
            }
        },
    )

    adapter = AsanaAdapter(config=tracker_config, session=session)
    issue = adapter.get_issue("42")

    assert issue.key == "42"
    assert issue.summary == "Implement Asana output"
    assert issue.description == "Markdown synced to Asana"
    assert issue.status == "In Progress"
    assert issue.assignee == "7"
    assert issue.story_points == 5


def test_create_subtask_sends_payload(tracker_config: TrackerConfig) -> None:
    session = MagicMock()
    session.request.return_value = FakeResponse(200, {"data": {"gid": "555"}})

    adapter = AsanaAdapter(config=tracker_config, session=session, dry_run=False)

    subtask_key = adapter.create_subtask(
        parent_key="100",
        summary="Write Asana adapter",
        description="Ensure Spectra can target Asana",
        project_key="9876",
        story_points=3,
        assignee="7",
    )

    assert subtask_key == "555"
    method, url = session.request.call_args[0][:2]
    assert method == "POST"
    assert url.endswith("/tasks/100/subtasks")
    payload = session.request.call_args.kwargs["json"]["data"]
    assert payload["projects"] == ["9876"]
    assert payload["custom_fields"][tracker_config.story_points_field] == 3


def test_missing_issue_raises_not_found(tracker_config: TrackerConfig) -> None:
    session = MagicMock()
    session.request.return_value = FakeResponse(404, {"errors": [{"message": "Task not found"}]})

    adapter = AsanaAdapter(config=tracker_config, session=session)

    with pytest.raises(ResourceNotFoundError):
        adapter.get_issue("missing")


def test_get_epic_children_paginates(tracker_config: TrackerConfig) -> None:
    """Verify that get_epic_children follows next_page cursors."""
    session = MagicMock()

    # First page with next_page cursor
    page1 = FakeResponse(
        200,
        {
            "data": [
                {"gid": "1", "name": "Task 1", "completed": False},
                {"gid": "2", "name": "Task 2", "completed": True},
            ],
            "next_page": {"offset": "cursor123"},
        },
    )
    # Second page with no next_page (end of results)
    page2 = FakeResponse(
        200,
        {
            "data": [
                {"gid": "3", "name": "Task 3", "completed": False},
            ],
            "next_page": None,
        },
    )

    session.request.side_effect = [page1, page2]

    adapter = AsanaAdapter(config=tracker_config, session=session)
    children = adapter.get_epic_children("12345")

    # Should have fetched all 3 tasks across 2 pages
    assert len(children) == 3
    assert children[0].key == "1"
    assert children[1].key == "2"
    assert children[2].key == "3"

    # Should have made 2 requests
    assert session.request.call_count == 2

    # Second request should include offset parameter
    second_call_params = session.request.call_args_list[1].kwargs.get("params", {})
    assert second_call_params.get("offset") == "cursor123"
