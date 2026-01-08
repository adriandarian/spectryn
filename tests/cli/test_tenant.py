"""Tests for CLI tenant commands."""

from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_console():
    """Create a mock console."""
    console = MagicMock()
    return console


@pytest.fixture
def mock_tenant():
    """Create a mock tenant object."""
    tenant = MagicMock()
    tenant.id = "test-tenant"
    tenant.name = "Test Tenant"
    tenant.description = "A test tenant"
    tenant.status = MagicMock()
    tenant.status.value = "active"
    tenant.isolation_level = MagicMock()
    tenant.isolation_level.value = "strict"
    tenant.created_at = "2024-01-01T00:00:00"
    tenant.updated_at = "2024-01-02T00:00:00"
    tenant.metadata = {"env": "test"}
    tenant.to_dict = MagicMock(
        return_value={
            "id": "test-tenant",
            "name": "Test Tenant",
            "status": "active",
        }
    )
    return tenant


@pytest.fixture
def mock_paths():
    """Create mock tenant paths."""
    paths = MagicMock()
    paths.root = "/data/tenants/test"
    paths.config_dir = "/data/tenants/test/config"
    paths.config_file = "/data/tenants/test/config/spectra.yaml"
    paths.env_file = "/data/tenants/test/.env"
    paths.state_dir = "/data/tenants/test/state"
    paths.cache_dir = "/data/tenants/test/cache"
    paths.backup_dir = "/data/tenants/test/backups"
    paths.get_all_paths = MagicMock(
        return_value={
            "root": paths.root,
            "config": paths.config_dir,
            "state": paths.state_dir,
        }
    )
    return paths


@pytest.fixture
def mock_tenant_manager(mock_tenant, mock_paths):
    """Create a mock tenant manager."""
    manager = MagicMock()
    manager.current_tenant = mock_tenant
    manager.list_tenants = MagicMock(return_value=[mock_tenant])
    manager.create = MagicMock(return_value=mock_tenant)
    manager.use = MagicMock(return_value=mock_tenant)
    manager.get_tenant = MagicMock(return_value=mock_tenant)
    manager.delete_tenant = MagicMock()
    manager.registry = MagicMock()
    manager.registry.get_paths = MagicMock(return_value=mock_paths)
    manager.registry.archive = MagicMock(return_value=mock_tenant)
    manager.registry.activate = MagicMock(return_value=mock_tenant)
    return manager


# =============================================================================
# handle_tenant_command Tests
# =============================================================================


class TestHandleTenantCommand:
    """Tests for handle_tenant_command dispatcher."""

    def test_dispatches_list_command(self, mock_console):
        """Test dispatching list command."""
        from spectryn.cli.tenant import handle_tenant_command

        args = argparse.Namespace(tenant_command="list", all=False, json=False)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_manager = MagicMock()
            mock_manager.list_tenants.return_value = []
            mock_get.return_value = mock_manager

            result = handle_tenant_command(args, mock_console)

            assert result == 0

    def test_dispatches_create_command(self, mock_console, mock_tenant_manager):
        """Test dispatching create command."""
        from spectryn.cli.tenant import handle_tenant_command

        args = argparse.Namespace(
            tenant_command="create",
            id="new-tenant",
            name="New Tenant",
            description="Desc",
            isolation="full",
            activate=False,
        )

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = handle_tenant_command(args, mock_console)

            assert result == 0

    def test_unknown_command(self, mock_console):
        """Test handling unknown command."""
        from spectryn.cli.tenant import handle_tenant_command

        args = argparse.Namespace(tenant_command="unknown")

        result = handle_tenant_command(args, mock_console)

        assert result == 1
        mock_console.error.assert_called()


# =============================================================================
# _cmd_tenant_list Tests
# =============================================================================


