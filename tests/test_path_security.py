"""Tests for path security validation module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from rx.path_security import (
    get_search_root,
    is_path_within_root,
    set_search_root,
    validate_path_within_root,
    validate_paths_within_root,
)


class TestSetSearchRoot:
    """Tests for set_search_root function."""

    def test_set_search_root_with_valid_directory(self, tmp_path):
        """Test setting search root with valid directory."""
        result = set_search_root(tmp_path)
        assert result == tmp_path.resolve()
        assert get_search_root() == tmp_path.resolve()

    def test_set_search_root_with_none_uses_cwd(self):
        """Test setting search root with None defaults to cwd."""
        result = set_search_root(None)
        assert result == Path.cwd().resolve()

    def test_set_search_root_with_nonexistent_path(self, tmp_path):
        """Test setting search root with non-existent path raises ValueError."""
        nonexistent = tmp_path / "nonexistent"
        with pytest.raises(ValueError, match="does not exist"):
            set_search_root(nonexistent)

    def test_set_search_root_with_file_raises_error(self, tmp_path):
        """Test setting search root with file raises ValueError."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("test")
        with pytest.raises(ValueError, match="not a directory"):
            set_search_root(file_path)

    def test_set_search_root_resolves_symlinks(self, tmp_path):
        """Test that search root resolves symlinks."""
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        link_dir = tmp_path / "link"
        link_dir.symlink_to(real_dir)

        result = set_search_root(link_dir)
        assert result == real_dir.resolve()


class TestValidatePathWithinRoot:
    """Tests for validate_path_within_root function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tmp_dir = tempfile.mkdtemp()
        self.root = Path(self.tmp_dir)
        set_search_root(self.root)

        # Create test structure
        (self.root / "allowed").mkdir()
        (self.root / "allowed" / "file.txt").write_text("test content")
        (self.root / "allowed" / "subdir").mkdir()
        (self.root / "allowed" / "subdir" / "nested.txt").write_text("nested")

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_valid_path_within_root(self):
        """Test valid path within root is accepted."""
        valid_path = self.root / "allowed" / "file.txt"
        result = validate_path_within_root(valid_path)
        assert result == valid_path.resolve()

    def test_valid_nested_path(self):
        """Test valid nested path within root is accepted."""
        valid_path = self.root / "allowed" / "subdir" / "nested.txt"
        result = validate_path_within_root(valid_path)
        assert result == valid_path.resolve()

    def test_path_with_dot_dot_inside_root(self):
        """Test path with ../ that stays inside root is accepted."""
        # Path: /root/allowed/subdir/../file.txt -> /root/allowed/file.txt
        path_with_dots = self.root / "allowed" / "subdir" / ".." / "file.txt"
        result = validate_path_within_root(path_with_dots)
        assert result == (self.root / "allowed" / "file.txt").resolve()

    def test_path_with_dot_dot_escaping_root_raises_error(self):
        """Test path with ../ escaping root raises PermissionError."""
        # Try to escape: /root/../etc/passwd
        escape_path = self.root / ".." / "etc" / "passwd"
        with pytest.raises(PermissionError, match="outside search root"):
            validate_path_within_root(escape_path)

    def test_absolute_path_outside_root_raises_error(self):
        """Test absolute path outside root raises PermissionError."""
        with pytest.raises(PermissionError, match="outside search root"):
            validate_path_within_root("/etc/passwd")

    def test_path_outside_root_raises_permission_error(self):
        """Test path outside root raises PermissionError."""
        outside_path = Path("/tmp/outside")
        with pytest.raises(PermissionError, match="outside search root"):
            validate_path_within_root(outside_path)

    def test_symlink_inside_root_to_file_inside_root(self):
        """Test symlink inside root pointing to file inside root is accepted."""
        target = self.root / "allowed" / "file.txt"
        link = self.root / "allowed" / "link.txt"
        link.symlink_to(target)

        result = validate_path_within_root(link)
        assert result == target.resolve()

    def test_symlink_inside_root_to_file_outside_root_raises_error(self):
        """Test symlink inside root pointing outside root raises PermissionError."""
        # Create a file outside the root
        outside_file = Path(tempfile.mktemp())
        outside_file.write_text("outside content")

        try:
            # Create symlink inside root pointing outside
            link = self.root / "allowed" / "escape_link.txt"
            link.symlink_to(outside_file)

            with pytest.raises(PermissionError, match="outside search root"):
                validate_path_within_root(link)
        finally:
            outside_file.unlink(missing_ok=True)

    def test_symlink_directory_inside_root_to_outside_raises_error(self):
        """Test symlink directory inside root pointing outside raises PermissionError."""
        # Create a directory outside the root
        outside_dir = Path(tempfile.mkdtemp())

        try:
            # Create symlink inside root pointing outside
            link = self.root / "allowed" / "escape_dir"
            link.symlink_to(outside_dir)

            # Try to access file through escaped symlink
            with pytest.raises(PermissionError, match="outside search root"):
                validate_path_within_root(link / "some_file.txt")
        finally:
            import shutil

            shutil.rmtree(outside_dir, ignore_errors=True)

    def test_multiple_dot_dot_escape_attempt(self):
        """Test multiple ../ escape attempts are blocked."""
        # Try: /root/allowed/subdir/../../../etc/passwd
        escape_path = self.root / "allowed" / "subdir" / ".." / ".." / ".." / "etc" / "passwd"
        with pytest.raises(PermissionError, match="outside search root"):
            validate_path_within_root(escape_path)

    def test_relative_path_resolved_from_root(self):
        """Test relative path is resolved relative to search root."""
        # Set up a relative path
        result = validate_path_within_root("allowed/file.txt")
        assert result == (self.root / "allowed" / "file.txt").resolve()

    def test_no_search_root_configured_raises_error(self):
        """Test validation without configured search root raises ValueError."""
        # Temporarily clear search root
        import rx.path_security as ps

        original = ps._search_root
        ps._search_root = None

        try:
            with pytest.raises(ValueError, match="Search root not configured"):
                validate_path_within_root("/some/path")
        finally:
            ps._search_root = original

    def test_custom_search_root_parameter(self):
        """Test using custom search root parameter."""
        custom_root = self.root / "allowed"
        valid_path = custom_root / "file.txt"

        result = validate_path_within_root(valid_path, search_root=custom_root)
        assert result == valid_path.resolve()

        # Should fail with custom root for paths outside it
        outside_custom = self.root / "allowed" / ".." / "other"
        with pytest.raises(PermissionError, match="outside search root"):
            validate_path_within_root(outside_custom, search_root=custom_root)


class TestValidatePathsWithinRoot:
    """Tests for validate_paths_within_root function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tmp_dir = tempfile.mkdtemp()
        self.root = Path(self.tmp_dir)
        set_search_root(self.root)

        # Create test structure
        (self.root / "file1.txt").write_text("file1")
        (self.root / "file2.txt").write_text("file2")
        (self.root / "subdir").mkdir()
        (self.root / "subdir" / "file3.txt").write_text("file3")

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_multiple_valid_paths(self):
        """Test multiple valid paths are all accepted."""
        paths = [
            self.root / "file1.txt",
            self.root / "file2.txt",
            self.root / "subdir" / "file3.txt",
        ]
        results = validate_paths_within_root(paths)
        assert len(results) == 3
        assert all(isinstance(p, Path) for p in results)

    def test_one_invalid_path_raises_error(self):
        """Test that one invalid path in list raises PermissionError."""
        paths = [
            self.root / "file1.txt",
            Path("/etc/passwd"),  # Outside root
            self.root / "file2.txt",
        ]
        with pytest.raises(PermissionError, match="outside search root"):
            validate_paths_within_root(paths)

    def test_empty_list(self):
        """Test empty list returns empty list."""
        result = validate_paths_within_root([])
        assert result == []


