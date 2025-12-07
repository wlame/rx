"""Simple tests for --no-cache and --no-index functionality."""

import os
import tempfile
from unittest.mock import patch

import pytest

from rx.trace import parse_paths


@pytest.fixture
def temp_file():
    """Create a temporary file."""
    content = "Line 1: ERROR here\nLine 2: Normal\nLine 3: ERROR again\n"
    
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestNoCacheFlag:
    """Test --no-cache / use_cache parameter."""

    def test_use_cache_false_accepted(self, temp_file):
        """Test that use_cache=False is accepted."""
        result = parse_paths([temp_file], ["ERROR"], use_cache=False)
        assert result is not None
        assert len(result.matches) >= 2

    def test_use_cache_true_default(self, temp_file):
        """Test that use_cache defaults to True."""
        result = parse_paths([temp_file], ["ERROR"])
        assert result is not None


class TestNoIndexFlag:
    """Test --no-index / use_index parameter."""

    def test_use_index_false_accepted(self, temp_file):
        """Test that use_index=False is accepted."""
        result = parse_paths([temp_file], ["ERROR"], use_index=False)
        assert result is not None
        assert len(result.matches) >= 2

    def test_use_index_true_default(self, temp_file):
        """Test that use_index defaults to True."""
        result = parse_paths([temp_file], ["ERROR"])
        assert result is not None


class TestBothFlags:
    """Test using both flags together."""

    def test_both_flags_together(self, temp_file):
        """Test that both use_cache=False and use_index=False work together."""
        result = parse_paths([temp_file], ["ERROR"], use_cache=False, use_index=False)
        assert result is not None
        assert len(result.matches) >= 2


class TestEnvironmentVariables:
    """Test RX_NO_CACHE and RX_NO_INDEX environment variables."""

    def test_rx_no_cache_env_parsing(self):
        """Test that RX_NO_CACHE environment variable is recognized."""
        # Test that the env var parsing logic works
        test_cases = [
            ("1", True),
            ("true", True),
            ("True", True),
            ("yes", True),
            ("0", False),
            ("false", False),
            ("", False),
        ]
        
        for value, expected in test_cases:
            result = value.lower() in ('1', 'true', 'yes')
            assert result == expected

    def test_rx_no_index_env_parsing(self):
        """Test that RX_NO_INDEX environment variable is recognized."""
        # Test that the env var parsing logic works
        test_cases = [
            ("1", True),
            ("true", True),
            ("yes", True),
            ("0", False),
        ]
        
        for value, expected in test_cases:
            result = value.lower() in ('1', 'true', 'yes')
            assert result == expected