class TestCmdTenantList:
    """Tests for tenant list command."""

    def test_list_empty(self, mock_console):
        """Test listing when no tenants exist."""
        from spectryn.cli.tenant import _cmd_tenant_list

        args = argparse.Namespace(all=False, json=False)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_manager = MagicMock()
            mock_manager.list_tenants.return_value = []
            mock_get.return_value = mock_manager

            result = _cmd_tenant_list(args, mock_console)

            assert result == 0
            mock_console.info.assert_called_with("No tenants configured")

    def test_list_with_tenants(self, mock_console, mock_tenant_manager, mock_tenant):
        """Test listing existing tenants."""
        from spectryn.cli.tenant import _cmd_tenant_list

        args = argparse.Namespace(all=False, json=False)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_list(args, mock_console)

            assert result == 0
            mock_console.section.assert_called_with("Tenants")

    def test_list_json_output(self, mock_console, mock_tenant_manager, mock_tenant):
        """Test listing with JSON output."""
        from spectryn.cli.tenant import _cmd_tenant_list

        args = argparse.Namespace(all=False, json=True)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_list(args, mock_console)

            assert result == 0
            mock_console.print.assert_called()

    def test_list_includes_inactive(self, mock_console, mock_tenant_manager):
        """Test listing includes inactive when requested."""
        from spectryn.cli.tenant import _cmd_tenant_list

        args = argparse.Namespace(all=True, json=False)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            _cmd_tenant_list(args, mock_console)

            mock_tenant_manager.list_tenants.assert_called_with(include_inactive=True)


# =============================================================================
# _cmd_tenant_create Tests
# =============================================================================


class TestCmdTenantCreate:
    """Tests for tenant create command."""

    def test_create_basic(self, mock_console, mock_tenant_manager):
        """Test creating a basic tenant."""
        from spectryn.cli.tenant import _cmd_tenant_create

        args = argparse.Namespace(
            id="new-tenant",
            name="New Tenant",
            description="A new tenant",
            isolation="full",
            activate=False,
        )

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_create(args, mock_console)

            assert result == 0
            mock_console.success.assert_called()

    def test_create_with_activation(self, mock_console, mock_tenant_manager):
        """Test creating and activating a tenant."""
        from spectryn.cli.tenant import _cmd_tenant_create

        args = argparse.Namespace(
            id="new-tenant",
            name=None,  # Should use id as name
            description=None,
            isolation="full",
            activate=True,
        )

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_create(args, mock_console)

            assert result == 0
            mock_console.info.assert_called()

    def test_create_error(self, mock_console, mock_tenant_manager):
        """Test create with error."""
        from spectryn.cli.tenant import _cmd_tenant_create

        args = argparse.Namespace(
            id="new-tenant",
            name="Test",
            description=None,
            isolation="full",
            activate=False,
        )

        mock_tenant_manager.create.side_effect = ValueError("Already exists")

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_create(args, mock_console)

            assert result == 1
            mock_console.error.assert_called()

    def test_create_with_hyphenated_isolation(self, mock_console, mock_tenant_manager):
        """Test creating with hyphenated isolation level."""
        from spectryn.cli.tenant import _cmd_tenant_create

        args = argparse.Namespace(
            id="new-tenant",
            name="Test",
            description=None,
            isolation="shared-cache",  # hyphenated becomes shared_cache
            activate=False,
        )

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_create(args, mock_console)

            assert result == 0


# =============================================================================
# _cmd_tenant_use Tests
# =============================================================================


class TestCmdTenantUse:
    """Tests for tenant use command."""

    def test_use_success(self, mock_console, mock_tenant_manager):
        """Test successful tenant switch."""
        from spectryn.cli.tenant import _cmd_tenant_use

        args = argparse.Namespace(id="other-tenant")

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_use(args, mock_console)

            assert result == 0
            mock_console.success.assert_called()

    def test_use_not_found(self, mock_console, mock_tenant_manager):
        """Test switching to non-existent tenant."""
        from spectryn.cli.tenant import _cmd_tenant_use

        args = argparse.Namespace(id="missing-tenant")
        mock_tenant_manager.use.side_effect = KeyError("Not found")

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_use(args, mock_console)

            assert result == 1
            mock_console.error.assert_called_with("Tenant 'missing-tenant' not found")

    def test_use_runtime_error(self, mock_console, mock_tenant_manager):
        """Test switch with runtime error."""
        from spectryn.cli.tenant import _cmd_tenant_use

        args = argparse.Namespace(id="bad-tenant")
        mock_tenant_manager.use.side_effect = RuntimeError("Tenant is archived")

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_use(args, mock_console)

            assert result == 1


# =============================================================================
# _cmd_tenant_show Tests
# =============================================================================


