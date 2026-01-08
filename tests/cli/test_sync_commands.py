"""
Tests for CLI sync command handlers.

Tests for:
- run_sync_links: Cross-project link syncing
- run_multi_epic: Multi-epic sync mode
- run_parallel_files: Parallel file processing
- run_multi_tracker_sync: Multi-tracker sync
"""

from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, Mock, patch

import pytest

from spectryn.cli.commands.sync import (
    _create_tracker_for_multi_sync,
    run_multi_epic,
    run_multi_tracker_sync,
    run_parallel_files,
    run_sync,
    run_sync_links,
)
from spectryn.cli.exit_codes import ExitCode


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_args():
    """Create mock CLI arguments."""
    args = Mock()
    args.input = "test.md"
    args.epic = "TEST-123"
    args.execute = False
    args.verbose = False
    args.quiet = False
    args.no_color = True
    args.config = None
    args.log_format = "text"
    # Multi-epic specific
    args.list_epics = False
    args.epic_filter = None
    args.stop_on_error = False
    # Parallel files specific
    args.input_files = None
    args.input_dir = None
    args.workers = 4
    args.file_timeout = 600.0
    args.fail_fast = False
    args.skip_empty = True
    # Multi-tracker specific
    args.trackers = []
    args.primary_tracker = None
    # Attachment specific
    args.attachment_mode = "upload"
    # Sync links specific
    args.analyze_links = False
    return args


@pytest.fixture
def sample_markdown_file(tmp_path):
    """Create a sample markdown file for testing."""
    md_content = dedent("""
        # Test Epic

        ## User Stories

        ### US-001: First Story

        | Field | Value |
        |-------|-------|
        | **Story Points** | 5 |
        | **Priority** | 🟡 High |
        | **Status** | ✅ Done |

        #### Description

        **As a** user
        **I want** a feature
        **So that** I benefit

        #### Links

        - Blocks: OTHER-100
        - Related: PROJ-200

        ---

        ### US-002: Second Story

        | Field | Value |
        |-------|-------|
        | **Story Points** | 3 |

        #### Description

        **As a** developer
        **I want** to implement
        **So that** it works
    """)
    md_file = tmp_path / "test.md"
    md_file.write_text(md_content, encoding="utf-8")
    return md_file


@pytest.fixture
def multi_epic_markdown_file(tmp_path):
    """Create a markdown file with multiple epics."""
    md_content = dedent("""
        # Project Epics

        ## Epic: PROJ-100 - First Epic

        ### US-001: Story in First Epic

        | Field | Value |
        |-------|-------|
        | **Story Points** | 5 |

        #### Description

        **As a** user
        **I want** feature A
        **So that** I benefit

        ---

        ## Epic: PROJ-200 - Second Epic

        ### US-002: Story in Second Epic

        | Field | Value |
        |-------|-------|
        | **Story Points** | 3 |

        #### Description

        **As a** developer
        **I want** feature B
        **So that** it works
    """)
    md_file = tmp_path / "multi_epic.md"
    md_file.write_text(md_content)
    return md_file


# =============================================================================
# run_sync tests
# =============================================================================


class TestRunSync:
    """Tests for run_sync function."""

    def test_run_sync_delegates_to_app(self, console, mock_args):
        """Test that run_sync delegates to app.run_sync."""
        with patch("spectryn.cli.app.run_sync") as mock_run_sync:
            mock_run_sync.return_value = ExitCode.SUCCESS

            result = run_sync(console, mock_args)

            mock_run_sync.assert_called_once_with(console, mock_args)
            assert result == ExitCode.SUCCESS


# =============================================================================
# run_sync_links tests
# =============================================================================


