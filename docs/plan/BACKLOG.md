# Spectra Backlog - Outstanding Work Items

> **Last Updated**: January 2026
> **Status**: 📋 Active Backlog (Recently Audited)

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

### ~~3. Asana Adapter - Full Feature Parity~~ ✅ COMPLETED
**Source**: Code review of `src/spectra/adapters/asana/adapter.py`
**Estimated Effort**: ~4 hours

**Status**: ✅ **VERIFIED January 2026** - All features implemented:
- [x] Batch operations support (`AsanaBatchClient` in `batch.py`)
- [x] Async operations support (`AsyncAsanaAdapter` in `async_adapter.py`)
- [x] Caching support (`CachedAsanaAdapter` in `cached_adapter.py`)
- [x] Custom field mapping (via `custom_fields` parameter)
- [x] Attachment handling (via `get_attachments`, `add_attachment`)
- [x] Comment sync (via `get_issue_comments`, `add_comment`)

**Tests**: 41 tests pass (16 unit + 25 integration)

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

### ~~5. Documentation Examples - Neutral Prefix~~ ✅ COMPLETED
**Source**: FLEXIBILITY-PLAN.md - Phase 3
**Estimated Effort**: ~2 hours

**Status**: ✅ **COMPLETED** - Documentation now shows flexible prefixes and notes that any `PREFIX-###` format works. See IMPROVEMENTS-CHECKLIST.md line 48.

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

### ~~7. AI Prompts - Dynamic Examples~~ ✅ COMPLETED
**Source**: FLEXIBILITY-PLAN.md - Section 8
**Estimated Effort**: ~1 hour

**Status**: ✅ **COMPLETED** - AI prompts now use dynamic examples. See IMPROVEMENTS-CHECKLIST.md line 49.

---

### ~~8. Parameterized Tests for ID Prefixes~~ ✅ COMPLETED
**Source**: FLEXIBILITY-PLAN.md - Phase 2
**Estimated Effort**: ~2 hours

**Status**: ✅ **COMPLETED** - Parameterized tests exist in `test_flexible_id_prefixes.py`. See IMPROVEMENTS-CHECKLIST.md line 32.

---

### ~~9. TrackerType Enum - Add Asana~~ ✅ COMPLETED
**Source**: Code review
**Estimated Effort**: ~30 minutes

**Status**: ✅ **VERIFIED January 2026** - TrackerType.ASANA is fully integrated:
- [x] `SourceFileUpdater._get_tracker_display_name()`
- [x] `SourceFileUpdater._build_url()`
- [x] CLI tracker selection
- [x] Documentation

See IMPROVEMENTS-CHECKLIST.md line 52.

---

### ~~10. OpenTelemetry/Prometheus - Optional Dependencies~~ ✅ COMPLETED
**Source**: `tests/cli/test_telemetry.py`
**Current State**: Properly skipped when not installed

**Status**: ✅ **COMPLETED** - Comprehensive documentation exists at `docs/guide/telemetry.md`. See IMPROVEMENTS-CHECKLIST.md line 51.

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
| Asana adapter full parity | BACKLOG.md #3 | ✅ Complete (Jan 2026) |
| Documentation neutral prefix | BACKLOG.md #5 | ✅ Complete |
| AI prompts dynamic examples | BACKLOG.md #7 | ✅ Complete |
| Parameterized ID prefix tests | BACKLOG.md #8 | ✅ Complete |
| TrackerType.ASANA integration | BACKLOG.md #9 | ✅ Complete |
| OpenTelemetry/Prometheus docs | BACKLOG.md #10 | ✅ Complete |

---

## Summary

| Priority | Count | Estimated Effort |
|----------|-------|------------------|
| 🔴 High | 2 | ~4 hours |
| 🟡 Medium | 2 | ~10 hours |
| 🟢 Low | 0 | 0 hours |
| Technical Debt | 2 | TBD |
| ✅ Completed | 6 | - |

**Total Remaining Effort**: ~14 hours

---

## Contributing

To work on any of these items:

1. Check if there's an existing GitHub issue
2. Create a branch: `feature/backlog-item-name`
3. Implement with tests
4. Run quality checks: `ruff format src tests && ruff check src tests --fix && mypy src/spectra && pytest`
5. Update this backlog when complete