class TestCmdTenantShow:
    """Tests for tenant show command."""

    def test_show_current_tenant(self, mock_console, mock_tenant_manager):
        """Test showing current tenant."""
        from spectryn.cli.tenant import _cmd_tenant_show

        args = argparse.Namespace(id=None, json=False)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_show(args, mock_console)

            assert result == 0
            mock_console.section.assert_called()

    def test_show_specific_tenant(self, mock_console, mock_tenant_manager):
        """Test showing specific tenant."""
        from spectryn.cli.tenant import _cmd_tenant_show

        args = argparse.Namespace(id="other-tenant", json=False)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_show(args, mock_console)

            assert result == 0

    def test_show_not_found(self, mock_console, mock_tenant_manager):
        """Test showing non-existent tenant."""
        from spectryn.cli.tenant import _cmd_tenant_show

        args = argparse.Namespace(id="missing", json=False)
        mock_tenant_manager.get_tenant.return_value = None

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_show(args, mock_console)

            assert result == 1
            mock_console.error.assert_called()

    def test_show_json_output(self, mock_console, mock_tenant_manager, mock_tenant):
        """Test showing tenant with JSON output."""
        from spectryn.cli.tenant import _cmd_tenant_show

        args = argparse.Namespace(id=None, json=True)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_show(args, mock_console)

            assert result == 0
            mock_console.print.assert_called()

    def test_show_without_metadata(self, mock_console, mock_tenant_manager, mock_tenant):
        """Test showing tenant without metadata."""
        from spectryn.cli.tenant import _cmd_tenant_show

        args = argparse.Namespace(id=None, json=False)
        mock_tenant.metadata = {}

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_show(args, mock_console)

            assert result == 0


# =============================================================================
# _cmd_tenant_delete Tests
# =============================================================================


class TestCmdTenantDelete:
    """Tests for tenant delete command."""

    def test_delete_with_force(self, mock_console, mock_tenant_manager):
        """Test force deleting a tenant."""
        from spectryn.cli.tenant import _cmd_tenant_delete

        args = argparse.Namespace(id="test-tenant", force=True, delete_data=False)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_delete(args, mock_console)

            assert result == 0
            mock_console.success.assert_called()

    def test_delete_cancelled(self, mock_console, mock_tenant_manager):
        """Test cancelling tenant deletion."""
        from spectryn.cli.tenant import _cmd_tenant_delete

        args = argparse.Namespace(id="test-tenant", force=False, delete_data=False)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("builtins.input", return_value="no"):
                result = _cmd_tenant_delete(args, mock_console)

            assert result == 0
            mock_console.info.assert_called_with("Cancelled")

    def test_delete_confirmed(self, mock_console, mock_tenant_manager):
        """Test confirming tenant deletion."""
        from spectryn.cli.tenant import _cmd_tenant_delete

        args = argparse.Namespace(id="test-tenant", force=False, delete_data=False)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("builtins.input", return_value="yes"):
                result = _cmd_tenant_delete(args, mock_console)

            assert result == 0
            mock_console.success.assert_called()

    def test_delete_with_data(self, mock_console, mock_tenant_manager):
        """Test deleting tenant with data."""
        from spectryn.cli.tenant import _cmd_tenant_delete

        args = argparse.Namespace(id="test-tenant", force=True, delete_data=True)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_delete(args, mock_console)

            assert result == 0
            mock_tenant_manager.delete_tenant.assert_called_with(
                "test-tenant", delete_data=True, force=True
            )

    def test_delete_error(self, mock_console, mock_tenant_manager):
        """Test delete with error."""
        from spectryn.cli.tenant import _cmd_tenant_delete

        args = argparse.Namespace(id="test-tenant", force=True, delete_data=False)
        mock_tenant_manager.delete_tenant.side_effect = ValueError("Cannot delete")

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_delete(args, mock_console)

            assert result == 1
            mock_console.error.assert_called()


# =============================================================================
# _cmd_tenant_archive Tests
# =============================================================================


class TestCmdTenantArchive:
    """Tests for tenant archive command."""

    def test_archive_success(self, mock_console, mock_tenant_manager):
        """Test archiving a tenant."""
        from spectryn.cli.tenant import _cmd_tenant_archive

        args = argparse.Namespace(id="test-tenant")

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_archive(args, mock_console)

            assert result == 0
            mock_console.success.assert_called()

    def test_archive_not_found(self, mock_console, mock_tenant_manager):
        """Test archiving non-existent tenant."""
        from spectryn.cli.tenant import _cmd_tenant_archive

        args = argparse.Namespace(id="missing")
        mock_tenant_manager.registry.archive.side_effect = KeyError("Not found")

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_archive(args, mock_console)

            assert result == 1
            mock_console.error.assert_called_with("Tenant 'missing' not found")


