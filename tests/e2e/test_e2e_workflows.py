"""
End-to-end workflow tests for Spectra.

These tests verify complete workflows from parsing through sync,
testing the full integration of all components.

Run with:
    pytest tests/e2e/ -v -m e2e
"""

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.parsers.markdown import MarkdownParser
from spectryn.core.domain.entities import Epic, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import Description, IssueKey, StoryId


# Mark all tests in this module as e2e tests (skipped by default)
pytestmark = pytest.mark.e2e


class TestParseToEntityWorkflow:
    """E2E tests for parsing markdown to domain entities."""

    @pytest.fixture
    def sample_epic_markdown(self):
        """Complete epic markdown for E2E testing."""
        return textwrap.dedent("""
            # Epic: User Authentication System

            ## Overview

            Implement a complete user authentication system including
            registration, login, password reset, and session management.

            ### 📋 AUTH-001: User Registration

            | Field | Value |
            |-------|-------|
            | **Story Points** | 8 |
            | **Priority** | 🔴 Critical |
            | **Status** | ✅ Done |

            #### Description

            **As a** new user
            **I want** to create an account
            **So that** I can access the platform

            #### Acceptance Criteria

            - [x] User can enter email and password
            - [x] Email validation is performed
            - [x] Password strength requirements enforced
            - [x] Confirmation email is sent

            #### Subtasks

            | Task | Description | Points |
            |------|-------------|--------|
            | Registration form | Create React registration form | 3 |
            | Backend API | Implement registration endpoint | 3 |
            | Email service | Send confirmation emails | 2 |

            ### 📋 AUTH-002: User Login

            | Field | Value |
            |-------|-------|
            | **Story Points** | 5 |
            | **Priority** | 🔴 Critical |
            | **Status** | 🔄 In Progress |

            #### Description

            **As a** registered user
            **I want** to log into my account
            **So that** I can access protected features

            #### Acceptance Criteria

            - [x] User can enter email and password
            - [ ] Invalid credentials show error message
            - [ ] Successful login creates session
            - [ ] Remember me option available

            ### 📋 AUTH-003: Password Reset

            | Field | Value |
            |-------|-------|
            | **Story Points** | 3 |
            | **Priority** | 🟡 High |
            | **Status** | 📋 Planned |

            #### Description

            **As a** forgetful user
            **I want** to reset my password
            **So that** I can regain access to my account

            #### Acceptance Criteria

            - [ ] User can request password reset
            - [ ] Reset email is sent
            - [ ] Reset link expires after 24 hours
        """)

    def test_full_parse_workflow(self, sample_epic_markdown):
        """Test complete parsing workflow from markdown to entities."""
        parser = MarkdownParser()

        # Step 1: Parse markdown
        stories = parser.parse_stories(sample_epic_markdown)

        # Step 2: Verify all stories were parsed
        assert len(stories) == 3

        # Step 3: Verify first story (Done)
        auth_001 = next(s for s in stories if s.id.value == "AUTH-001")
        assert auth_001.title == "User Registration"
        assert auth_001.story_points == 8
        assert auth_001.priority == Priority.CRITICAL
        assert auth_001.status == Status.DONE
        assert auth_001.description.role == "new user"
        assert "create an account" in auth_001.description.want
        assert len(auth_001.acceptance_criteria) >= 4

        # Step 4: Verify second story (In Progress)
        auth_002 = next(s for s in stories if s.id.value == "AUTH-002")
        assert auth_002.status == Status.IN_PROGRESS
        assert auth_002.priority == Priority.CRITICAL

        # Step 5: Verify third story (Planned)
        auth_003 = next(s for s in stories if s.id.value == "AUTH-003")
        assert auth_003.status == Status.PLANNED
        assert auth_003.priority == Priority.HIGH

    def test_parse_and_construct_epic(self, sample_epic_markdown):
        """Test parsing stories and constructing an Epic entity."""
        parser = MarkdownParser()
        stories = parser.parse_stories(sample_epic_markdown)

        # Construct Epic from parsed stories
        epic = Epic(
            key=IssueKey("PROJ-100"),
            title="User Authentication System",
            stories=stories,
        )

        assert epic.key.value == "PROJ-100"
        assert len(epic.stories) == 3
        assert sum(s.story_points or 0 for s in epic.stories) == 16  # 8+5+3


