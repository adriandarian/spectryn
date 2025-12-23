# Spectra Backlog - Outstanding Work Items

> **Last Updated**: December 2025
> **Status**: 📋 Active Backlog

This document consolidates all remaining work items, planned features, and potential improvements identified across the codebase.

---

## 🔴 Priority: High

### 1. Custom ID Separators Support
**Source**: FLEXIBILITY-PLAN.md - Related Improvements
**Estimated Effort**: ~2 hours

Currently, story IDs only support hyphen separators (`PROJ-123`). Some organizations use:
- Underscore: `PROJ_123`
- Forward slash: `PROJ/123`

**Files to Update**:
- `src/spectra/core/domain/value_objects.py` - `StoryId` and `IssueKey` patterns
- `src/spectra/adapters/parsers/markdown.py` - `STORY_ID_PATTERN`
- `src/spectra/adapters/parsers/asciidoc_parser.py`
- `src/spectra/adapters/parsers/*.py` - All other parsers
- Tests for each parser

**Implementation**:
```python
# Current pattern
STORY_ID_PATTERN = r"[A-Z]+-\d+"

# Proposed pattern
STORY_ID_PATTERN = r"[A-Z]+[-_/]\d+"
```

---

### 2. Universal `#123` ID Support
**Source**: FLEXIBILITY-PLAN.md - Related Improvements
**Estimated Effort**: ~2 hours

GitHub-style `#123` IDs are only supported in `NotionParser`. Extend to all parsers.

**Current State**:
| Parser | `#123` Support |
|--------|----------------|
| `NotionParser` | ✅ Yes |
| `MarkdownParser` | ❌ No |
| `AsciiDocParser` | ❌ No |
| `YamlParser` | ❌ No |
| `JsonParser` | ❌ No |
| `CsvParser` | ❌ No |
| `ExcelParser` | ❌ No |
| `TomlParser` | ❌ No |

**Files to Update**:
- All parsers in `src/spectra/adapters/parsers/`
- `src/spectra/core/domain/value_objects.py` - May need a new `GitHubStyleId` value object
- Tests for each parser

---

## 🟡 Priority: Medium

### 3. Asana Adapter - Full Feature Parity
**Source**: Code review of `src/spectra/adapters/asana/adapter.py`
**Estimated Effort**: ~4 hours

The Asana adapter is functional but may be missing some features compared to the Jira adapter:

**To Verify/Implement**:
- [ ] Batch operations support (like `JiraBatchClient`)
- [ ] Async operations support
- [ ] Caching support
- [ ] Custom field mapping
- [ ] Attachment handling
- [ ] Comment sync

---

### 4. Integration Tests for All Trackers
**Source**: Test coverage analysis
**Estimated Effort**: ~6 hours

Currently only Jira has dedicated integration tests (`tests/integration/test_jira_integration.py`).

**Missing Integration Tests**:
- [ ] `test_github_integration.py`
- [ ] `test_linear_integration.py`
- [ ] `test_azure_devops_integration.py`
- [ ] `test_asana_integration.py`
- [ ] `test_confluence_integration.py`

---

### 5. Documentation Examples - Neutral Prefix
**Source**: FLEXIBILITY-PLAN.md - Phase 3
**Estimated Effort**: ~2 hours

Many documentation examples still use `US-001` format. While technically valid, consider using a more neutral prefix like `STORY-001` or varying prefixes to demonstrate flexibility.

**Files to Review**:
- `docs/guide/quick-start.md`
- `docs/guide/getting-started.md`
- `docs/examples/template.md`
- `docs/examples/basic.md`
- `README.md`

---

### 6. Code Coverage Target
**Source**: CHANGELOG.md
**Estimated Effort**: Ongoing

Current coverage: 70%+
Target coverage: 80%+

**Areas Needing Coverage**:
- Run `pytest --cov=spectra --cov-report=html` to identify gaps
- Focus on edge cases in parsers
- Error handling paths in adapters

---

## 🟢 Priority: Low

### 7. AI Prompts - Dynamic Examples
**Source**: FLEXIBILITY-PLAN.md - Section 8
**Estimated Effort**: ~1 hour