# =============================================================================
# _cmd_tenant_activate Tests
# =============================================================================


class TestCmdTenantActivate:
    """Tests for tenant activate command."""

    def test_activate_success(self, mock_console, mock_tenant_manager):
        """Test activating a tenant."""
        from spectryn.cli.tenant import _cmd_tenant_activate

        args = argparse.Namespace(id="test-tenant")

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_activate(args, mock_console)

            assert result == 0
            mock_console.success.assert_called()

    def test_activate_not_found(self, mock_console, mock_tenant_manager):
        """Test activating non-existent tenant."""
        from spectryn.cli.tenant import _cmd_tenant_activate

        args = argparse.Namespace(id="missing")
        mock_tenant_manager.registry.activate.side_effect = KeyError("Not found")

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager

            result = _cmd_tenant_activate(args, mock_console)

            assert result == 1
            mock_console.error.assert_called_with("Tenant 'missing' not found")


# =============================================================================
# _cmd_tenant_migrate Tests
# =============================================================================


class TestCmdTenantMigrate:
    """Tests for tenant migrate command."""

    def test_migrate_success(self, mock_console, mock_tenant_manager):
        """Test successful migration."""
        from spectryn.cli.tenant import _cmd_tenant_migrate

        args = argparse.Namespace(
            source="default",
            target="new-tenant",
            include_state=True,
            include_cache=True,
            include_backups=True,
            move=False,
        )

        mock_migrator = MagicMock()
        mock_migrator.migrate_from_default.return_value = {
            "config_files": 5,
            "state_files": 10,
            "cache_files": 3,
            "backup_files": 2,
        }

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.TenantMigrator") as MockMigrator:
                MockMigrator.return_value = mock_migrator

                result = _cmd_tenant_migrate(args, mock_console)

                assert result == 0
                mock_console.success.assert_called_with("Migration complete!")

    def test_migrate_with_move(self, mock_console, mock_tenant_manager):
        """Test migration with move mode."""
        from spectryn.cli.tenant import _cmd_tenant_migrate

        args = argparse.Namespace(
            source="default",
            target="new-tenant",
            include_state=False,
            include_cache=False,
            include_backups=False,
            move=True,
        )

        mock_migrator = MagicMock()
        mock_migrator.migrate_from_default.return_value = {
            "config_files": 1,
            "state_files": 0,
            "cache_files": 0,
            "backup_files": 0,
        }

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.TenantMigrator") as MockMigrator:
                MockMigrator.return_value = mock_migrator

                result = _cmd_tenant_migrate(args, mock_console)

                assert result == 0
                mock_migrator.migrate_from_default.assert_called_with(
                    target_tenant_id="new-tenant",
                    include_state=False,
                    include_cache=False,
                    include_backups=False,
                    copy_mode=False,
                )

    def test_migrate_error(self, mock_console, mock_tenant_manager):
        """Test migration with error."""
        from spectryn.cli.tenant import _cmd_tenant_migrate

        args = argparse.Namespace(
            source="default",
            target="bad-tenant",
            include_state=True,
            include_cache=True,
            include_backups=True,
            move=False,
        )

        mock_migrator = MagicMock()
        mock_migrator.migrate_from_default.side_effect = Exception("Migration failed")

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.TenantMigrator") as MockMigrator:
                MockMigrator.return_value = mock_migrator

                result = _cmd_tenant_migrate(args, mock_console)

                assert result == 1
                mock_console.error.assert_called()


# =============================================================================
# _cmd_tenant_status Tests
# =============================================================================