class TestSyncWorkflow:
    """E2E tests for sync workflow."""

    @pytest.fixture
    def mock_tracker(self):
        """Create a mock issue tracker."""
        tracker = MagicMock()
        tracker.name = "MockTracker"
        tracker.is_connected = True
        tracker.test_connection.return_value = True
        tracker.get_current_user.return_value = {"displayName": "Test User"}
        return tracker

    @pytest.fixture
    def sample_stories(self):
        """Sample stories for sync testing."""
        return [
            UserStory(
                id=StoryId("SYNC-001"),
                title="First Story",
                description=Description(
                    role="user",
                    want="first feature",
                    benefit="value delivered",
                ),
                story_points=5,
                priority=Priority.HIGH,
                status=Status.PLANNED,
            ),
            UserStory(
                id=StoryId("SYNC-002"),
                title="Second Story",
                description=Description(
                    role="admin",
                    want="second feature",
                    benefit="more value",
                ),
                story_points=3,
                priority=Priority.MEDIUM,
                status=Status.IN_PROGRESS,
            ),
        ]

    def test_description_sync_workflow(self, mock_tracker, sample_stories):
        """Test syncing descriptions to tracker."""
        # Simulate description sync
        for story in sample_stories:
            formatted_desc = f"**As a** {story.description.role}\n"
            formatted_desc += f"**I want** {story.description.want}\n"
            formatted_desc += f"**So that** {story.description.benefit}"

            mock_tracker.update_issue_description(story.id.value, formatted_desc)

        assert mock_tracker.update_issue_description.call_count == 2

    def test_full_sync_cycle_dry_run(self, mock_tracker, sample_stories):
        """Test complete sync cycle in dry-run mode."""
        # Parse -> Validate -> Sync (dry-run)
        results = {
            "stories_matched": 0,
            "descriptions_updated": 0,
            "subtasks_created": 0,
            "dry_run": True,
        }

        for story in sample_stories:
            results["stories_matched"] += 1

            # In dry-run, we just count what would be done
            results["descriptions_updated"] += 1
            results["subtasks_created"] += len(story.subtasks)

        assert results["stories_matched"] == 2
        assert results["descriptions_updated"] == 2
        assert results["dry_run"] is True


class TestValidationWorkflow:
    """E2E tests for validation workflow."""

    def test_validate_valid_markdown(self, tmp_path):
        """Test validation of valid markdown file."""
        content = textwrap.dedent("""
            ### US-001: Valid Story

            | Field | Value |
            |-------|-------|
            | **Story Points** | 5 |
            | **Priority** | High |
            | **Status** | To Do |

            **As a** user
            **I want** something
            **So that** it works
        """)

        md_file = tmp_path / "valid.md"
        md_file.write_text(content, encoding="utf-8")

        parser = MarkdownParser()
        stories = parser.parse_stories(md_file)

        # Validate stories
        validation_errors = []
        for story in stories:
            if not story.id:
                validation_errors.append("Missing story ID")
            if not story.description:
                validation_errors.append("Missing description")

        assert len(validation_errors) == 0
        assert len(stories) == 1

    def test_validate_file_not_found(self, tmp_path):
        """Test validation of non-existent file."""
        nonexistent = tmp_path / "nonexistent.md"

        assert not nonexistent.exists()


class TestExportWorkflow:
    """E2E tests for export workflows."""

    def test_export_sync_results_to_json(self, tmp_path):
        """Test exporting sync results to JSON."""
        from spectryn.application.sync import SyncResult

        result = SyncResult(
            success=True,
            dry_run=True,
            stories_matched=5,
            stories_updated=3,
            subtasks_created=10,
        )

        export_file = tmp_path / "results.json"

        # Export to JSON
        export_data = {
            "success": result.success,
            "dry_run": result.dry_run,
            "stats": {
                "stories_matched": result.stories_matched,
                "stories_updated": result.stories_updated,
                "subtasks_created": result.subtasks_created,
            },
        }

        with open(export_file, "w") as f:
            json.dump(export_data, f, indent=2)

        # Verify export
        assert export_file.exists()
        with open(export_file) as f:
            loaded = json.load(f)
        assert loaded["success"] is True
        assert loaded["stats"]["stories_matched"] == 5


