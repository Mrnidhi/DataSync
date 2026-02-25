"""Tests for datasight.remediation.patcher"""

import os
import tempfile
import shutil

import pytest

from datasight.remediation.patcher import Patcher


class TestPatcher:
    """Test code patching and rollback."""

    def setup_method(self):
        """Create a temp file to patch."""
        from datasight.config.settings import get_settings
        get_settings.cache_clear()

        self.temp_dir = tempfile.mkdtemp()
        self.target_file = os.path.join(self.temp_dir, "test_dag.py")
        self.original_content = '''def my_task():
    result = df.select("user_email")
    return result
'''
        with open(self.target_file, "w") as f:
            f.write(self.original_content)

    def teardown_method(self):
        """Clean up temp files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_apply_patch(self):
        """Should write patched code and create backup."""
        patcher = Patcher()
        patched = '''def my_task():
    result = df.select("email_address")
    return result
'''
        patcher.apply(self.target_file, patched)

        # File should contain patched code
        with open(self.target_file) as f:
            assert "email_address" in f.read()

        # Backup should exist
        backup = f"{self.target_file}.datasight.bak"
        assert os.path.exists(backup)
        with open(backup) as f:
            assert "user_email" in f.read()

    def test_rollback(self):
        """Should restore from backup."""
        patcher = Patcher()
        patcher.apply(self.target_file, "new content")
        assert patcher.rollback(self.target_file) is True

        with open(self.target_file) as f:
            assert f.read() == self.original_content

    def test_rollback_no_backup(self):
        """Should return False when no backup exists."""
        patcher = Patcher()
        assert patcher.rollback(self.target_file) is False

    def test_apply_nonexistent_file(self):
        """Should raise FileNotFoundError for missing files."""
        patcher = Patcher()
        with pytest.raises(FileNotFoundError):
            patcher.apply("/nonexistent/file.py", "code")

    def test_consecutive_patches(self):
        """Should handle consecutive patches (backup always has pre-patch state)."""
        patcher = Patcher()
        patcher.apply(self.target_file, "patch_v1")
        patcher.apply(self.target_file, "patch_v2")

        with open(self.target_file) as f:
            assert f.read() == "patch_v2"

        # Backup should contain the previous patch, not original
        backup = f"{self.target_file}.datasight.bak"
        with open(backup) as f:
            assert f.read() == "patch_v1"
