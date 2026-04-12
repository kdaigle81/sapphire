"""
Backup path safety tests for core/backup.py.

delete_backup() and get_backup_path() are the path-traversal guards for the
backup system. They reject filenames with slashes, non-.gz extensions, and
non-sapphire_ prefixes. If these guards fail, a malicious API call could
delete or read arbitrary files on the filesystem.

Run with: pytest tests/test_backup_safety.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def backup(tmp_path):
    """Create a Backup instance with a temp backup dir and a valid test file."""
    from core.backup import Backup

    with patch.object(Backup, '__init__', lambda self: None):
        b = Backup()
        b.backup_dir = tmp_path
        b._stop_event = None

    # Create a valid backup file for positive tests
    valid = tmp_path / "sapphire_daily_2026-04-12_0300.tar.gz"
    valid.write_bytes(b"fake backup data")

    return b


# ─── delete_backup path traversal guard ─────────────────────────────────────

class TestDeleteBackup:
    def test_rejects_forward_slash(self, backup):
        assert backup.delete_backup("../../etc/passwd") is False

    def test_rejects_backslash(self, backup):
        assert backup.delete_backup("..\\..\\windows\\system32") is False

    def test_rejects_non_gz_extension(self, backup):
        (backup.backup_dir / "sapphire_bad.txt").write_text("nope")
        assert backup.delete_backup("sapphire_bad.txt") is False

    def test_rejects_non_sapphire_prefix(self, backup):
        (backup.backup_dir / "evil_daily_2026.tar.gz").write_bytes(b"data")
        assert backup.delete_backup("evil_daily_2026.tar.gz") is False

    def test_rejects_nonexistent_file(self, backup):
        assert backup.delete_backup("sapphire_ghost_2026.tar.gz") is False

    def test_deletes_valid_backup(self, backup):
        assert backup.delete_backup("sapphire_daily_2026-04-12_0300.tar.gz") is True
        assert not (backup.backup_dir / "sapphire_daily_2026-04-12_0300.tar.gz").exists()


# ─── get_backup_path guard ──────────────────────────────────────────────────

class TestGetBackupPath:
    def test_rejects_forward_slash(self, backup):
        assert backup.get_backup_path("../../../etc/shadow") is None

    def test_rejects_backslash(self, backup):
        assert backup.get_backup_path("..\\secret") is None

    def test_rejects_non_sapphire_prefix(self, backup):
        (backup.backup_dir / "not_a_backup.tar.gz").write_bytes(b"data")
        assert backup.get_backup_path("not_a_backup.tar.gz") is None

    def test_rejects_nonexistent_file(self, backup):
        assert backup.get_backup_path("sapphire_ghost_2026.tar.gz") is None

    def test_returns_valid_path(self, backup):
        path = backup.get_backup_path("sapphire_daily_2026-04-12_0300.tar.gz")
        assert path is not None
        assert path.exists()
