"""Tests for AI Sync Summary module."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from spectra.application.ai_sync_summary import (
    AISyncSummaryGenerator,
    SummaryOptions,
    SyncAction,
    SyncedEntity,
    SyncEntityType,
    SyncOperation,
    SyncSummary,
    build_summary_prompt,
    generate_summary_fallback,
    parse_summary_response,
)


@pytest.fixture
def created_entity() -> SyncedEntity:
    """Create a created entity."""
    return SyncedEntity(
        entity_type=SyncEntityType.STORY,
        entity_id="US-001",
        title="User Login",
        action=SyncAction.CREATED,
        source="markdown",
        target="jira",
        changes=["Created new story"],
    )


@pytest.fixture
def updated_entity() -> SyncedEntity:
    """Create an updated entity."""
    return SyncedEntity(
        entity_type=SyncEntityType.STORY,
        entity_id="US-002",
        title="User Registration",
        action=SyncAction.UPDATED,
        source="markdown",
        target="jira",
        changes=["Updated priority", "Added AC"],
    )


@pytest.fixture
def failed_entity() -> SyncedEntity:
    """Create a failed entity."""
    return SyncedEntity(
        entity_type=SyncEntityType.STORY,
        entity_id="US-003",
        title="Broken Story",
        action=SyncAction.FAILED,
        source="markdown",
        target="jira",
        error="Missing required field: description",
    )


@pytest.fixture
def sync_operation(
    created_entity: SyncedEntity,
    updated_entity: SyncedEntity,
    failed_entity: SyncedEntity,
) -> SyncOperation:
    """Create a sync operation with mixed results."""
    return SyncOperation(
        operation_id="sync-001",
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        source="markdown",
        target="jira",
        entities=[created_entity, updated_entity, failed_entity],
        duration_seconds=5.2,
        dry_run=False,
    )


class TestSyncAction:
    """Tests for SyncAction enum."""

    def test_action_values(self) -> None:
        """Test sync action enum values."""
        assert SyncAction.CREATED.value == "created"
        assert SyncAction.UPDATED.value == "updated"
        assert SyncAction.DELETED.value == "deleted"
        assert SyncAction.FAILED.value == "failed"
        assert SyncAction.SKIPPED.value == "skipped"


class TestSyncEntityType:
    """Tests for SyncEntityType enum."""

    def test_entity_type_values(self) -> None:
        """Test entity type enum values."""
        assert SyncEntityType.STORY.value == "story"
        assert SyncEntityType.EPIC.value == "epic"
        assert SyncEntityType.SUBTASK.value == "subtask"
        assert SyncEntityType.COMMENT.value == "comment"


class TestSyncedEntity:
    """Tests for SyncedEntity dataclass."""

    def test_entity_creation(self, created_entity: SyncedEntity) -> None:
        """Test creating a synced entity."""
        assert created_entity.entity_id == "US-001"
        assert created_entity.action == SyncAction.CREATED
        assert created_entity.is_success is True

    def test_is_success_for_failed(self, failed_entity: SyncedEntity) -> None:
        """Test is_success for failed entity."""
        assert failed_entity.is_success is False


class TestSyncOperation:
    """Tests for SyncOperation dataclass."""

    def test_operation_counts(self, sync_operation: SyncOperation) -> None:
        """Test operation count properties."""
        assert sync_operation.created_count == 1
        assert sync_operation.updated_count == 1
        assert sync_operation.deleted_count == 0
        assert sync_operation.failed_count == 1
        assert sync_operation.total_count == 3

    def test_success_rate(self, sync_operation: SyncOperation) -> None:
        """Test success rate calculation."""
        # 2 successful out of 3
        assert sync_operation.success_rate == pytest.approx(66.67, rel=0.01)

    def test_empty_operation(self) -> None:
        """Test empty operation defaults."""
        operation = SyncOperation()
        assert operation.total_count == 0
        assert operation.success_rate == 100.0


class TestSyncSummary:
    """Tests for SyncSummary dataclass."""

    def test_to_markdown(self) -> None:
        """Test markdown output."""
        summary = SyncSummary(
            headline="Synced 5 stories",
            overview="Completed successfully.",
            key_changes=["Created US-001", "Updated US-002"],
            issues=["Failed US-003"],
            recommendations=["Review failed items"],
            stats={"Created": 1, "Updated": 1},
        )

        md = summary.to_markdown()

        assert "# Synced 5 stories" in md
        assert "Completed successfully." in md
        assert "## Key Changes" in md
        assert "Created US-001" in md
        assert "⚠️" in md
        assert "💡" in md

    def test_to_slack(self) -> None:
        """Test Slack output."""
        summary = SyncSummary(
            headline="Synced 5 stories",
            overview="Completed.",
            key_changes=["Created US-001"],
            stats={"Created": 1},
        )

        slack = summary.to_slack()

        assert "*Synced 5 stories*" in slack
        assert "📊" in slack
        assert "•" in slack


class TestSummaryOptions:
    """Tests for SummaryOptions configuration."""

    def test_default_options(self) -> None:
        """Test default summary options."""
        options = SummaryOptions()

        assert options.include_details is True
        assert options.include_recommendations is True
        assert options.max_key_changes == 10
        assert options.audience == "technical"

    def test_custom_options(self) -> None:
        """Test custom summary options."""
        options = SummaryOptions(
            audience="manager",
            format="slack",
            max_key_changes=5,
        )

        assert options.audience == "manager"
        assert options.format == "slack"
        assert options.max_key_changes == 5


class TestBuildSummaryPrompt:
    """Tests for prompt building."""

    def test_basic_prompt(self, sync_operation: SyncOperation) -> None:
        """Test basic prompt generation."""
        options = SummaryOptions()
        prompt = build_summary_prompt(sync_operation, options)

        assert "markdown" in prompt
        assert "jira" in prompt
        assert "US-001" in prompt
        assert "US-002" in prompt
        assert "Created: 1" in prompt
        assert "Updated: 1" in prompt

    def test_prompt_includes_audience(self, sync_operation: SyncOperation) -> None:
        """Test prompt includes audience."""
        options = SummaryOptions(audience="manager")
        prompt = build_summary_prompt(sync_operation, options)

        assert "manager" in prompt


class TestParseSummaryResponse:
    """Tests for parsing LLM responses."""

    def test_parse_valid_response(self) -> None:
        """Test parsing valid JSON response."""
        response = json.dumps(
            {
                "headline": "Synced 10 stories to Jira",
                "overview": "Successfully synchronized with 2 failures.",
                "key_changes": ["Created US-001", "Updated US-002"],
                "issues": ["Failed US-003: Missing description"],
                "recommendations": ["Fix missing fields"],
                "stats": {"Created": 1, "Updated": 1, "Failed": 1},
                "detailed_changes": {"US-001": ["Created new story"]},
            }
        )

        summary = parse_summary_response(response)

        assert summary.headline == "Synced 10 stories to Jira"
        assert len(summary.key_changes) == 2
        assert len(summary.issues) == 1
        assert summary.stats["Created"] == 1

    def test_parse_fallback_on_invalid_json(self) -> None:
        """Test fallback when JSON is invalid."""
        response = "This is not JSON but a plain text summary"

        summary = parse_summary_response(response)

        # Should use response as overview
        assert summary.overview != ""


class TestGenerateSummaryFallback:
    """Tests for fallback summary generation."""

    def test_fallback_with_mixed_results(self, sync_operation: SyncOperation) -> None:
        """Test fallback generates correct summary."""
        options = SummaryOptions()
        summary = generate_summary_fallback(sync_operation, options)

        assert "3 items" in summary.headline
        assert "markdown" in summary.headline
        assert "jira" in summary.headline
        assert summary.stats["Created"] == 1
        assert summary.stats["Updated"] == 1
        assert summary.stats["Failed"] == 1
        assert len(summary.key_changes) > 0
        assert len(summary.issues) > 0

    def test_fallback_dry_run(self) -> None:
        """Test fallback for dry run."""
        operation = SyncOperation(
            source="markdown",
            target="github",
            dry_run=True,
            entities=[
                SyncedEntity(
                    entity_type=SyncEntityType.STORY,
                    entity_id="US-001",
                    title="Test",
                    action=SyncAction.CREATED,
                )
            ],
        )

        options = SummaryOptions()
        summary = generate_summary_fallback(operation, options)

        assert "Dry Run" in summary.headline

    def test_fallback_empty_operation(self) -> None:
        """Test fallback for empty operation."""
        operation = SyncOperation(source="markdown", target="jira")
        options = SummaryOptions()

        summary = generate_summary_fallback(operation, options)

        assert "No changes made" in summary.overview


class TestAISyncSummaryGenerator:
    """Tests for AISyncSummaryGenerator class."""

    def test_generate_with_fallback(self, sync_operation: SyncOperation) -> None:
        """Test generation falls back without LLM."""
        with patch("spectra.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            generator = AISyncSummaryGenerator()
            summary = generator.generate(sync_operation)

            assert summary.headline != ""
            assert len(summary.stats) > 0

    def test_generate_with_mocked_llm(self, sync_operation: SyncOperation) -> None:
        """Test generation with mocked LLM."""
        mock_response_content = json.dumps(
            {
                "headline": "Successfully synced 3 stories",
                "overview": "Completed in 5.2 seconds with 1 failure.",
                "key_changes": ["Created US-001: User Login"],
                "issues": ["US-003 failed due to missing description"],
                "recommendations": ["Add description to US-003"],
                "stats": {"Created": 1, "Updated": 1, "Failed": 1},
            }
        )

        with patch("spectra.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = True

            mock_response = MagicMock()
            mock_response.content = mock_response_content
            mock_response.total_tokens = 150
            mock_response.model = "claude-3"
            mock_response.provider = "anthropic"
            mock_mgr.prompt.return_value = mock_response

            mock_manager.return_value = mock_mgr

            generator = AISyncSummaryGenerator()
            summary = generator.generate(sync_operation)

            assert summary.headline == "Successfully synced 3 stories"
            assert summary.provider_used == "anthropic"

    def test_generate_from_results(self) -> None:
        """Test generating from raw results."""
        results = [
            {"id": "US-001", "title": "Login", "created": True},
            {"id": "US-002", "title": "Register", "updated": True, "changes": ["Priority"]},
            {"id": "US-003", "title": "Broken", "error": "Missing field"},
        ]

        with patch("spectra.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            generator = AISyncSummaryGenerator()
            summary = generator.generate_from_results(
                results,
                source="markdown",
                target="jira",
                duration=3.5,
            )

            assert summary.headline != ""
            assert summary.stats["Created"] == 1
            assert summary.stats["Updated"] == 1
            assert summary.stats["Failed"] == 1