AI prompts in `src/spectra/cli/ai_fix.py` contain hardcoded `US-001` examples. Make these dynamic or use neutral examples.

**Current**:
```python
"Story headers MUST use format: ### [emoji] US-XXX: Title"
```

**Proposed**:
```python
"Story headers MUST use format: ### [emoji] PREFIX-XXX: Title (e.g., US-001, PROJ-123)"
```

---

### 8. Parameterized Tests for ID Prefixes
**Source**: FLEXIBILITY-PLAN.md - Phase 2
**Estimated Effort**: ~2 hours

Add parameterized tests to ensure all parsers handle varied prefixes:

```python
@pytest.mark.parametrize("story_id", [
    "US-001",      # backwards compat
    "EU-001",      # regional
    "PROJ-123",    # project
    "A-1",         # minimal
    "VERYLONGPREFIX-99999",  # edge case
])
def test_parse_various_prefixes(parser, story_id):
    ...
```

---

### 9. TrackerType Enum - Add Asana
**Source**: Code review
**Estimated Effort**: ~30 minutes

The `TrackerType` enum in `config_provider.py` already has `ASANA`, but verify it's fully integrated in:
- [ ] `SourceFileUpdater._get_tracker_display_name()`
- [ ] `SourceFileUpdater._build_url()`
- [ ] CLI tracker selection
- [ ] Documentation

---

### 10. OpenTelemetry/Prometheus - Optional Dependencies
**Source**: `tests/cli/test_telemetry.py`
**Current State**: Properly skipped when not installed

These are optional features that work correctly. Consider adding documentation for setup:
- [ ] Document OpenTelemetry integration setup
- [ ] Document Prometheus metrics export setup

---

## 📝 Technical Debt

### 11. Comment/Note Patterns in Code
**Source**: Grep for `Note:` patterns

Several informational notes exist in the code. These are documentation, not TODOs, but could be formalized:
- `markdown.py:1143` - Colon placement in markdown
- `source_updater.py:190` - Pattern explanation
- `asana/adapter.py:274` - Asana API limitations

---

### 12. Backup Restoration - Story Points
**Source**: `application/sync/backup.py:780`

```python
# Note: Story points restoration for parent issues would need
```

This comment suggests incomplete implementation for restoring story points on parent issues.

---

## ✅ Recently Completed

These items were in planning documents but are now complete:

| Item | Plan | Status |
|------|------|--------|
| Flexible story ID prefixes | FLEXIBILITY-PLAN.md | ✅ Complete |
| Lowercase tolerance | FLEXIBILITY-PLAN.md | ✅ Complete |
| Number padding flexibility | FLEXIBILITY-PLAN.md | ✅ Complete |
| Epic ID flexibility | FLEXIBILITY-PLAN.md | ✅ Complete |
| Tracker writeback service | TRACKER-WRITEBACK-PLAN.md | ✅ Complete |
| Parser reads tracker info | TRACKER-WRITEBACK-PLAN.md | ✅ Complete |
| CLI `--update-source` option | TRACKER-WRITEBACK-PLAN.md | ✅ Complete |
| Subtask tracking writeback | TRACKER-WRITEBACK-PLAN.md | ✅ Complete |
| Conflict detection | TRACKER-WRITEBACK-PLAN.md | ✅ Complete |
| Last sync timestamp | TRACKER-WRITEBACK-PLAN.md | ✅ Complete |

---

## Summary

| Priority | Count | Estimated Effort |
|----------|-------|------------------|
| 🔴 High | 2 | ~4 hours |
| 🟡 Medium | 4 | ~14 hours |
| 🟢 Low | 4 | ~5.5 hours |
| Technical Debt | 2 | TBD |

**Total Estimated Effort**: ~23.5 hours

---

## Contributing

To work on any of these items:

1. Check if there's an existing GitHub issue
2. Create a branch: `feature/backlog-item-name`
3. Implement with tests
4. Run quality checks: `ruff format src tests && ruff check src tests --fix && mypy src/spectra && pytest`
5. Update this backlog when complete