class TestRunSyncLinks:
    """Tests for run_sync_links function."""

    def test_file_not_found(self, mock_args):
        """Test handling of missing markdown file."""
        mock_args.input = "/nonexistent/file.md"

        result = run_sync_links(mock_args)

        assert result == ExitCode.FILE_NOT_FOUND

    def test_config_validation_errors(self, mock_args, sample_markdown_file):
        """Test handling of configuration validation errors."""
        mock_args.input = str(sample_markdown_file)

        with patch("spectryn.adapters.EnvironmentConfigProvider") as mock_config_provider:
            mock_provider_instance = Mock()
            mock_provider_instance.validate.return_value = ["Missing JIRA_URL"]
            mock_config_provider.return_value = mock_provider_instance

            result = run_sync_links(mock_args)

            assert result == ExitCode.CONFIG_ERROR

    def test_connection_error(self, mock_args, sample_markdown_file):
        """Test handling of connection failures."""
        mock_args.input = str(sample_markdown_file)

        with patch("spectryn.adapters.EnvironmentConfigProvider") as mock_config_provider:
            with patch("spectryn.adapters.JiraAdapter") as mock_jira_adapter:
                # Config is valid
                mock_provider_instance = Mock()
                mock_provider_instance.validate.return_value = []
                mock_config = Mock()
                mock_config.tracker = Mock(url="https://test.atlassian.net")
                mock_config.sync = Mock()
                mock_provider_instance.load.return_value = mock_config
                mock_config_provider.return_value = mock_provider_instance

                # Connection fails
                mock_tracker = Mock()
                mock_tracker.test_connection.return_value = False
                mock_jira_adapter.return_value = mock_tracker

                result = run_sync_links(mock_args)

                assert result == ExitCode.CONNECTION_ERROR

    def test_no_links_found(self, mock_args, sample_markdown_file):
        """Test handling when no links are found in markdown."""
        mock_args.input = str(sample_markdown_file)

        with patch("spectryn.adapters.EnvironmentConfigProvider") as mock_config_provider:
            with patch("spectryn.adapters.JiraAdapter") as mock_jira_adapter:
                with patch("spectryn.adapters.parsers.MarkdownParser") as mock_parser:
                    # Setup valid config
                    mock_provider_instance = Mock()
                    mock_provider_instance.validate.return_value = []
                    mock_config = Mock()
                    mock_config.tracker = Mock(url="https://test.atlassian.net")
                    mock_config.sync = Mock()
                    mock_provider_instance.load.return_value = mock_config
                    mock_config_provider.return_value = mock_provider_instance

                    # Setup tracker
                    mock_tracker = Mock()
                    mock_tracker.test_connection.return_value = True
                    mock_tracker.get_current_user.return_value = {"displayName": "Test User"}
                    mock_jira_adapter.return_value = mock_tracker

                    # Setup parser - return stories without links
                    mock_parser_instance = Mock()
                    mock_story = Mock()
                    mock_story.links = []  # No links
                    mock_parser_instance.parse_stories.return_value = [mock_story]
                    mock_parser.return_value = mock_parser_instance

                    result = run_sync_links(mock_args)

                    assert result == ExitCode.SUCCESS


# =============================================================================
# run_multi_epic tests
# =============================================================================


class TestRunMultiEpic:
    """Tests for run_multi_epic function."""

    def test_file_not_found(self, mock_args):
        """Test handling of missing markdown file."""
        mock_args.input = "/nonexistent/file.md"

        result = run_multi_epic(mock_args)

        assert result == ExitCode.FILE_NOT_FOUND

    def test_list_epics_mode(self, mock_args, multi_epic_markdown_file):
        """Test list-only mode to show epics."""
        mock_args.input = str(multi_epic_markdown_file)
        mock_args.list_epics = True

        with patch("spectryn.adapters.parsers.MarkdownParser") as mock_parser:
            # Setup parser
            mock_parser_instance = Mock()
            mock_epic1 = Mock(key="PROJ-100", title="First Epic", stories=[Mock()])
            mock_epic2 = Mock(key="PROJ-200", title="Second Epic", stories=[Mock(), Mock()])
            mock_parser_instance.parse_epics.return_value = [mock_epic1, mock_epic2]
            mock_parser.return_value = mock_parser_instance

            result = run_multi_epic(mock_args)

            assert result == ExitCode.SUCCESS
            mock_parser_instance.parse_epics.assert_called_once()

    def test_config_validation_errors(self, mock_args, multi_epic_markdown_file):
        """Test handling of configuration validation errors."""
        mock_args.input = str(multi_epic_markdown_file)
        mock_args.list_epics = False

        with patch("spectryn.adapters.EnvironmentConfigProvider") as mock_config_provider:
            mock_provider_instance = Mock()
            mock_provider_instance.validate.return_value = ["Missing JIRA_URL"]
            mock_config_provider.return_value = mock_provider_instance

            result = run_multi_epic(mock_args)

            assert result == ExitCode.CONFIG_ERROR

    def test_not_multi_epic_file(self, mock_args, sample_markdown_file):
        """Test handling when file doesn't contain multiple epics."""
        mock_args.input = str(sample_markdown_file)
        mock_args.list_epics = False

        with patch("spectryn.adapters.EnvironmentConfigProvider") as mock_config_provider:
            with patch("spectryn.adapters.JiraAdapter") as mock_jira_adapter:
                with patch("spectryn.adapters.parsers.MarkdownParser") as mock_parser:
                    # Setup valid config
                    mock_provider_instance = Mock()
                    mock_provider_instance.validate.return_value = []
                    mock_config = Mock()
                    mock_config.tracker = Mock(url="https://test.atlassian.net")
                    mock_config.sync = Mock()
                    mock_provider_instance.load.return_value = mock_config
                    mock_config_provider.return_value = mock_provider_instance

                    # Setup tracker
                    mock_tracker = Mock()
                    mock_tracker.test_connection.return_value = True
                    mock_tracker.get_current_user.return_value = {"displayName": "Test User"}
                    mock_jira_adapter.return_value = mock_tracker

                    # Setup parser - not multi-epic
                    mock_parser_instance = Mock()
                    mock_parser_instance.is_multi_epic.return_value = False
                    mock_parser.return_value = mock_parser_instance

                    result = run_multi_epic(mock_args)

                    assert result == ExitCode.VALIDATION_ERROR

    def test_connection_error(self, mock_args, multi_epic_markdown_file):
        """Test handling of connection failures."""
        mock_args.input = str(multi_epic_markdown_file)
        mock_args.list_epics = False

        with patch("spectryn.adapters.EnvironmentConfigProvider") as mock_config_provider:
            with patch("spectryn.adapters.JiraAdapter") as mock_jira_adapter:
                # Setup valid config
                mock_provider_instance = Mock()
                mock_provider_instance.validate.return_value = []
                mock_config = Mock()
                mock_config.tracker = Mock(url="https://test.atlassian.net")
                mock_config.sync = Mock()
                mock_provider_instance.load.return_value = mock_config
                mock_config_provider.return_value = mock_provider_instance

                # Connection fails
                mock_tracker = Mock()
                mock_tracker.test_connection.return_value = False
                mock_jira_adapter.return_value = mock_tracker

                result = run_multi_epic(mock_args)

                assert result == ExitCode.CONNECTION_ERROR


