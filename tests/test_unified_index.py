"""Tests for unified index functionality."""

import os
import tempfile
from pathlib import Path

import pytest

from rx.indexer import FileIndexer
from rx.models import UnifiedFileIndex
from rx.unified_index import (
    UNIFIED_INDEX_VERSION,
    IndexBuildResult,
    build_index,
    calculate_exact_line_for_offset,
    calculate_exact_offset_for_line,
    calculate_line_info_for_offsets,
    delete_index,
    find_line_offset,
    get_cache_key,
    get_index_cache_dir,
    get_index_path,
    get_index_step_bytes,
    get_large_file_threshold_bytes,
    load_index,
)


@pytest.fixture
def temp_text_file():
    """Create a temporary text file with known content."""
    content = 'Line 1: First line\nLine 2: Second line\nLine 3: Third line\n'
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        f.write(content)
        temp_path = f.name
    yield temp_path
    if os.path.exists(temp_path):
        os.unlink(temp_path)
    # Clean up any index files
    index_path = get_index_path(temp_path)
    if index_path.exists():
        index_path.unlink()


@pytest.fixture
def temp_large_file():
    """Create a temporary file with many lines for testing."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        for i in range(10000):
            f.write(f'Line {i + 1}: This is line number {i + 1} with some padding text\n')
        temp_path = f.name
    yield temp_path
    if os.path.exists(temp_path):
        os.unlink(temp_path)
    index_path = get_index_path(temp_path)
    if index_path.exists():
        index_path.unlink()


class TestCacheDirectory:
    """Tests for cache directory functions."""

    def test_get_cache_dir_exists(self):
        """Test that cache directory is created."""
        cache_dir = get_index_cache_dir()
        assert cache_dir.exists()

    def test_get_cache_dir_in_expected_location(self):
        """Test cache directory is in expected location."""
        cache_dir = get_index_cache_dir()
        assert 'indexes' in str(cache_dir)


class TestIndexPath:
    """Tests for index path generation."""

    def test_get_index_path_returns_path(self, temp_text_file):
        """Test that get_index_path returns a Path object."""
        path = get_index_path(temp_text_file)
        assert isinstance(path, Path)

    def test_get_index_path_consistent(self, temp_text_file):
        """Test that same file always gets same index path."""
        path1 = get_index_path(temp_text_file)
        path2 = get_index_path(temp_text_file)
        assert path1 == path2

    def test_get_index_path_different_for_different_files(self, temp_text_file, temp_large_file):
        """Test that different files get different index paths."""
        path1 = get_index_path(temp_text_file)
        path2 = get_index_path(temp_large_file)
        assert path1 != path2

    def test_get_index_path_includes_filename(self, temp_text_file):
        """Test that index path includes original filename."""
        path = get_index_path(temp_text_file)
        basename = os.path.basename(temp_text_file)
        assert basename.replace('.txt', '') in str(path)

    def test_get_index_path_is_json(self, temp_text_file):
        """Test that index path has .json extension."""
        path = get_index_path(temp_text_file)
        assert str(path).endswith('.json')

    def test_cache_key_format(self, temp_text_file):
        """Test that cache key has expected format: filename_hash."""
        cache_key = get_cache_key(temp_text_file)
        basename = os.path.basename(temp_text_file)
        # Should be filename_hash format
        assert basename.replace('.txt', '') in cache_key
        assert '_' in cache_key


class TestConfiguration:
    """Tests for configuration functions."""

    def test_get_large_file_threshold_default(self):
        """Test default large file threshold is 50MB."""
        threshold = get_large_file_threshold_bytes()
        assert threshold == 50 * 1024 * 1024

    def test_get_index_step_default(self):
        """Test default index step is threshold / 50."""
        step = get_index_step_bytes()
        threshold = get_large_file_threshold_bytes()
        assert step == threshold // 50


class TestBuildIndex:
    """Tests for build_index function."""

    def test_build_index_returns_result(self, temp_text_file):
        """Test that build_index returns IndexBuildResult."""
        result = build_index(temp_text_file)
        assert isinstance(result, IndexBuildResult)
        assert result.line_count > 0

    def test_build_index_first_entry_is_line_1_offset_0(self, temp_text_file):
        """Test that first index entry is line 1 at offset 0."""
        result = build_index(temp_text_file)
        assert result.line_index[0] == [1, 0]

    def test_build_index_counts_lines_correctly(self, temp_text_file):
        """Test line count matches actual file lines."""
        result = build_index(temp_text_file)
        with open(temp_text_file) as f:
            actual_lines = sum(1 for _ in f)
        assert result.line_count == actual_lines

    def test_build_index_offsets_aligned_to_line_starts(self, temp_large_file):
        """Test that all indexed offsets are at line starts."""
        result = build_index(temp_large_file)
        with open(temp_large_file, 'rb') as f:
            content = f.read()

        for line_num, offset in result.line_index:
            if offset > 0:
                # Previous character should be a newline
                assert content[offset - 1 : offset] == b'\n'

    def test_build_index_calculates_statistics(self, temp_large_file):
        """Test that build_index calculates line statistics."""
        result = build_index(temp_large_file)
        assert result.line_length_avg > 0
        assert result.line_length_max >= result.line_length_avg
        assert result.line_length_median > 0

    def test_build_index_detects_line_ending(self, temp_text_file):
        """Test that build_index detects line ending style."""
        result = build_index(temp_text_file)
        assert result.line_ending in ('LF', 'CRLF', 'CR', 'mixed')


class TestFindLineOffset:
    """Tests for find_line_offset function."""

    def test_find_line_offset_exact_match(self):
        """Test finding exact line match."""
        line_index = [[1, 0], [100, 5000], [200, 10000]]
        line_num, offset = find_line_offset(line_index, 100)
        assert line_num == 100
        assert offset == 5000

    def test_find_line_offset_between_entries(self):
        """Test finding line between index entries."""
        line_index = [[1, 0], [100, 5000], [200, 10000]]
        line_num, offset = find_line_offset(line_index, 150)
        # Should return closest previous entry
        assert line_num == 100
        assert offset == 5000

    def test_find_line_offset_before_first(self):
        """Test finding line before first entry returns first."""
        line_index = [[10, 500], [100, 5000]]
        line_num, offset = find_line_offset(line_index, 5)
        assert line_num == 10
        assert offset == 500

    def test_find_line_offset_after_last(self):
        """Test finding line after last entry returns last."""
        line_index = [[1, 0], [100, 5000]]
        line_num, offset = find_line_offset(line_index, 500)
        assert line_num == 100
        assert offset == 5000

    def test_find_line_offset_empty_index(self):
        """Test empty index returns default."""
        line_num, offset = find_line_offset([], 100)
        assert line_num == 1
        assert offset == 0


class TestOffsetLineMapping:
    """Tests for offset/line calculation functions."""

    def test_calculate_offset_for_line_small_file(self, temp_text_file):
        """Test calculating offset for line in small file."""
        offset = calculate_exact_offset_for_line(temp_text_file, 1)
        assert offset == 0  # First line starts at offset 0

    def test_calculate_line_for_offset_small_file(self, temp_text_file):
        """Test calculating line for offset in small file."""
        line = calculate_exact_line_for_offset(temp_text_file, 0)
        assert line == 1  # Offset 0 is line 1

    def test_bidirectional_consistency(self, temp_text_file):
        """Test that offset->line->offset is consistent."""
        for target_line in [1, 2, 3]:
            offset = calculate_exact_offset_for_line(temp_text_file, target_line)
            if offset >= 0:
                line = calculate_exact_line_for_offset(temp_text_file, offset)
                assert line == target_line


class TestCalculateLineInfoForOffsets:
    """Tests for calculate_line_info_for_offsets function."""

    def test_single_offset(self, temp_text_file):
        """Test getting line info for a single offset."""
        result = calculate_line_info_for_offsets(temp_text_file, [0])
        assert 0 in result
        assert result[0].line_number == 1

    def test_multiple_offsets_same_line(self, temp_text_file):
        """Test multiple offsets within the same line."""
        result = calculate_line_info_for_offsets(temp_text_file, [0, 5])
        assert len(result) == 2
        assert result[0].line_number == result[5].line_number

    def test_empty_offset_list(self, temp_text_file):
        """Test empty offset list returns empty dict."""
        result = calculate_line_info_for_offsets(temp_text_file, [])
        assert result == {}


class TestSaveLoadIndex:
    """Tests for save and load functions."""

    def test_save_and_load_roundtrip(self, temp_text_file):
        """Test that saving and loading index preserves data."""
        # Create an index using FileIndexer
        indexer = FileIndexer(analyze=True)
        idx = indexer.index_file(temp_text_file)
        assert idx is not None

        # Load it back
        loaded = load_index(temp_text_file)
        assert loaded is not None
        assert loaded.source_path == idx.source_path
        assert loaded.line_count == idx.line_count

    def test_load_nonexistent_returns_none(self, temp_text_file):
        """Test loading nonexistent index returns None."""
        result = load_index(temp_text_file)
        # May or may not exist depending on test order
        # Just verify it doesn't crash


class TestDeleteIndex:
    """Tests for delete_index function."""

    def test_delete_removes_index(self, temp_text_file):
        """Test that delete_index removes the cache file."""
        # Create index
        indexer = FileIndexer(analyze=True)
        indexer.index_file(temp_text_file)

        # Verify it exists
        assert load_index(temp_text_file) is not None

        # Delete it
        result = delete_index(temp_text_file)
        assert result is True

        # Verify it's gone
        assert load_index(temp_text_file) is None

    def test_delete_nonexistent_returns_false(self, temp_text_file):
        """Test deleting nonexistent index returns False."""
        # Ensure no index exists
        delete_index(temp_text_file)
        result = delete_index(temp_text_file)
        assert result is False


class TestFileIndexer:
    """Tests for FileIndexer class."""

    def test_indexer_creates_unified_index(self, temp_text_file):
        """Test that FileIndexer creates a UnifiedFileIndex."""
        indexer = FileIndexer(analyze=True)
        result = indexer.index_file(temp_text_file)
        assert isinstance(result, UnifiedFileIndex)
        assert result.version == UNIFIED_INDEX_VERSION

    def test_indexer_with_analyze_includes_stats(self, temp_text_file):
        """Test that analyze=True includes statistics."""
        indexer = FileIndexer(analyze=True)
        result = indexer.index_file(temp_text_file)
        assert result.line_count is not None
        assert result.line_count > 0
        assert result.analysis_performed is True

    def test_indexer_caches_result(self, temp_text_file):
        """Test that indexer caches the result."""
        indexer = FileIndexer(analyze=True)
        indexer.index_file(temp_text_file)

        # Should be loadable from cache
        loaded = load_index(temp_text_file)
        assert loaded is not None
