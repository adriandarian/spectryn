"""
Tests for the interactive CLI mode.
"""

from unittest.mock import Mock, patch

import pytest

from spectryn.cli.interactive import (
    Action,
    InteractiveSession,
    PendingOperation,
    PhasePreview,
    run_interactive,
)
from spectryn.cli.output import Console


class TestPendingOperation:
    """Tests for PendingOperation dataclass."""

    def test_create_operation(self):
        """Test creating a pending operation."""
        op = PendingOperation(
            operation_type="update_description",
            issue_key="PROJ-123",
            story_id="US-001",
            description="Update description",
        )

        assert op.operation_type == "update_description"
        assert op.issue_key == "PROJ-123"
        assert op.story_id == "US-001"
        assert op.selected is True  # Default

    def test_toggle_operation(self):
        """Test toggling an operation's selection state."""
        op = PendingOperation(
            operation_type="update_description",
            issue_key="PROJ-123",
            story_id="US-001",
            description="Update description",
        )

        assert op.selected is True
        op.toggle()
        assert op.selected is False
        op.toggle()
        assert op.selected is True

    def test_operation_with_details(self):
        """Test operation with optional details."""
        op = PendingOperation(
            operation_type="sync_subtask",
            issue_key="PROJ-123",
            story_id="US-001",
            description="Sync subtask: Implement feature",
            details="3 SP",
        )

        assert op.details == "3 SP"


class TestPhasePreview:
    """Tests for PhasePreview dataclass."""

    def test_create_phase(self):
        """Test creating a phase preview."""
        phase = PhasePreview(
            name="Descriptions",
            description="Update story descriptions",
        )

        assert phase.name == "Descriptions"
        assert phase.enabled is True
        assert phase.operations == []
        assert phase.selected_count == 0
        assert phase.total_count == 0

    def test_phase_with_operations(self):
        """Test phase with operations."""
        phase = PhasePreview(
            name="Descriptions",
            description="Update story descriptions",
        )

        phase.operations = [
            PendingOperation("update", "PROJ-1", "US-1", "Op 1"),
            PendingOperation("update", "PROJ-2", "US-2", "Op 2"),
            PendingOperation("update", "PROJ-3", "US-3", "Op 3", selected=False),
        ]

        assert phase.total_count == 3
        assert phase.selected_count == 2

    def test_select_all(self):
        """Test selecting all operations."""
        phase = PhasePreview("Test", "Test phase")
        phase.operations = [
            PendingOperation("update", "PROJ-1", "US-1", "Op 1", selected=False),
            PendingOperation("update", "PROJ-2", "US-2", "Op 2", selected=False),
        ]

        assert phase.selected_count == 0
        phase.select_all()
        assert phase.selected_count == 2

    def test_deselect_all(self):
        """Test deselecting all operations."""
        phase = PhasePreview("Test", "Test phase")
        phase.operations = [
            PendingOperation("update", "PROJ-1", "US-1", "Op 1"),
            PendingOperation("update", "PROJ-2", "US-2", "Op 2"),
        ]

        assert phase.selected_count == 2
        phase.deselect_all()
        assert phase.selected_count == 0


