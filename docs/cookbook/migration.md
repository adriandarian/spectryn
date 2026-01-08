# Migration Projects

Track system migrations, technology upgrades, and data migrations with spectryn.

## Migration Epic Template

```markdown
# 🔄 Database Migration: PostgreSQL to CockroachDB

> **Epic: Migrate primary database for horizontal scalability**

---

## Epic Summary

| Field | Value |
|-------|-------|
| **Epic Name** | PostgreSQL to CockroachDB Migration |
| **Status** | 🔄 In Progress |
| **Priority** | 🔴 Critical |
| **Start Date** | January 2025 |
| **Target Date** | March 2025 |
| **Risk Level** | High |

### Summary

Migrate our primary PostgreSQL database to CockroachDB to achieve 
horizontal scalability and multi-region deployment capabilities.

### Migration Phases

1. **Preparation** - Schema analysis, compatibility testing
2. **Development** - Code changes, ORM updates
3. **Testing** - Performance, data integrity verification
4. **Migration** - Data sync, cutover
5. **Validation** - Post-migration verification

### Rollback Plan

- Keep PostgreSQL in read-only mode for 2 weeks post-migration
- Automated rollback script prepared
- Data sync bidirectional during transition period

---

## Phase 1: Preparation

---

### 🔧 US-001: Schema Compatibility Analysis

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | ✅ Done |
| **Phase** | Preparation |

#### Description

**As a** database engineer
**I want** to analyze PostgreSQL schema for CockroachDB compatibility
**So that** we identify required changes before development

#### Acceptance Criteria

- [x] All tables analyzed for compatibility
- [x] Incompatible features documented
- [x] Migration complexity estimated
- [x] Report shared with team

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Export schema | pg_dump schema only | 1 | ✅ Done |
| 2 | Run compatibility tool | CockroachDB migration tool | 1 | ✅ Done |
| 3 | Document findings | Create compatibility report | 2 | ✅ Done |
| 4 | Estimate effort | Story point estimates for fixes | 1 | ✅ Done |

---

### 🔧 US-002: Development Environment Setup

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🔴 Critical |
| **Status** | ✅ Done |
| **Phase** | Preparation |

#### Description

**As a** developer
**I want** CockroachDB running locally
**So that** I can develop and test migrations

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Docker compose | Add CockroachDB to docker-compose | 1 | ✅ Done |
| 2 | Seed data | Script to populate test data | 1 | ✅ Done |
| 3 | Documentation | Update README with setup steps | 1 | ✅ Done |

---

## Phase 2: Development

---

### 🔧 US-003: ORM Compatibility Changes

| Field | Value |
|-------|-------|
| **Story Points** | 8 |
| **Priority** | 🔴 Critical |
| **Status** | 🔄 In Progress |
| **Phase** | Development |

#### Description

**As a** backend developer
**I want** ORM queries updated for CockroachDB
**So that** the application works with the new database

#### Acceptance Criteria

- [ ] All raw SQL queries reviewed
- [ ] Incompatible queries rewritten
- [ ] Transaction retry logic added
- [ ] All tests pass with CockroachDB

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Audit raw queries | Find all raw SQL in codebase | 1 | ✅ Done |
| 2 | Fix SERIAL to UUID | Replace auto-increment with UUID | 2 | ✅ Done |
| 3 | Add retry logic | Handle transaction conflicts | 2 | 🔄 In Progress |
| 4 | Update migrations | Alembic migration compatibility | 2 | 📋 Planned |
| 5 | Integration tests | Test suite with CockroachDB | 1 | 📋 Planned |

---

### 🔧 US-004: Schema Migrations

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟡 High |
| **Status** | 📋 Planned |
| **Phase** | Development |

#### Description

**As a** database engineer
**I want** schema migration scripts ready
**So that** we can migrate the database structure

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Create migration script | SQL to create all tables | 2 | 📋 Planned |
| 2 | Index optimization | Optimize indexes for CockroachDB | 1 | 📋 Planned |
| 3 | Foreign key review | Ensure FK constraints work | 1 | 📋 Planned |
| 4 | Test on staging | Run migration on staging DB | 1 | 📋 Planned |

---

## Phase 3: Testing

---

### 🧪 US-005: Performance Testing

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |
| **Phase** | Testing |

#### Description

**As a** performance engineer
**I want** to benchmark CockroachDB performance
**So that** we ensure acceptable response times

#### Acceptance Criteria

- [ ] Load test with production-like traffic
- [ ] Query performance within 2x of PostgreSQL
- [ ] No degradation under concurrent load
- [ ] Report with recommendations

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Setup k6 tests | Load testing scripts | 1 | 📋 Planned |
| 2 | Baseline PostgreSQL | Benchmark current performance | 1 | 📋 Planned |
| 3 | Benchmark CockroachDB | Run same tests on CRDB | 1 | 📋 Planned |
| 4 | Analyze & optimize | Tune queries if needed | 2 | 📋 Planned |

---

### 🧪 US-006: Data Integrity Verification

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |
| **Phase** | Testing |

#### Description

**As a** QA engineer
**I want** to verify data integrity after migration
**So that** we confirm no data loss or corruption

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Row count verification | Compare table counts | 1 | 📋 Planned |
| 2 | Checksum validation | Hash comparison on key tables | 1 | 📋 Planned |
| 3 | Sample data review | Manual spot checks | 1 | 📋 Planned |

---

## Phase 4: Migration

---

### 🚀 US-007: Data Migration Execution

| Field | Value |
|-------|-------|
| **Story Points** | 8 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |
| **Phase** | Migration |

#### Description

**As a** database engineer
**I want** to execute the production data migration
**So that** we complete the database transition

#### Acceptance Criteria

- [ ] Migration window scheduled
- [ ] All stakeholders notified
- [ ] Runbook prepared and tested
- [ ] Rollback procedure verified
- [ ] Post-migration checks pass

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Final data sync | Sync latest data to CRDB | 2 | 📋 Planned |
| 2 | Application cutover | Switch connection strings | 1 | 📋 Planned |
| 3 | Smoke tests | Verify critical paths | 2 | 📋 Planned |
| 4 | Monitor | Watch metrics for 24 hours | 2 | 📋 Planned |
| 5 | Communication | Update stakeholders | 1 | 📋 Planned |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Data loss during migration | Critical | Dual-write during transition |
| Performance regression | High | Extensive load testing |
| Application bugs | High | Feature flags for rollback |
| Extended downtime | Medium | Practice runbook in staging |

---
```

