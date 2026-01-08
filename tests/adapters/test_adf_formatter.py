"""Tests for ADF formatter adapter."""

from spectryn.core.domain import CommitRef


class TestADFFormatter:
    """Tests for ADFFormatter."""

    def test_format_text_plain(self, adf_formatter):
        """Test formatting plain text."""
        result = adf_formatter.format_text("Hello world")

        assert result["type"] == "doc"
        assert result["version"] == 1
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "paragraph"

    def test_format_text_with_bold(self, adf_formatter):
        """Test formatting text with bold."""
        result = adf_formatter.format_text("This is **bold** text")

        para = result["content"][0]
        content = para["content"]

        # Should have: "This is ", bold "bold", " text"
        assert len(content) >= 3

        # Find the bold text
        bold_found = False
        for node in content:
            if node.get("text") == "bold":
                marks = node.get("marks", [])
                if any(m["type"] == "strong" for m in marks):
                    bold_found = True

        assert bold_found

    def test_format_text_with_code(self, adf_formatter):
        """Test formatting text with inline code."""
        result = adf_formatter.format_text("Use `code` here")

        para = result["content"][0]
        content = para["content"]

        code_found = False
        for node in content:
            if node.get("text") == "code":
                marks = node.get("marks", [])
                if any(m["type"] == "code" for m in marks):
                    code_found = True

        assert code_found

    def test_format_heading(self, adf_formatter):
        """Test heading formatting."""
        result = adf_formatter.format_text("## Heading 2")

        heading = result["content"][0]
        assert heading["type"] == "heading"
        assert heading["attrs"]["level"] == 2

    def test_format_task_list(self, adf_formatter):
        """Test task list formatting."""
        result = adf_formatter.format_text("- [ ] Todo\n- [x] Done")

        task_list = result["content"][0]
        assert task_list["type"] == "taskList"

        items = task_list["content"]
        assert len(items) == 2

        assert items[0]["attrs"]["state"] == "TODO"
        assert items[1]["attrs"]["state"] == "DONE"

    def test_format_bullet_list(self, adf_formatter):
        """Test bullet list formatting."""
        result = adf_formatter.format_text("* Item 1\n* Item 2")

        bullet_list = result["content"][0]
        assert bullet_list["type"] == "bulletList"
        assert len(bullet_list["content"]) == 2

    def test_format_commits_table(self, adf_formatter):
        """Test commits table formatting."""
        commits = [
            CommitRef(hash="abc1234567", message="First commit"),
            CommitRef(hash="def7890123", message="Second commit"),
        ]

        result = adf_formatter.format_commits_table(commits)

        assert result["type"] == "doc"

        # Should have heading and table
        content = result["content"]

        has_heading = any(n["type"] == "heading" for n in content)
        has_table = any(n["type"] == "table" for n in content)

        assert has_heading
        assert has_table

        # Check table has header row + data rows
        table = next(n for n in content if n["type"] == "table")
        rows = table["content"]

        assert len(rows) == 3  # 1 header + 2 data rows

    def test_format_list_helper(self, adf_formatter):
        """Test format_list helper."""
        result = adf_formatter.format_list(["Item 1", "Item 2"])

        list_node = result["content"][0]
        assert list_node["type"] == "bulletList"

    def test_format_task_list_helper(self, adf_formatter):
        """Test format_task_list helper."""
        result = adf_formatter.format_task_list(
            [
                ("Todo item", False),
                ("Done item", True),
            ]
        )

        task_list = result["content"][0]
        assert task_list["type"] == "taskList"

        items = task_list["content"]
        assert items[0]["attrs"]["state"] == "TODO"
        assert items[1]["attrs"]["state"] == "DONE"

    def test_empty_text(self, adf_formatter):
        """Test formatting empty text returns valid ADF."""
        result = adf_formatter.format_text("")

        assert result["type"] == "doc"
        assert result["version"] == 1
        assert len(result["content"]) > 0