class TestInteractiveSession:
    """Tests for InteractiveSession class."""

    @pytest.fixture
    def console(self):
        """Create a console instance."""
        return Console(color=False, verbose=False)

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator."""
        orchestrator = Mock()
        orchestrator.config = Mock()
        orchestrator.config.dry_run = True
        orchestrator.config.sync_descriptions = True
        orchestrator.config.sync_subtasks = True
        orchestrator.config.sync_comments = True
        orchestrator.config.sync_statuses = True
        orchestrator._md_stories = []
        orchestrator._jira_issues = []
        orchestrator._matches = {}
        return orchestrator

    def test_create_session(self, console, mock_orchestrator):
        """Test creating an interactive session."""
        session = InteractiveSession(
            console=console,
            orchestrator=mock_orchestrator,
            markdown_path="/path/to/file.md",
            epic_key="PROJ-123",
        )

        assert session.markdown_path == "/path/to/file.md"
        assert session.epic_key == "PROJ-123"
        assert session.phases == []
        assert session._aborted is False

    def test_truncate_text(self, console, mock_orchestrator):
        """Test text truncation helper."""
        session = InteractiveSession(
            console=console,
            orchestrator=mock_orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        # Short text unchanged
        assert session._truncate("short", 10) == "short"

        # Long text truncated
        result = session._truncate("this is a very long text", 15)
        assert len(result) == 15
        assert result.endswith("...")

    def test_truncate_removes_newlines(self, console, mock_orchestrator):
        """Test that truncate removes newlines."""
        session = InteractiveSession(
            console=console,
            orchestrator=mock_orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        result = session._truncate("line1\nline2\nline3", 100)
        assert "\n" not in result
        assert result == "line1 line2 line3"

    @patch("builtins.input", return_value="y")
    def test_prompt_continue_yes(self, mock_input, console, mock_orchestrator):
        """Test continue prompt with 'y' response."""
        session = InteractiveSession(
            console=console,
            orchestrator=mock_orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        result = session._prompt_continue()
        assert result is True

    @patch("builtins.input", return_value="n")
    def test_prompt_continue_no(self, mock_input, console, mock_orchestrator):
        """Test continue prompt with 'n' response."""
        session = InteractiveSession(
            console=console,
            orchestrator=mock_orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        result = session._prompt_continue()
        assert result is False

    @patch("builtins.input", return_value="")
    def test_prompt_continue_default_yes(self, mock_input, console, mock_orchestrator):
        """Test continue prompt with empty response (default yes)."""
        session = InteractiveSession(
            console=console,
            orchestrator=mock_orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        result = session._prompt_continue(default=True)
        assert result is True

    @patch("builtins.input", return_value="")
    def test_prompt_continue_default_no(self, mock_input, console, mock_orchestrator):
        """Test continue prompt with empty response (default no)."""
        session = InteractiveSession(
            console=console,
            orchestrator=mock_orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        result = session._prompt_continue(default=False)
        assert result is False

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_prompt_continue_interrupt(self, mock_input, console, mock_orchestrator, capsys):
        """Test continue prompt handles keyboard interrupt."""
        session = InteractiveSession(
            console=console,
            orchestrator=mock_orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        result = session._prompt_continue()
        assert result is False

    @patch("builtins.input", return_value="")
    def test_prompt_phase_action_continue(self, mock_input, console, mock_orchestrator):
        """Test phase action prompt returns continue."""
        session = InteractiveSession(
            console=console,
            orchestrator=mock_orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        phase = PhasePreview("Test", "Test phase")
        result = session._prompt_phase_action(phase)
        assert result == Action.CONTINUE

    @patch("builtins.input", return_value="s")
    def test_prompt_phase_action_skip(self, mock_input, console, mock_orchestrator):
        """Test phase action prompt returns skip."""
        session = InteractiveSession(
            console=console,
            orchestrator=mock_orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        phase = PhasePreview("Test", "Test phase")
        result = session._prompt_phase_action(phase)
        assert result == Action.SKIP

    @patch("builtins.input", return_value="a")
    def test_prompt_phase_action_abort(self, mock_input, console, mock_orchestrator):
        """Test phase action prompt returns abort."""
        session = InteractiveSession(
            console=console,
            orchestrator=mock_orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        phase = PhasePreview("Test", "Test phase")
        result = session._prompt_phase_action(phase)
        assert result == Action.ABORT


class TestRunInteractive:
    """Tests for run_interactive function."""

    def test_run_interactive_aborted(self):
        """Test run_interactive when session is aborted."""
        console = Console(color=False)
        orchestrator = Mock()

        with patch.object(InteractiveSession, "run", return_value=False):
            result = run_interactive(
                console=console,
                orchestrator=orchestrator,
                markdown_path="test.md",
                epic_key="PROJ-123",
            )

        assert result is False

    def test_run_interactive_success(self):
        """Test run_interactive when session completes successfully."""
        console = Console(color=False)
        orchestrator = Mock()

        with patch.object(InteractiveSession, "run", return_value=True):
            result = run_interactive(
                console=console,
                orchestrator=orchestrator,
                markdown_path="test.md",
                epic_key="PROJ-123",
            )

        assert result is True


class TestInteractiveSessionPhases:
    """Tests for phase building in InteractiveSession."""

    @pytest.fixture
    def console(self):
        return Console(color=False)

    @pytest.fixture
    def mock_story(self):
        """Create a mock user story."""
        story = Mock()
        story.id = "US-001"
        story.title = "Test Story"
        story.description = "Test description"
        story.subtasks = []
        story.commits = []
        story.status = Mock()
        story.status.is_complete.return_value = False
        return story

    def test_build_description_phase(self, console, mock_story):
        """Test building description phase preview."""
        orchestrator = Mock()
        orchestrator.config = Mock()
        orchestrator.config.dry_run = True
        orchestrator.config.sync_descriptions = True
        orchestrator.config.sync_subtasks = False
        orchestrator.config.sync_comments = False
        orchestrator.config.sync_statuses = False
        orchestrator._md_stories = [mock_story]
        orchestrator._matches = {"US-001": "PROJ-123"}

        session = InteractiveSession(
            console=console,
            orchestrator=orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        session._build_phase_previews()

        assert len(session.phases) == 1
        assert session.phases[0].name == "Descriptions"
        assert session.phases[0].total_count == 1
        assert session.phases[0].operations[0].issue_key == "PROJ-123"

    def test_build_subtasks_phase(self, console, mock_story):
        """Test building subtasks phase preview."""
        subtask = Mock()
        subtask.name = "Implement feature"
        subtask.description = "Subtask description"
        subtask.story_points = 3
        mock_story.subtasks = [subtask]

        orchestrator = Mock()
        orchestrator.config = Mock()
        orchestrator.config.dry_run = True
        orchestrator.config.sync_descriptions = False
        orchestrator.config.sync_subtasks = True
        orchestrator.config.sync_comments = False
        orchestrator.config.sync_statuses = False
        orchestrator._md_stories = [mock_story]
        orchestrator._matches = {"US-001": "PROJ-123"}

        session = InteractiveSession(
            console=console,
            orchestrator=orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        session._build_phase_previews()

        assert len(session.phases) == 1
        assert session.phases[0].name == "Subtasks"
        assert session.phases[0].total_count == 1
        assert "Implement feature" in session.phases[0].operations[0].description

    def test_build_comments_phase(self, console, mock_story):
        """Test building comments phase preview."""
        commit = Mock()
        commit.sha = "abc123"
        mock_story.commits = [commit]

        orchestrator = Mock()
        orchestrator.config = Mock()
        orchestrator.config.dry_run = True
        orchestrator.config.sync_descriptions = False
        orchestrator.config.sync_subtasks = False
        orchestrator.config.sync_comments = True
        orchestrator.config.sync_statuses = False
        orchestrator._md_stories = [mock_story]
        orchestrator._matches = {"US-001": "PROJ-123"}

        session = InteractiveSession(
            console=console,
            orchestrator=orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        session._build_phase_previews()

        assert len(session.phases) == 1
        assert session.phases[0].name == "Comments"
        assert session.phases[0].total_count == 1

    def test_build_statuses_phase(self, console, mock_story):
        """Test building statuses phase preview for completed story."""
        mock_story.status.is_complete.return_value = True

        orchestrator = Mock()
        orchestrator.config = Mock()
        orchestrator.config.dry_run = True
        orchestrator.config.sync_descriptions = False
        orchestrator.config.sync_subtasks = False
        orchestrator.config.sync_comments = False
        orchestrator.config.sync_statuses = True
        orchestrator._md_stories = [mock_story]
        orchestrator._matches = {"US-001": "PROJ-123"}

        session = InteractiveSession(
            console=console,
            orchestrator=orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        session._build_phase_previews()

        assert len(session.phases) == 1
        assert session.phases[0].name == "Statuses"
        assert session.phases[0].total_count == 1

    def test_no_phases_for_disabled_sync(self, console, mock_story):
        """Test no phases are created when all sync options are disabled."""
        orchestrator = Mock()
        orchestrator.config = Mock()
        orchestrator.config.dry_run = True
        orchestrator.config.sync_descriptions = False
        orchestrator.config.sync_subtasks = False
        orchestrator.config.sync_comments = False
        orchestrator.config.sync_statuses = False
        orchestrator._md_stories = [mock_story]
        orchestrator._matches = {"US-001": "PROJ-123"}

        session = InteractiveSession(
            console=console,
            orchestrator=orchestrator,
            markdown_path="test.md",
            epic_key="PROJ-123",
        )

        session._build_phase_previews()

        assert len(session.phases) == 0