## Sync Commands for Migration

```bash
# Initial sync when planning starts
spectryn -m migrations/postgres-to-crdb.md -e INFRA-100 -x

# Update as phases complete
spectryn -m migrations/postgres-to-crdb.md -e INFRA-100 -x --phase statuses

# Export for stakeholder reports
spectryn -m migrations/postgres-to-crdb.md -e INFRA-100 --export migration-status.json
```

## Migration Tracking Dashboard

Create a script to generate migration status:

```bash
#!/bin/bash
# migration-status.sh

spectryn -m migrations/postgres-to-crdb.md -e INFRA-100 --output json | jq '
{
  epic: .epic_key,
  phases: [
    {name: "Preparation", complete: (.stories | map(select(.phase == "Preparation" and .status == "done")) | length), total: (.stories | map(select(.phase == "Preparation")) | length)},
    {name: "Development", complete: (.stories | map(select(.phase == "Development" and .status == "done")) | length), total: (.stories | map(select(.phase == "Development")) | length)},
    {name: "Testing", complete: (.stories | map(select(.phase == "Testing" and .status == "done")) | length), total: (.stories | map(select(.phase == "Testing")) | length)},
    {name: "Migration", complete: (.stories | map(select(.phase == "Migration" and .status == "done")) | length), total: (.stories | map(select(.phase == "Migration")) | length)}
  ],
  overall: {
    complete: (.stories | map(select(.status == "done")) | length),
    total: (.stories | length)
  }
}
'
```

## Tips

::: warning Migration Best Practices
- **Always have a rollback plan**
- Test migrations in staging first
- Document every step in the runbook
- Communicate timeline to stakeholders
:::

::: tip Version Control
- Keep migration docs in Git
- Tag completed phases
- Review changes in PRs before sync
:::