# =============================================================================
# run_parallel_files tests
# =============================================================================


class TestRunParallelFiles:
    """Tests for run_parallel_files function."""

    def test_no_input_files(self, mock_args):
        """Test handling when no input files specified."""
        mock_args.input = None
        mock_args.input_files = None
        mock_args.input_dir = None

        result = run_parallel_files(mock_args)

        assert result == ExitCode.FILE_NOT_FOUND

    def test_config_validation_errors(self, mock_args, sample_markdown_file):
        """Test handling of configuration validation errors."""
        mock_args.input = str(sample_markdown_file)
        mock_args.input_files = None
        mock_args.input_dir = None

        with patch("spectryn.adapters.EnvironmentConfigProvider") as mock_config_provider:
            mock_provider_instance = Mock()
            mock_provider_instance.validate.return_value = ["Missing JIRA_URL"]
            mock_config_provider.return_value = mock_provider_instance

            result = run_parallel_files(mock_args)

            assert result == ExitCode.CONFIG_ERROR

    def test_connection_error(self, mock_args, sample_markdown_file):
        """Test handling of connection failures."""
        mock_args.input = str(sample_markdown_file)
        mock_args.input_files = None
        mock_args.input_dir = None
        mock_args.epic = "TEST-123"

        with patch("spectryn.adapters.EnvironmentConfigProvider") as mock_config_provider:
            with patch("spectryn.adapters.trackers.JiraAdapter") as mock_jira_adapter:
                # Config is valid
                mock_provider_instance = Mock()
                mock_provider_instance.validate.return_value = []
                mock_config = Mock()
                mock_config.tracker = Mock(url="https://test.atlassian.net", project_key="TEST")
                mock_config.sync = Mock()
                mock_provider_instance.load.return_value = mock_config
                mock_config_provider.return_value = mock_provider_instance

                # Connection fails
                mock_tracker = Mock()
                mock_tracker.test_connection.return_value = False
                mock_jira_adapter.return_value = mock_tracker

                result = run_parallel_files(mock_args)

                assert result == ExitCode.CONNECTION_ERROR


# =============================================================================
# run_multi_tracker_sync tests
# =============================================================================