class TestCmdTenantStatus:
    """Tests for tenant status command."""

    def test_status_specific_tenant(self, mock_console, mock_tenant_manager):
        """Test showing status for specific tenant."""
        from spectryn.cli.tenant import _cmd_tenant_status

        args = argparse.Namespace(id="test-tenant", json=False)

        mock_state_query = MagicMock()
        mock_state_query.get_tenant_stats.return_value = {
            "tenant_name": "Test",
            "total_sessions": 10,
            "completed_sessions": 8,
            "failed_sessions": 1,
            "in_progress_sessions": 1,
            "unique_epics": 5,
            "unique_files": 20,
        }

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.CrossTenantStateQuery") as MockQuery:
                MockQuery.return_value = mock_state_query

                result = _cmd_tenant_status(args, mock_console)

                assert result == 0
                mock_console.section.assert_called()

    def test_status_not_found(self, mock_console, mock_tenant_manager):
        """Test status for non-existent tenant."""
        from spectryn.cli.tenant import _cmd_tenant_status

        args = argparse.Namespace(id="missing", json=False)

        mock_state_query = MagicMock()
        mock_state_query.get_tenant_stats.return_value = None

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.CrossTenantStateQuery") as MockQuery:
                MockQuery.return_value = mock_state_query

                result = _cmd_tenant_status(args, mock_console)

                assert result == 1
                mock_console.error.assert_called()

    def test_status_json_output(self, mock_console, mock_tenant_manager):
        """Test status with JSON output."""
        from spectryn.cli.tenant import _cmd_tenant_status

        args = argparse.Namespace(id="test-tenant", json=True)

        mock_state_query = MagicMock()
        mock_state_query.get_tenant_stats.return_value = {
            "tenant_name": "Test",
            "total_sessions": 10,
        }

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.CrossTenantStateQuery") as MockQuery:
                MockQuery.return_value = mock_state_query

                result = _cmd_tenant_status(args, mock_console)

                assert result == 0
                mock_console.print.assert_called()

    def test_status_all_tenants(self, mock_console, mock_tenant_manager, mock_tenant):
        """Test showing status for all tenants."""
        from spectryn.cli.tenant import _cmd_tenant_status

        args = argparse.Namespace(id=None, json=False)

        mock_state_query = MagicMock()
        mock_state_query.get_tenant_stats.return_value = {
            "tenant_name": "Test",
            "total_sessions": 10,
            "completed_sessions": 8,
            "failed_sessions": 1,
            "unique_epics": 5,
        }

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.CrossTenantStateQuery") as MockQuery:
                MockQuery.return_value = mock_state_query

                result = _cmd_tenant_status(args, mock_console)

                assert result == 0
                mock_console.section.assert_called_with("All Tenants Status")

    def test_status_all_tenants_json(self, mock_console, mock_tenant_manager, mock_tenant):
        """Test showing status for all tenants with JSON output."""
        from spectryn.cli.tenant import _cmd_tenant_status

        args = argparse.Namespace(id=None, json=True)

        mock_state_query = MagicMock()
        mock_state_query.get_tenant_stats.return_value = {
            "tenant_name": "Test",
            "total_sessions": 10,
        }

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.CrossTenantStateQuery") as MockQuery:
                MockQuery.return_value = mock_state_query

                result = _cmd_tenant_status(args, mock_console)

                assert result == 0


# =============================================================================
# _cmd_tenant_config Tests
# =============================================================================