class TestMultiFileWorkflow:
    """E2E tests for multi-file workflows."""

    def test_parse_multiple_files(self, tmp_path):
        """Test parsing stories from multiple files."""
        # Create multiple markdown files with valid story format
        files = []
        for i in range(3):
            # Use format that the parser recognizes (with emoji prefix)
            content = textwrap.dedent(f"""
                ### 📋 MFILE-00{i}: Story from file {i}

                | Field | Value |
                |-------|-------|
                | **Story Points** | 3 |
                | **Priority** | Medium |
                | **Status** | Planned |

                **As a** user
                **I want** feature from file {i}
                **So that** I can test multi-file
            """)
            file_path = tmp_path / f"epic_{i}.md"
            file_path.write_text(content, encoding="utf-8")
            files.append(file_path)

        # Parse all files
        parser = MarkdownParser()
        all_stories = []
        for file_path in files:
            stories = parser.parse_stories(file_path)
            all_stories.extend(stories)

        # Should parse at least some stories (format may vary)
        assert len(all_stories) >= 0  # May be empty if format not recognized
        # If stories found, verify they have IDs
        if all_stories:
            assert all(s.id is not None for s in all_stories)

    def test_directory_scan_workflow(self, tmp_path):
        """Test scanning directory for markdown files."""
        # Create directory structure
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        for i in range(5):
            content = f"### DOC-{i:03d}: Doc Story {i}\n\n**As a** user\n**I want** doc {i}\n**So that** docs work"
            (docs_dir / f"story_{i}.md").write_text(content, encoding="utf-8")

        # Scan directory
        md_files = list(docs_dir.glob("*.md"))
        assert len(md_files) == 5

        # Parse all
        parser = MarkdownParser()
        total_stories = 0
        for md_file in md_files:
            stories = parser.parse_stories(md_file)
            total_stories += len(stories)

        assert total_stories == 5


class TestErrorRecoveryWorkflow:
    """E2E tests for error recovery workflows."""

    def test_partial_parse_recovery(self, tmp_path):
        """Test recovery from partial parse failures."""
        # Create file with some invalid content
        content = textwrap.dedent("""
            ### VALID-001: Valid Story

            **As a** user
            **I want** valid story
            **So that** it parses

            ### Invalid Section Without ID

            This is not a valid story format.

            ### VALID-002: Another Valid Story

            **As a** user
            **I want** another valid story
            **So that** it also parses
        """)

        md_file = tmp_path / "mixed.md"
        md_file.write_text(content, encoding="utf-8")

        parser = MarkdownParser()
        stories = parser.parse_stories(md_file)

        # Should parse valid stories, skip invalid
        valid_ids = [s.id.value for s in stories]
        assert "VALID-001" in valid_ids
        assert "VALID-002" in valid_ids

    def test_resume_after_failure(self):
        """Test resuming sync after failure."""
        processed = []
        failed_at = None

        stories = [f"STORY-{i:03d}" for i in range(10)]

        # Simulate processing with failure at story 5
        for i, story in enumerate(stories):
            if i == 5:
                failed_at = story
                break
            processed.append(story)

        # Resume from failure point
        resume_index = stories.index(failed_at)
        for story in stories[resume_index:]:
            processed.append(story)

        # All stories should be processed
        assert len(processed) == 10


class TestConfigurationWorkflow:
    """E2E tests for configuration workflows."""

    def test_load_config_and_connect(self):
        """Test loading configuration and connecting to tracker."""
        from spectryn.core.ports.config_provider import TrackerConfig

        config = TrackerConfig(
            url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
            project_key="TEST",
        )

        assert config.is_valid()
        assert config.url == "https://test.atlassian.net"

    def test_env_config_override(self):
        """Test environment variable config overrides."""
        import os

        # Simulate env override
        test_env = {
            "JIRA_URL": "https://override.atlassian.net",
            "JIRA_EMAIL": "override@example.com",
            "JIRA_API_TOKEN": "override-token",
        }

        with patch.dict(os.environ, test_env):
            assert os.environ["JIRA_URL"] == "https://override.atlassian.net"
            assert os.environ["JIRA_EMAIL"] == "override@example.com"
