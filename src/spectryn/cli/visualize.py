"""
Visualize Command - Generate dependency graphs.

Outputs:
- Mermaid diagrams
- Graphviz DOT format
- ASCII art (for terminal)

Shows:
- Story dependencies
- Epic relationships
- Status flow
- Priority heatmap
"""

from dataclasses import dataclass, field
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


@dataclass
class GraphNode:
    """A node in the graph."""

    id: str
    label: str
    node_type: str  # epic, story, subtask
    status: str = ""
    priority: str = ""
    points: int = 0


@dataclass
class GraphEdge:
    """An edge in the graph."""

    source: str
    target: str
    edge_type: str  # blocks, depends_on, relates_to, parent


@dataclass
class DependencyGraph:
    """Graph of story dependencies."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    @property
    def has_dependencies(self) -> bool:
        """Check if there are any dependencies."""
        return bool(self.edges)


def build_graph_from_file(file_path: str) -> DependencyGraph:
    """
    Build dependency graph from a markdown file.

    Args:
        file_path: Path to markdown file.

    Returns:
        DependencyGraph with nodes and edges.
    """
    from spectryn.adapters.parsers import MarkdownParser

    graph = DependencyGraph()
    parser = MarkdownParser()

    try:
        epic = parser.parse_epic(file_path)
    except Exception:
        return graph

    # Add epic node
    graph.nodes.append(
        GraphNode(
            id=str(epic.key),
            label=epic.title[:30],
            node_type="epic",
        )
    )

    # Add story nodes and edges
    for story in epic.stories:
        story_id = str(story.id)

        graph.nodes.append(
            GraphNode(
                id=story_id,
                label=story.title[:25],
                node_type="story",
                status=story.status.value if story.status else "",
                priority=story.priority.value if story.priority else "",
                points=story.story_points or 0,
            )
        )

        # Edge from epic to story
        graph.edges.append(
            GraphEdge(
                source=str(epic.key),
                target=story_id,
                edge_type="parent",
            )
        )

        # Parse links for dependencies
        if story.links:
            for link in story.links:
                link_lower = link.lower()

                # Determine edge type
                if "blocks" in link_lower:
                    edge_type = "blocks"
                elif "depends" in link_lower or "blocked by" in link_lower:
                    edge_type = "depends_on"
                else:
                    edge_type = "relates_to"

                # Extract target ID
                import re

                target_match = re.search(r"([A-Z]+-\d+|US-\d+|#\d+)", link)
                if target_match:
                    graph.edges.append(
                        GraphEdge(
                            source=story_id,
                            target=target_match.group(1),
                            edge_type=edge_type,
                        )
                    )

    return graph


def generate_mermaid(graph: DependencyGraph, direction: str = "TB") -> str:
    """
    Generate Mermaid diagram from graph.

    Args:
        graph: DependencyGraph to render.
        direction: Graph direction (TB, LR, BT, RL).

    Returns:
        Mermaid diagram string.
    """
    lines = [f"graph {direction}"]
    lines.append("")

    # Style definitions
    lines.append("    %% Styles")
    lines.append("    classDef epic fill:#6366f1,stroke:#4338ca,color:#fff")
    lines.append("    classDef done fill:#22c55e,stroke:#16a34a,color:#fff")
    lines.append("    classDef inprogress fill:#f59e0b,stroke:#d97706,color:#fff")
    lines.append("    classDef planned fill:#94a3b8,stroke:#64748b,color:#fff")
    lines.append("    classDef blocked fill:#ef4444,stroke:#dc2626,color:#fff")
    lines.append("")

    # Node definitions
    lines.append("    %% Nodes")
    for node in graph.nodes:
        # Escape label
        label = node.label.replace('"', "'")

        if node.node_type == "epic":
            lines.append(f'    {node.id}["{label}"]:::epic')
        else:
            # Determine style based on status
            status_lower = node.status.lower()
            if status_lower in ("done", "closed", "resolved"):
                style = ":::done"
            elif status_lower in ("in_progress", "in progress", "active"):
                style = ":::inprogress"
            elif status_lower in ("blocked",):
                style = ":::blocked"
            else:
                style = ":::planned"

            if node.points:
                lines.append(f'    {node.id}["{label}<br/>({node.points} pts)"]{style}')
            else:
                lines.append(f'    {node.id}["{label}"]{style}')

    lines.append("")

    # Edge definitions
    lines.append("    %% Edges")
    for edge in graph.edges:
        if edge.edge_type == "parent":
            lines.append(f"    {edge.source} --> {edge.target}")
        elif edge.edge_type == "blocks":
            lines.append(f"    {edge.source} -.->|blocks| {edge.target}")
        elif edge.edge_type == "depends_on":
            lines.append(f"    {edge.target} -.->|depends on| {edge.source}")
        else:
            lines.append(f"    {edge.source} -.- {edge.target}")

    return "\n".join(lines)


def generate_graphviz(graph: DependencyGraph) -> str:
    """
    Generate Graphviz DOT format from graph.

    Args:
        graph: DependencyGraph to render.

    Returns:
        DOT format string.
    """
    lines = ["digraph G {"]
    lines.append("    rankdir=TB;")
    lines.append("    node [shape=box, style=rounded];")
    lines.append("")

    # Color mapping
    status_colors = {
        "done": "#22c55e",
        "closed": "#22c55e",
        "resolved": "#22c55e",
        "in_progress": "#f59e0b",
        "in progress": "#f59e0b",
        "active": "#f59e0b",
        "blocked": "#ef4444",
    }

    # Nodes
    for node in graph.nodes:
        label = node.label.replace('"', '\\"')
        if node.points:
            label = f"{label}\\n({node.points} pts)"

        if node.node_type == "epic":
            lines.append(
                f'    "{node.id}" [label="{label}", '
                f'fillcolor="#6366f1", style=filled, fontcolor=white];'
            )
        else:
            color = status_colors.get(node.status.lower(), "#94a3b8")
            lines.append(f'    "{node.id}" [label="{label}", fillcolor="{color}", style=filled];')

    lines.append("")

    # Edges
    for edge in graph.edges:
        if edge.edge_type == "parent":
            lines.append(f'    "{edge.source}" -> "{edge.target}";')
        elif edge.edge_type == "blocks":
            lines.append(f'    "{edge.source}" -> "{edge.target}" [style=dashed, label="blocks"];')
        elif edge.edge_type == "depends_on":
            lines.append(
                f'    "{edge.target}" -> "{edge.source}" [style=dashed, label="depends on"];'
            )
        else:
            lines.append(f'    "{edge.source}" -> "{edge.target}" [style=dotted];')

    lines.append("}")
    return "\n".join(lines)


def generate_ascii(graph: DependencyGraph, color: bool = True) -> str:
    """
    Generate ASCII art visualization.

    Args:
        graph: DependencyGraph to render.
        color: Whether to use colors.

    Returns:
        ASCII art string.
    """
    lines = []

    # Find epics
    epics = [n for n in graph.nodes if n.node_type == "epic"]
    stories = [n for n in graph.nodes if n.node_type == "story"]

    # Status symbols
    status_symbols = {
        "done": "✅",
        "closed": "✅",
        "resolved": "✅",
        "in_progress": "🔄",
        "in progress": "🔄",
        "active": "🔄",
        "blocked": "⏸️",
        "planned": "📋",
    }

    for epic in epics:
        if color:
            lines.append(f"{Colors.BOLD}{Colors.CYAN}🚀 {epic.id}: {epic.label}{Colors.RESET}")
        else:
            lines.append(f"🚀 {epic.id}: {epic.label}")
        lines.append("│")

        # Get stories for this epic
        epic_stories = [
            s for s in stories if any(e.source == epic.id and e.target == s.id for e in graph.edges)
        ]

        for i, story in enumerate(epic_stories):
            is_last = i == len(epic_stories) - 1
            connector = "└──" if is_last else "├──"

            symbol = status_symbols.get(story.status.lower(), "📋")
            points_str = f" ({story.points} pts)" if story.points else ""

            if color:
                status_color = ""
                if story.status.lower() in ("done", "closed", "resolved"):
                    status_color = Colors.GREEN
                elif story.status.lower() in ("in_progress", "in progress"):
                    status_color = Colors.YELLOW
                elif story.status.lower() == "blocked":
                    status_color = Colors.RED

                lines.append(
                    f"{connector} {symbol} {status_color}{story.id}{Colors.RESET}: "
                    f"{story.label}{points_str}"
                )
            else:
                lines.append(f"{connector} {symbol} {story.id}: {story.label}{points_str}")

            # Show dependencies
            deps = [e for e in graph.edges if e.source == story.id and e.edge_type != "parent"]
            for dep in deps:
                indent = "    " if is_last else "│   "
                if color:
                    lines.append(
                        f"{indent}  {Colors.DIM}↳ {dep.edge_type}: {dep.target}{Colors.RESET}"
                    )
                else:
                    lines.append(f"{indent}  ↳ {dep.edge_type}: {dep.target}")

    return "\n".join(lines)


def run_visualize(
    console: Console,
    input_path: str,
    output_format: str = "mermaid",
    output_file: str | None = None,
    direction: str = "TB",
) -> int:
    """
    Run the visualize command.

    Args:
        console: Console for output.
        input_path: Path to markdown file.
        output_format: Output format (mermaid, graphviz, ascii).
        output_file: Optional output file path.
        direction: Graph direction for mermaid.

    Returns:
        Exit code.
    """
    console.header(f"spectra Visualize {Symbols.CHART}")
    console.print()

    # Check file exists
    if not Path(input_path).exists():
        console.error(f"File not found: {input_path}")
        return ExitCode.FILE_NOT_FOUND

    console.info(f"Source: {input_path}")
    console.info(f"Format: {output_format}")
    console.print()

    # Build graph
    console.info("Building dependency graph...")
    graph = build_graph_from_file(input_path)

    console.info(f"Found {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    console.print()

    # Generate output
    if output_format == "mermaid":
        output = generate_mermaid(graph, direction)
    elif output_format in ("graphviz", "dot"):
        output = generate_graphviz(graph)
    elif output_format == "ascii":
        output = generate_ascii(graph, color=console.color)
    else:
        console.error(f"Unknown format: {output_format}")
        console.info("Supported: mermaid, graphviz, ascii")
        return ExitCode.CONFIG_ERROR

    # Output
    if output_file:
        Path(output_file).write_text(output, encoding="utf-8")
        console.success(f"Written to: {output_file}")

        # Hint for mermaid
        if output_format == "mermaid":
            console.print()
            console.info("View the diagram:")
            console.item("https://mermaid.live (paste content)")
            console.item("VS Code: Markdown Preview Mermaid Support extension")
    # Print to stdout
    elif output_format in ("mermaid", "graphviz", "dot"):
        print("```" + output_format)
        print(output)
        print("```")
    else:
        print(output)

    return ExitCode.SUCCESS