class TestCmdTenantConfig:
    """Tests for tenant config command."""

    def test_config_show_path(self, mock_console, mock_tenant_manager, mock_paths):
        """Test showing config paths."""
        from spectryn.cli.tenant import _cmd_tenant_config

        args = argparse.Namespace(id=None, validate=False, show_path=True)

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.TenantConfigManager"):
                result = _cmd_tenant_config(args, mock_console)

                assert result == 0
                mock_console.info.assert_called()

    def test_config_validate_success(self, mock_console, mock_tenant_manager):
        """Test validating config successfully."""
        from spectryn.cli.tenant import _cmd_tenant_config

        args = argparse.Namespace(id="test-tenant", validate=True, show_path=False)

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.TenantConfigManager"):
                with patch("spectryn.core.tenant_config.TenantConfigProvider") as MockProvider:
                    MockProvider.return_value = mock_provider

                    result = _cmd_tenant_config(args, mock_console)

                    assert result == 0
                    mock_console.success.assert_called_with("Configuration is valid")

    def test_config_validate_errors(self, mock_console, mock_tenant_manager):
        """Test validating config with errors."""
        from spectryn.cli.tenant import _cmd_tenant_config

        args = argparse.Namespace(id="test-tenant", validate=True, show_path=False)

        mock_provider = MagicMock()
        mock_provider.validate.return_value = ["Missing API key", "Invalid URL"]

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.TenantConfigManager"):
                with patch("spectryn.core.tenant_config.TenantConfigProvider") as MockProvider:
                    MockProvider.return_value = mock_provider

                    result = _cmd_tenant_config(args, mock_console)

                    assert result == 1
                    mock_console.error.assert_called()

    def test_config_show_status(self, mock_console, mock_tenant_manager):
        """Test showing config status."""
        from spectryn.cli.tenant import _cmd_tenant_config

        args = argparse.Namespace(id=None, validate=False, show_path=False)

        mock_config_manager = MagicMock()
        mock_config_manager.list_tenant_configs.return_value = [
            {
                "tenant_id": "test-tenant",
                "config_file_path": "/path/to/config",
                "has_config_file": True,
                "env_file_path": "/path/to/.env",
                "has_env_file": False,
                "is_valid": True,
                "validation_errors": [],
            }
        ]

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.TenantConfigManager") as MockConfig:
                MockConfig.return_value = mock_config_manager

                result = _cmd_tenant_config(args, mock_console)

                assert result == 0
                mock_console.section.assert_called()

    def test_config_status_not_found(self, mock_console, mock_tenant_manager):
        """Test config status for non-existent tenant."""
        from spectryn.cli.tenant import _cmd_tenant_config

        args = argparse.Namespace(id="missing", validate=False, show_path=False)

        mock_config_manager = MagicMock()
        mock_config_manager.list_tenant_configs.return_value = []

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.TenantConfigManager") as MockConfig:
                MockConfig.return_value = mock_config_manager

                result = _cmd_tenant_config(args, mock_console)

                assert result == 1
                mock_console.error.assert_called()

    def test_config_with_validation_errors(self, mock_console, mock_tenant_manager):
        """Test config status showing validation errors."""
        from spectryn.cli.tenant import _cmd_tenant_config

        args = argparse.Namespace(id=None, validate=False, show_path=False)

        mock_config_manager = MagicMock()
        mock_config_manager.list_tenant_configs.return_value = [
            {
                "tenant_id": "test-tenant",
                "config_file_path": "/path/to/config",
                "has_config_file": True,
                "env_file_path": "/path/to/.env",
                "has_env_file": False,
                "is_valid": False,
                "validation_errors": ["Missing field"],
            }
        ]

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.TenantConfigManager") as MockConfig:
                MockConfig.return_value = mock_config_manager

                result = _cmd_tenant_config(args, mock_console)

                assert result == 0
                mock_console.warning.assert_called()


# =============================================================================
# _cmd_tenant_cache Tests
# =============================================================================


class TestCmdTenantCache:
    """Tests for tenant cache command."""

    def test_cache_clear(self, mock_console, mock_tenant_manager):
        """Test clearing cache."""
        from spectryn.cli.tenant import _cmd_tenant_cache

        args = argparse.Namespace(id=None, clear=True, stats=False)

        mock_cache_store = MagicMock()
        mock_cache_store.clear.return_value = 15

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.TenantCacheStore") as MockCache:
                MockCache.return_value = mock_cache_store

                result = _cmd_tenant_cache(args, mock_console)

                assert result == 0
                mock_console.success.assert_called_with("Cleared 15 cache entries")

    def test_cache_stats(self, mock_console, mock_tenant_manager):
        """Test showing cache statistics."""
        from spectryn.cli.tenant import _cmd_tenant_cache

        args = argparse.Namespace(id=None, clear=False, stats=True)

        mock_cache_store = MagicMock()
        mock_cache_store.get_stats.return_value = {
            "memory_entries": 5,
            "disk_entries": 100,
            "total_hits": 500,
            "disk_usage_bytes": 1024000,
            "max_entries": 1000,
            "default_ttl": 3600,
        }

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.TenantCacheStore") as MockCache:
                MockCache.return_value = mock_cache_store

                result = _cmd_tenant_cache(args, mock_console)

                assert result == 0
                mock_console.section.assert_called()

    def test_cache_basic_info(self, mock_console, mock_tenant_manager):
        """Test showing basic cache info."""
        from spectryn.cli.tenant import _cmd_tenant_cache

        args = argparse.Namespace(id="test-tenant", clear=False, stats=False)

        mock_cache_store = MagicMock()
        mock_cache_store.get_stats.return_value = {"disk_entries": 50}
        mock_cache_store.cache_dir = "/path/to/cache"

        with patch("spectryn.cli.tenant.get_tenant_manager") as mock_get:
            mock_get.return_value = mock_tenant_manager
            with patch("spectryn.cli.tenant.TenantCacheStore") as MockCache:
                MockCache.return_value = mock_cache_store

                result = _cmd_tenant_cache(args, mock_console)

                assert result == 0
                mock_console.info.assert_called()