class TestRunMultiTrackerSync:
    """Tests for run_multi_tracker_sync function."""

    def test_file_not_found(self, mock_args):
        """Test handling of missing markdown file."""
        mock_args.input = "/nonexistent/file.md"
        mock_args.trackers = ["jira:TEST-123"]

        result = run_multi_tracker_sync(mock_args)

        assert result == ExitCode.FILE_NOT_FOUND

    def test_no_tracker_targets(self, mock_args, sample_markdown_file):
        """Test handling when no tracker targets specified."""
        mock_args.input = str(sample_markdown_file)
        mock_args.trackers = []
        mock_args.primary_tracker = None

        result = run_multi_tracker_sync(mock_args)

        assert result == ExitCode.CONFIG_ERROR

    def test_invalid_tracker_spec_format(self, mock_args, sample_markdown_file):
        """Test handling of invalid tracker specification format."""
        mock_args.input = str(sample_markdown_file)
        mock_args.trackers = ["invalid-no-colon"]  # Missing colon separator
        mock_args.primary_tracker = None

        with patch("spectryn.adapters.EnvironmentConfigProvider") as mock_config_provider:
            with patch(
                "spectryn.application.sync.multi_tracker.MultiTrackerSyncOrchestrator"
            ) as mock_orchestrator:
                # Config loads
                mock_provider_instance = Mock()
                mock_config = Mock()
                mock_config.sync = Mock()
                mock_provider_instance.load.return_value = mock_config
                mock_config_provider.return_value = mock_provider_instance

                # Orchestrator has no targets
                mock_orch_instance = Mock()
                mock_orch_instance.targets = []
                mock_orchestrator.return_value = mock_orch_instance

                result = run_multi_tracker_sync(mock_args)

                assert result == ExitCode.CONFIG_ERROR


# =============================================================================
# _create_tracker_for_multi_sync tests
# =============================================================================


class TestCreateTrackerForMultiSync:
    """Tests for _create_tracker_for_multi_sync helper function."""

    def test_create_jira_tracker(self):
        """Test creating a Jira tracker adapter."""
        mock_config = Mock()
        mock_config.tracker = Mock()
        mock_config_provider = Mock()

        with patch("spectryn.adapters.ADFFormatter"):
            with patch("spectryn.adapters.JiraAdapter") as mock_jira_adapter:
                mock_tracker = Mock()
                mock_jira_adapter.return_value = mock_tracker

                result = _create_tracker_for_multi_sync(
                    "jira", mock_config, mock_config_provider, True
                )

                assert result is mock_tracker
                mock_jira_adapter.assert_called_once()

    @patch.dict(
        "os.environ",
        {"GITHUB_TOKEN": "test-token", "GITHUB_OWNER": "owner", "GITHUB_REPO": "repo"},
    )
    def test_create_github_tracker(self):
        """Test creating a GitHub tracker adapter."""
        mock_config = Mock()
        mock_config_provider = Mock()

        with patch("spectryn.adapters.github.GitHubAdapter") as mock_github_adapter:
            mock_tracker = Mock()
            mock_github_adapter.return_value = mock_tracker

            result = _create_tracker_for_multi_sync(
                "github", mock_config, mock_config_provider, True
            )

            assert result is mock_tracker

    @patch.dict(
        "os.environ",
        {"GITLAB_TOKEN": "test-token", "GITLAB_PROJECT_ID": "123"},
    )
    def test_create_gitlab_tracker(self):
        """Test creating a GitLab tracker adapter."""
        mock_config = Mock()
        mock_config_provider = Mock()

        with patch("spectryn.adapters.gitlab.GitLabAdapter") as mock_gitlab_adapter:
            mock_tracker = Mock()
            mock_gitlab_adapter.return_value = mock_tracker

            result = _create_tracker_for_multi_sync(
                "gitlab", mock_config, mock_config_provider, True
            )

            assert result is mock_tracker

    @patch.dict(
        "os.environ",
        {"LINEAR_API_KEY": "test-key", "LINEAR_TEAM_KEY": "TEST"},
    )
    def test_create_linear_tracker(self):
        """Test creating a Linear tracker adapter."""
        mock_config = Mock()
        mock_config_provider = Mock()

        with patch("spectryn.adapters.linear.LinearAdapter") as mock_linear_adapter:
            mock_tracker = Mock()
            mock_linear_adapter.return_value = mock_tracker

            result = _create_tracker_for_multi_sync(
                "linear", mock_config, mock_config_provider, True
            )

            assert result is mock_tracker

    def test_unknown_tracker_type(self):
        """Test handling of unknown tracker type."""
        mock_config = Mock()
        mock_config_provider = Mock()

        result = _create_tracker_for_multi_sync("unknown", mock_config, mock_config_provider, True)

        assert result is None