class TestIsPathWithinRoot:
    """Tests for is_path_within_root function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tmp_dir = tempfile.mkdtemp()
        self.root = Path(self.tmp_dir)
        set_search_root(self.root)

        (self.root / "valid.txt").write_text("valid")

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_valid_path_returns_true(self):
        """Test valid path returns True."""
        assert is_path_within_root(self.root / "valid.txt") is True

    def test_invalid_path_returns_false(self):
        """Test invalid path returns False."""
        assert is_path_within_root("/etc/passwd") is False

    def test_escape_attempt_returns_false(self):
        """Test escape attempt returns False."""
        assert is_path_within_root(self.root / ".." / "etc" / "passwd") is False


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tmp_dir = tempfile.mkdtemp()
        self.root = Path(self.tmp_dir)
        set_search_root(self.root)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_path_with_spaces(self):
        """Test path with spaces is handled correctly."""
        dir_with_spaces = self.root / "path with spaces"
        dir_with_spaces.mkdir()
        file_path = dir_with_spaces / "file.txt"
        file_path.write_text("content")

        result = validate_path_within_root(file_path)
        assert result == file_path.resolve()

    def test_path_with_special_characters(self):
        """Test path with special characters is handled correctly."""
        special_dir = self.root / "path-with_special.chars"
        special_dir.mkdir()
        file_path = special_dir / "file[1].txt"
        file_path.write_text("content")

        result = validate_path_within_root(file_path)
        assert result == file_path.resolve()

    def test_root_path_itself_is_valid(self):
        """Test that the root path itself is valid."""
        result = validate_path_within_root(self.root)
        assert result == self.root.resolve()

    def test_nonexistent_file_inside_root_is_validated(self):
        """Test that non-existent file inside root passes validation."""
        # The file doesn't exist but the path is within root
        nonexistent = self.root / "nonexistent.txt"
        result = validate_path_within_root(nonexistent)
        assert result == nonexistent.resolve()

    def test_string_path_input(self):
        """Test that string paths are accepted."""
        file_path = self.root / "test.txt"
        file_path.write_text("test")

        result = validate_path_within_root(str(file_path))
        assert result == file_path.resolve()

    def test_deeply_nested_escape_attempt(self):
        """Test deeply nested escape attempt is blocked."""
        # Create deep directory structure
        deep_dir = self.root / "a" / "b" / "c" / "d"
        deep_dir.mkdir(parents=True)

        # Try to escape from deep inside
        escape_path = deep_dir / ".." / ".." / ".." / ".." / ".." / "etc" / "passwd"
        with pytest.raises(PermissionError, match="outside search root"):
            validate_path_within_root(escape_path)
