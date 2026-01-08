"""
Confluence Adapter - Implements DocumentOutputPort for Confluence.

Publishes epics and stories as Confluence pages with proper formatting.
"""

import html
import logging

from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Status
from spectryn.core.domain.value_objects import Description
from spectryn.core.ports.document_output import (
    AuthenticationError,
    DocumentOutputPort,
    NotFoundError,
    PageData,
    PermissionError,
    SpaceData,
)

from .client import ConfluenceAPIError, ConfluenceClient


class ConfluenceAdapter(DocumentOutputPort):
    """
    Confluence adapter implementing DocumentOutputPort.

    Publishes epics and stories as Confluence pages with:
    - Structured content using Confluence storage format
    - Status/priority macros
    - Tables for subtasks
    - Links to Jira issues (if available)

    Page Structure:
    - Epic → Parent page with summary and links to stories
    - Story → Child page with full details
    """

    def __init__(self, client: ConfluenceClient) -> None:
        """
        Initialize the Confluence adapter.

        Args:
            client: Configured ConfluenceClient instance
        """
        self._client = client
        self.logger = logging.getLogger("ConfluenceAdapter")

    @property
    def name(self) -> str:
        return "Confluence"

    # -------------------------------------------------------------------------
    # Connection
    # -------------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to Confluence."""
        try:
            self._client.connect()
            # Verify connection by getting current user
            user = self._client.get_current_user()
            self.logger.info(f"Connected as {user.get('displayName', 'Unknown')}")
        except ConfluenceAPIError as e:
            if e.status_code == 401:
                raise AuthenticationError("Invalid credentials") from e
            raise

    def disconnect(self) -> None:
        """Disconnect from Confluence."""
        self._client.disconnect()

    # -------------------------------------------------------------------------
    # Space Operations
    # -------------------------------------------------------------------------

    def get_space(self, space_key: str) -> SpaceData:
        """Get space by key."""
        try:
            data = self._client.get_space(space_key)
            return self._map_space(data)
        except ConfluenceAPIError as e:
            if e.status_code == 404:
                raise NotFoundError(f"Space not found: {space_key}") from e
            raise

    def list_spaces(self) -> list[SpaceData]:
        """List all accessible spaces."""
        spaces = self._client.list_spaces()
        return [self._map_space(s) for s in spaces]

    def _map_space(self, data: dict) -> SpaceData:
        """Map API response to SpaceData."""
        return SpaceData(
            key=data.get("key", ""),
            name=data.get("name", ""),
            type=data.get("type", "global"),
            url=data.get("_links", {}).get("webui"),
        )

    # -------------------------------------------------------------------------
    # Page Operations
    # -------------------------------------------------------------------------

    def get_page(self, page_id: str) -> PageData:
        """Get page by ID."""
        try:
            data = self._client.get_content(
                page_id,
                expand=["body.storage", "version", "space", "metadata.labels"],
            )
            return self._map_page(data)
        except ConfluenceAPIError as e:
            if e.status_code == 404:
                raise NotFoundError(f"Page not found: {page_id}") from e
            if e.status_code == 403:
                raise PermissionError(f"Permission denied: {page_id}") from e
            raise

    def get_page_by_title(self, space_key: str, title: str) -> PageData | None:
        """Find page by title."""
        data = self._client.get_content_by_title(
            space_key,
            title,
            expand=["body.storage", "version", "metadata.labels"],
        )
        return self._map_page(data) if data else None

    def create_page(
        self,
        space_key: str,
        title: str,
        content: str,
        parent_id: str | None = None,
        labels: list[str] | None = None,
    ) -> PageData:
        """Create a new page."""
        try:
            data = self._client.create_content(
                space_key=space_key,
                title=title,
                body=content,
                parent_id=parent_id,
            )
            page = self._map_page(data)

            # Add labels if provided
            if labels:
                self._client.add_labels(page.id, labels)
                page.labels = labels

            self.logger.info(f"Created page: {title} ({page.id})")
            return page

        except ConfluenceAPIError as e:
            if e.status_code == 403:
                raise PermissionError(f"Cannot create page in space {space_key}") from e
            raise

    def update_page(
        self,
        page_id: str,
        title: str,
        content: str,
        version: int,
        labels: list[str] | None = None,
    ) -> PageData:
        """Update an existing page."""
        try:
            data = self._client.update_content(
                content_id=page_id,
                title=title,
                body=content,
                version=version,
            )
            page = self._map_page(data)

            # Update labels if provided
            if labels is not None:
                # Get current labels
                current = self._client.get_labels(page_id)
                current_names = {l["name"] for l in current}
                new_names = set(labels)

                # Remove old labels
                for label in current_names - new_names:
                    self._client.remove_label(page_id, label)

                # Add new labels
                to_add = list(new_names - current_names)
                if to_add:
                    self._client.add_labels(page_id, to_add)

                page.labels = labels

            self.logger.info(f"Updated page: {title} ({page_id})")
            return page

        except ConfluenceAPIError as e:
            if e.status_code == 404:
                raise NotFoundError(f"Page not found: {page_id}") from e
            if e.status_code == 409:
                raise PermissionError(f"Version conflict on page {page_id}") from e
            raise

    def delete_page(self, page_id: str) -> None:
        """Delete a page."""
        try:
            self._client.delete_content(page_id)
            self.logger.info(f"Deleted page: {page_id}")
        except ConfluenceAPIError as e:
            if e.status_code == 404:
                raise NotFoundError(f"Page not found: {page_id}") from e
            raise

    def _map_page(self, data: dict) -> PageData:
        """Map API response to PageData."""
        labels = []
        if "metadata" in data and "labels" in data["metadata"]:
            labels = [l["name"] for l in data["metadata"]["labels"].get("results", [])]

        content = ""
        if "body" in data and "storage" in data["body"]:
            content = data["body"]["storage"].get("value", "")

        return PageData(
            id=data.get("id", ""),
            title=data.get("title", ""),
            content=content,
            space_key=data.get("space", {}).get("key"),
            version=data.get("version", {}).get("number", 1),
            url=data.get("_links", {}).get("webui"),
            labels=labels,
        )

    # -------------------------------------------------------------------------
    # Epic/Story Publishing
    # -------------------------------------------------------------------------

    def publish_epic(
        self,
        epic: Epic,
        space_key: str,
        parent_id: str | None = None,
        update_existing: bool = True,
    ) -> PageData:
        """Publish an epic and its stories as pages."""
        # Create/update epic page
        epic_title = f"Epic: {epic.title}"
        epic_content = self.format_epic_content(epic)

        existing = self.get_page_by_title(space_key, epic_title)

        if existing and update_existing:
            epic_page = self.update_page(
                existing.id,
                epic_title,
                epic_content,
                existing.version,
                labels=["epic", "spectra"],
            )
        else:
            epic_page = self.create_page(
                space_key,
                epic_title,
                epic_content,
                parent_id=parent_id,
                labels=["epic", "spectra"],
            )

        # Create/update story pages as children
        for story in epic.stories:
            self.publish_story(
                story,
                space_key,
                parent_id=epic_page.id,
                update_existing=update_existing,
            )

        return epic_page

    def publish_story(
        self,
        story: UserStory,
        space_key: str,
        parent_id: str | None = None,
        update_existing: bool = True,
    ) -> PageData:
        """Publish a story as a page."""
        story_title = f"{story.id}: {story.title}"
        story_content = self.format_story_content(story)

        labels = ["story", "spectra", f"status-{story.status.name.lower()}"]

        existing = self.get_page_by_title(space_key, story_title)

        if existing and update_existing:
            return self.update_page(
                existing.id,
                story_title,
                story_content,
                existing.version,
                labels=labels,
            )
        return self.create_page(
            space_key,
            story_title,
            story_content,
            parent_id=parent_id,
            labels=labels,
        )

    # -------------------------------------------------------------------------
    # Content Formatting - Confluence Storage Format
    # -------------------------------------------------------------------------

    def format_epic_content(self, epic: Epic) -> str:
        """Format epic as Confluence storage format."""
        parts = []

        # Info panel with metadata
        parts.append(
            self._info_panel(
                f"<strong>Epic Key:</strong> {html.escape(str(epic.key))}<br/>"
                f"<strong>Stories:</strong> {len(epic.stories)}<br/>"
                f"<strong>Total Story Points:</strong> {sum(s.story_points for s in epic.stories)}"
            )
        )

        # Summary table of stories
        if epic.stories:
            parts.append("<h2>User Stories</h2>")
            parts.append(self._stories_table(epic.stories))

        # Story summaries
        for story in epic.stories:
            parts.append(f"<h3>{html.escape(str(story.id))}: {html.escape(story.title)}</h3>")

            if story.description:
                parts.append(self._format_description(story.description))

            parts.append(
                f"<p><strong>Story Points:</strong> {story.story_points} | "
                f"<strong>Priority:</strong> {story.priority.name} | "
                f"<strong>Status:</strong> {self._status_lozenge(story.status)}</p>"
            )

        return "\n".join(parts)

    def format_story_content(self, story: UserStory) -> str:
        """Format story as Confluence storage format."""
        parts = []

        # Status panel
        status_color = self._status_color(story.status)
        parts.append(
            self._status_panel(
                f"<strong>Status:</strong> {story.status.name}<br/>"
                f"<strong>Priority:</strong> {story.priority.name}<br/>"
                f"<strong>Story Points:</strong> {story.story_points}",
                status_color,
            )
        )

        # User story description
        if story.description:
            parts.append("<h2>User Story</h2>")
            parts.append(self._quote_panel(self._format_description(story.description)))

        # Acceptance criteria
        if story.acceptance_criteria and story.acceptance_criteria.items:
            parts.append("<h2>Acceptance Criteria</h2>")
            parts.append(
                self._task_list(
                    story.acceptance_criteria.items,
                    story.acceptance_criteria.checked,
                )
            )

        # Subtasks
        if story.subtasks:
            parts.append("<h2>Subtasks</h2>")
            parts.append(self._subtasks_table(story.subtasks))

        # Technical notes
        if story.technical_notes:
            parts.append("<h2>Technical Notes</h2>")
            parts.append(self._code_block(story.technical_notes))

        # Commits
        if story.commits:
            parts.append("<h2>Related Commits</h2>")
            parts.append("<ul>")
            for commit in story.commits:
                parts.append(
                    f"<li><code>{html.escape(commit.sha[:8])}</code> - "
                    f"{html.escape(commit.message)}</li>"
                )
            parts.append("</ul>")

        # External links
        if story.external_url:
            parts.append("<h2>External Links</h2>")
            parts.append(
                f'<p><a href="{html.escape(story.external_url)}">View in Issue Tracker</a></p>'
            )

        return "\n".join(parts)

    def _format_description(self, desc: Description) -> str:
        """Format user story description."""
        if desc.role and desc.want:
            text = f"<strong>As a</strong> {html.escape(desc.role)},<br/>"
            text += f"<strong>I want</strong> {html.escape(desc.want)}"
            if desc.benefit:
                text += f",<br/><strong>So that</strong> {html.escape(desc.benefit)}"
            return f"<p>{text}</p>"
        return f"<p>{html.escape(desc.want)}</p>"

    # -------------------------------------------------------------------------
    # Confluence Macros & Formatting
    # -------------------------------------------------------------------------

    def _info_panel(self, content: str) -> str:
        """Create an info panel macro."""
        return (
            '<ac:structured-macro ac:name="info">'
            "<ac:rich-text-body>"
            f"<p>{content}</p>"
            "</ac:rich-text-body>"
            "</ac:structured-macro>"
        )

    def _status_panel(self, content: str, color: str = "Blue") -> str:
        """Create a colored panel."""
        return (
            f'<ac:structured-macro ac:name="panel">'
            f'<ac:parameter ac:name="borderColor">{color}</ac:parameter>'
            f'<ac:parameter ac:name="bgColor">{self._lighten_color(color)}</ac:parameter>'
            "<ac:rich-text-body>"
            f"<p>{content}</p>"
            "</ac:rich-text-body>"
            "</ac:structured-macro>"
        )

    def _quote_panel(self, content: str) -> str:
        """Create a quote block."""
        return f"<blockquote>{content}</blockquote>"

    def _code_block(self, content: str, language: str = "none") -> str:
        """Create a code block macro."""
        return (
            '<ac:structured-macro ac:name="code">'
            f'<ac:parameter ac:name="language">{language}</ac:parameter>'
            f"<ac:plain-text-body><![CDATA[{content}]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )

    def _status_lozenge(self, status: Status) -> str:
        """Create a status lozenge macro."""
        color = self._status_color(status)
        return (
            f'<ac:structured-macro ac:name="status">'
            f'<ac:parameter ac:name="colour">{color}</ac:parameter>'
            f'<ac:parameter ac:name="title">{status.name}</ac:parameter>'
            "</ac:structured-macro>"
        )

    def _status_color(self, status: Status) -> str:
        """Map status to Confluence color."""
        color_map = {
            Status.PLANNED: "Blue",
            Status.OPEN: "Blue",
            Status.IN_PROGRESS: "Yellow",
            Status.IN_REVIEW: "Yellow",
            Status.DONE: "Green",
            Status.CANCELLED: "Red",
        }
        return color_map.get(status, "Grey")

    def _lighten_color(self, color: str) -> str:
        """Get a lighter shade for backgrounds."""
        light_map = {
            "Blue": "#deebff",
            "Yellow": "#fffae6",
            "Green": "#e3fcef",
            "Red": "#ffebe6",
            "Grey": "#f4f5f7",
        }
        return light_map.get(color, "#f4f5f7")

    def _task_list(self, items: list[str], checked: list[bool]) -> str:
        """Create a task list."""
        parts = ["<ac:task-list>"]
        for i, item in enumerate(items):
            is_checked = checked[i] if i < len(checked) else False
            status = "complete" if is_checked else "incomplete"
            parts.append(
                f"<ac:task>"
                f"<ac:task-id>{i + 1}</ac:task-id>"
                f"<ac:task-status>{status}</ac:task-status>"
                f"<ac:task-body>{html.escape(item)}</ac:task-body>"
                f"</ac:task>"
            )
        parts.append("</ac:task-list>")
        return "\n".join(parts)

    def _stories_table(self, stories: list[UserStory]) -> str:
        """Create a summary table of stories."""
        rows = []
        rows.append(
            "<tr><th>ID</th><th>Title</th><th>Points</th><th>Priority</th><th>Status</th></tr>"
        )

        for story in stories:
            rows.append(
                f"<tr>"
                f"<td>{html.escape(str(story.id))}</td>"
                f"<td>{html.escape(story.title)}</td>"
                f"<td>{story.story_points}</td>"
                f"<td>{story.priority.name}</td>"
                f"<td>{self._status_lozenge(story.status)}</td>"
                f"</tr>"
            )

        return f"<table><tbody>{''.join(rows)}</tbody></table>"

    def _subtasks_table(self, subtasks: list[Subtask]) -> str:
        """Create a table of subtasks."""
        rows = []
        rows.append(
            "<tr><th>#</th><th>Task</th><th>Points</th><th>Status</th><th>Assignee</th></tr>"
        )

        for st in subtasks:
            rows.append(
                f"<tr>"
                f"<td>{st.number}</td>"
                f"<td>{html.escape(st.name)}</td>"
                f"<td>{st.story_points}</td>"
                f"<td>{self._status_lozenge(st.status)}</td>"
                f"<td>{html.escape(st.assignee or '-')}</td>"
                f"</tr>"
            )

        return f"<table><tbody>{''.join(rows)}</tbody></table>"
