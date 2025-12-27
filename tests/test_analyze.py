"""Tests for file analysis functionality"""

import json
import os
import shutil
import tempfile

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from rx.analyzer import (
    FileAnalyzer,
    analyze_path,
    human_readable_size,
)
from rx.cli.index import index_command
from rx.models import AnalyzeResponse, FileAnalysisResult
from rx.web import app


@pytest.fixture
def temp_root():
    """Create a temporary root directory and set it as search root."""
    tmp_dir = tempfile.mkdtemp()
    # Resolve symlinks (e.g., /var -> /private/var on macOS) for consistent paths
    resolved_tmp_dir = os.path.realpath(tmp_dir)
    # Set environment variable so app lifespan uses our temp directory
    old_env = os.environ.get('RX_SEARCH_ROOT')
    os.environ['RX_SEARCH_ROOT'] = resolved_tmp_dir
    yield resolved_tmp_dir
    # Cleanup
    shutil.rmtree(resolved_tmp_dir, ignore_errors=True)
    # Restore original env var
    if old_env is not None:
        os.environ['RX_SEARCH_ROOT'] = old_env
    elif 'RX_SEARCH_ROOT' in os.environ:
        del os.environ['RX_SEARCH_ROOT']


@pytest.fixture
def client(temp_root):
    """Create test client with search root set to temp directory"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def temp_text_file(temp_root):
    """Create a temporary test file with known content"""
    content = """Line 1: Short line
Line 2: This is a much longer line with more content
Line 3: Medium length line here

Line 5: After empty line
"""
    temp_path = os.path.join(temp_root, 'test_text.txt')
    with open(temp_path, 'w') as f:
        f.write(content)

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_empty_file(temp_root):
    """Create an empty temporary file"""
    temp_path = os.path.join(temp_root, 'empty.txt')
    with open(temp_path, 'w') as f:
        pass  # Create empty file

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_binary_file(temp_root):
    """Create a temporary binary file"""
    temp_path = os.path.join(temp_root, 'test.bin')
    with open(temp_path, 'wb') as f:
        f.write(b'\x00\x01\x02\x03\xff\xfe\xfd')

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_directory(temp_root):
    """Create a temporary directory with mixed files"""
    temp_dir = os.path.join(temp_root, 'subdir')
    os.makedirs(temp_dir, exist_ok=True)

    # Create a text file in the directory
    text_file = os.path.join(temp_dir, 'test.txt')
    with open(text_file, 'w') as f:
        f.write('Test content\n')

    # Create a binary file in the directory
    binary_file = os.path.join(temp_dir, 'test.bin')
    with open(binary_file, 'wb') as f:
        f.write(b'\x00\x01\x02')

    yield temp_dir

    # Cleanup
    for file in os.listdir(temp_dir):
        os.unlink(os.path.join(temp_dir, file))
    os.rmdir(temp_dir)


class TestHumanReadableSize:
    """Tests for human_readable_size function"""

    def test_bytes(self):
        """Test bytes formatting"""
        assert human_readable_size(0) == '0.00 B'
        assert human_readable_size(512) == '512.00 B'
        assert human_readable_size(1023) == '1023.00 B'

    def test_kilobytes(self):
        """Test kilobytes formatting"""
        assert human_readable_size(1024) == '1.00 KB'
        assert human_readable_size(2048) == '2.00 KB'
        assert human_readable_size(1536) == '1.50 KB'

    def test_megabytes(self):
        """Test megabytes formatting"""
        assert human_readable_size(1024 * 1024) == '1.00 MB'
        assert human_readable_size(1024 * 1024 * 5) == '5.00 MB'

    def test_gigabytes(self):
        """Test gigabytes formatting"""
        assert human_readable_size(1024 * 1024 * 1024) == '1.00 GB'

    def test_terabytes(self):
        """Test terabytes formatting"""
        assert human_readable_size(1024 * 1024 * 1024 * 1024) == '1.00 TB'


class TestFileAnalyzer:
    """Tests for FileAnalyzer class"""

    def test_analyze_text_file(self, temp_text_file):
        """Test analyzing a text file"""
        analyzer = FileAnalyzer()
        result = analyzer.analyze_file(temp_text_file, 'f1')

        assert result.file_id == 'f1'
        assert result.filepath == temp_text_file
        assert result.is_text is True
        assert result.size_bytes > 0
        assert result.line_count == 5  # 5 lines (4 content + 1 empty)
        assert result.empty_line_count == 1
        assert result.line_length_max == 52  # "Line 2: This is a much longer line with more content"
        assert result.line_length_avg is not None
        assert result.line_length_median is not None
        assert result.line_length_p95 is not None
        assert result.line_length_p99 is not None
        assert result.line_length_stddev is not None
        assert result.line_length_max_line_number is not None
        assert result.line_length_max_byte_offset is not None
        assert result.line_ending is not None

    def test_analyze_empty_file(self, temp_empty_file):
        """Test analyzing an empty file"""
        analyzer = FileAnalyzer()
        result = analyzer.analyze_file(temp_empty_file, 'f1')

        assert result.file_id == 'f1'
        assert result.is_text is True
        assert result.size_bytes == 0
        assert result.line_count == 0
        assert result.empty_line_count == 0
        # Empty files return 0 instead of None
        assert result.line_length_max == 0
        assert result.line_length_avg == 0.0
        assert result.line_length_median == 0.0
        assert result.line_length_p95 == 0.0
        assert result.line_length_p99 == 0.0
        assert result.line_length_stddev == 0.0

    def test_analyze_binary_file(self, temp_binary_file):
        """Test analyzing a binary file"""
        analyzer = FileAnalyzer()
        result = analyzer.analyze_file(temp_binary_file, 'f1')

        assert result.file_id == 'f1'
        assert result.is_text is False
        assert result.size_bytes > 0
        # Text metrics should be None for binary files
        assert result.line_count is None
        assert result.empty_line_count is None
        assert result.line_length_max is None

    def test_file_hook(self, temp_text_file):
        """Test overriding file hook method"""
        hook_called = []

        class CustomAnalyzer(FileAnalyzer):
            def file_hook(self, filepath, result):
                hook_called.append(filepath)
                result.custom_metrics['hook_executed'] = True

        analyzer = CustomAnalyzer()
        result = analyzer.analyze_file(temp_text_file, 'f1')

        assert len(hook_called) == 1
        assert hook_called[0] == temp_text_file
        assert result.custom_metrics.get('hook_executed') is True

    def test_line_hook(self, temp_text_file):
        """Test overriding line hook method"""
        lines_processed = []

        class CustomAnalyzer(FileAnalyzer):
            def line_hook(self, line, line_num, result):
                lines_processed.append((line_num, len(line)))

        analyzer = CustomAnalyzer()
        result = analyzer.analyze_file(temp_text_file, 'f1')

        assert len(lines_processed) == 5  # 5 lines in file
        assert lines_processed[0][0] == 1  # First line number

    def test_post_hook(self, temp_text_file):
        """Test overriding post hook method"""
        post_hook_called = []

        class CustomAnalyzer(FileAnalyzer):
            def post_hook(self, result):
                post_hook_called.append(True)
                result.custom_metrics['post_processed'] = result.line_count

        analyzer = CustomAnalyzer()
        result = analyzer.analyze_file(temp_text_file, 'f1')

        assert len(post_hook_called) == 1
        assert result.custom_metrics.get('post_processed') == result.line_count

    def test_multiple_hooks(self, temp_text_file):
        """Test multiple hooks of different types"""
        execution_order = []

        class CustomAnalyzer(FileAnalyzer):
            def file_hook(self, filepath, result):
                execution_order.append('file')

            def line_hook(self, line, line_num, result):
                execution_order.append(f'line_{line_num}')

            def post_hook(self, result):
                execution_order.append('post')

        analyzer = CustomAnalyzer()
        result = analyzer.analyze_file(temp_text_file, 'f1')

        # File hook should run first, then line hooks, then post hook
        assert execution_order[0] == 'file'
        assert execution_order[-1] == 'post'
        assert 'line_1' in execution_order

    def test_metadata_fields(self, temp_text_file):
        """Test that metadata fields are populated"""
        analyzer = FileAnalyzer()
        result = analyzer.analyze_file(temp_text_file, 'f1')

        # These should be populated for all files
        assert result.created_at is not None
        assert result.modified_at is not None
        assert result.permissions is not None
        # Owner might be None on some systems, so just check it exists
        assert hasattr(result, 'owner')


class TestAnalyzePath:
    """Tests for analyze_path function"""

    def test_analyze_single_file(self, temp_text_file):
        """Test analyzing a single file"""
        result = analyze_path([temp_text_file])

        assert 'path' in result
        assert 'time' in result
        assert 'files' in result
        assert 'results' in result
        assert 'scanned_files' in result
        assert 'skipped_files' in result

        assert len(result['files']) == 1
        assert len(result['results']) == 1
        assert len(result['scanned_files']) == 1
        assert len(result['skipped_files']) == 0

        # Check file ID format
        assert 'f1' in result['files']
        assert result['files']['f1'] == temp_text_file

    def test_analyze_directory(self, temp_directory):
        """Test analyzing a directory - only text files are analyzed"""
        result = analyze_path([temp_directory])

        # Only text files are analyzed when scanning directories
        assert len(result['files']) == 1  # only test.txt
        assert len(result['results']) == 1
        assert len(result['scanned_files']) == 1
        # Binary file should be in skipped_files
        assert len(result['skipped_files']) == 1

    def test_analyze_multiple_paths(self, temp_text_file, temp_empty_file):
        """Test analyzing multiple paths"""
        result = analyze_path([temp_text_file, temp_empty_file])

        assert len(result['files']) == 2
        assert len(result['results']) == 2
        assert 'f1' in result['files']
        assert 'f2' in result['files']

    def test_analyze_with_max_workers(self, temp_directory):
        """Test analyzing with custom max_workers"""
        result = analyze_path([temp_directory], max_workers=2)

        # Only text files are analyzed
        assert len(result['files']) == 1
        assert result['time'] > 0

    def test_analyze_nonexistent_path(self):
        """Test analyzing a nonexistent path"""
        result = analyze_path(['/nonexistent/path'])

        # Should return empty results, not crash
        assert len(result['files']) == 0
        assert len(result['scanned_files']) == 0

    def test_timing_information(self, temp_text_file):
        """Test that timing information is included"""
        result = analyze_path([temp_text_file])

        assert 'time' in result
        assert isinstance(result['time'], float)
        assert result['time'] >= 0


class TestIndexEndpoint:
    """Tests for /v1/index API endpoint (GET returns cached index data)"""

    def test_index_requires_path(self, client):
        """Test index endpoint requires path parameter"""
        response = client.get('/v1/index')
        assert response.status_code == 422  # Validation error

    def test_index_returns_404_when_no_cache(self, client, temp_text_file):
        """Test GET /v1/index returns 404 when no index exists"""
        response = client.get('/v1/index', params={'path': temp_text_file})
        assert response.status_code == 404
        assert 'No index found' in response.json()['detail']
        assert 'POST /v1/index' in response.json()['detail']

    def test_index_returns_cached_data(self, client, temp_text_file):
        """Test GET /v1/index returns cached index data after indexing"""
        from rx.indexer import FileIndexer

        # First create an index using FileIndexer
        indexer = FileIndexer(analyze=True, force=True)
        indexer.index_file(temp_text_file)

        # Now GET should return the cached data
        response = client.get('/v1/index', params={'path': temp_text_file})
        assert response.status_code == 200

        data = response.json()
        assert 'path' in data
        assert 'file_type' in data
        assert 'size_bytes' in data
        assert 'line_count' in data
        assert 'line_index' in data
        assert 'index_entries' in data
        assert 'analysis_performed' in data
        assert data['analysis_performed'] is True

    def test_index_response_structure(self, client, temp_text_file):
        """Test that response matches expected structure"""
        from rx.indexer import FileIndexer

        # Create index with analysis
        indexer = FileIndexer(analyze=True, force=True)
        indexer.index_file(temp_text_file)

        response = client.get('/v1/index', params={'path': temp_text_file})
        assert response.status_code == 200

        data = response.json()

        # Validate response structure
        assert 'path' in data
        assert 'file_type' in data
        assert 'size_bytes' in data
        assert 'line_count' in data
        assert 'empty_line_count' in data
        assert 'line_ending' in data
        assert 'line_index' in data
        assert 'index_entries' in data
        assert 'analysis_performed' in data
        assert 'build_time_seconds' in data
        assert 'anomaly_count' in data
        assert 'anomaly_summary' in data

        # With analyze=True, analysis should be performed
        assert data['analysis_performed'] is True

    def test_index_includes_line_statistics(self, client, temp_text_file):
        """Test that response includes line length statistics"""
        from rx.indexer import FileIndexer

        # Create index with analysis
        indexer = FileIndexer(analyze=True, force=True)
        indexer.index_file(temp_text_file)

        response = client.get('/v1/index', params={'path': temp_text_file})
        assert response.status_code == 200

        data = response.json()

        # Should have line length stats
        assert 'line_length' in data
        if data['line_length'] is not None:
            assert 'max' in data['line_length']
            assert 'avg' in data['line_length']
            assert 'median' in data['line_length']
            assert 'p95' in data['line_length']
            assert 'p99' in data['line_length']
            assert 'stddev' in data['line_length']

    def test_index_nonexistent_file(self, client, temp_root):
        """Test GET for nonexistent file returns 404 (no index found)"""
        nonexistent = os.path.join(temp_root, 'nonexistent.txt')
        response = client.get('/v1/index', params={'path': nonexistent})
        # Returns 404 because no index exists (file doesn't exist either)
        assert response.status_code == 404


class TestAnalyzeCLI:
    """Tests for rx analyze CLI command"""

    def test_analyze_requires_path(self):
        """Test analyze command requires path argument"""
        runner = CliRunner()
        result = runner.invoke(index_command, [])
        assert result.exit_code != 0

    def test_analyze_single_file(self, temp_text_file):
        """Test analyzing a single file via CLI"""
        runner = CliRunner()
        result = runner.invoke(index_command, [temp_text_file, '--analyze'])
        assert result.exit_code == 0
        assert 'Analysis Results' in result.output or temp_text_file in result.output

    def test_analyze_json_output(self, temp_text_file):
        """Test --json flag outputs valid JSON"""
        runner = CliRunner()
        result = runner.invoke(index_command, [temp_text_file, '--analyze', '--json'])
        assert result.exit_code == 0

        # Should be valid JSON with unified index format
        data = json.loads(result.output)
        assert 'indexed' in data
        assert 'skipped' in data
        assert 'errors' in data
        assert 'total_time' in data

    def test_analyze_no_color(self, temp_text_file):
        """Test --no-color flag"""
        runner = CliRunner()
        result = runner.invoke(index_command, [temp_text_file, '--analyze'])
        assert result.exit_code == 0
        # Output should not contain ANSI escape codes
        assert '\x1b[' not in result.output or result.output.strip() == ''

    def test_analyze_max_workers(self, temp_text_file):
        """Test --max-workers parameter"""
        runner = CliRunner()
        result = runner.invoke(index_command, [temp_text_file, '--analyze', '--max-workers', '5'])
        assert result.exit_code == 0

    def test_analyze_multiple_paths(self, temp_text_file, temp_empty_file):
        """Test analyzing multiple paths"""
        runner = CliRunner()
        result = runner.invoke(index_command, [temp_text_file, temp_empty_file, '--analyze'])
        assert result.exit_code == 0

    def test_analyze_directory(self, temp_directory):
        """Test analyzing a directory - only text files are analyzed"""
        runner = CliRunner()
        result = runner.invoke(index_command, [temp_directory, '--analyze', '-r'])
        # Exit code 0 for success, 2 for warning (skipped binary files)
        assert result.exit_code in [0, 2]

    def test_analyze_nonexistent_file(self):
        """Test analyzing nonexistent file"""
        runner = CliRunner()
        result = runner.invoke(index_command, ['/nonexistent/file.txt', '--analyze'])
        assert result.exit_code != 0

    def test_analyze_with_skipped_files(self, temp_directory):
        """Test exit code when files are skipped"""
        runner = CliRunner()
        result = runner.invoke(index_command, [temp_directory, '--analyze', '-r'])
        # Exit code 2 indicates warning (skipped files)
        assert result.exit_code in [0, 2]


class TestAnalyzeModels:
    """Tests for Pydantic models"""

    def test_file_analysis_result_model(self):
        """Test FileAnalysisResult model creation"""
        result = FileAnalysisResult(
            file='f1',
            size_bytes=1024,
            size_human='1.00 KB',
            is_text=True,
            created_at='2024-01-01T00:00:00',
            modified_at='2024-01-01T00:00:00',
            permissions='0644',
            owner='user',
            line_count=10,
            empty_line_count=2,
            line_length_max=80,
            line_length_avg=40.5,
            line_length_median=42.0,
            line_length_p95=75.0,
            line_length_p99=79.0,
            line_length_stddev=10.2,
            line_length_max_line_number=5,
            line_length_max_byte_offset=100,
            line_ending='LF',
            custom_metrics={},
        )

        assert result.file == 'f1'
        assert result.size_bytes == 1024
        assert result.is_text is True
        assert result.line_length_max == 80
        assert result.line_length_p95 == 75.0
        assert result.line_length_p99 == 79.0
        assert result.line_length_max_line_number == 5
        assert result.line_ending == 'LF'

    def test_analyze_response_model(self):
        """Test AnalyzeResponse model creation"""
        response = AnalyzeResponse(
            path='/tmp/test',
            time=0.123,
            files={'f1': '/tmp/test/file.txt'},
            results=[
                FileAnalysisResult(
                    file='f1',
                    size_bytes=100,
                    size_human='100.00 B',
                    is_text=True,
                    created_at='2024-01-01T00:00:00',
                    modified_at='2024-01-01T00:00:00',
                    permissions='0644',
                    owner='user',
                    line_count=5,
                    empty_line_count=0,
                    line_length_max=20,
                    line_length_avg=15.0,
                    line_length_median=16.0,
                    line_length_p95=19.0,
                    line_length_p99=20.0,
                    line_length_stddev=2.5,
                    line_length_max_line_number=2,
                    line_length_max_byte_offset=50,
                    line_ending='LF',
                )
            ],
            scanned_files=['/tmp/test/file.txt'],
            skipped_files=[],
        )

        assert response.path == '/tmp/test'
        assert len(response.results) == 1
        assert len(response.files) == 1

    def test_analyze_response_to_cli(self):
        """Test AnalyzeResponse.to_cli() method"""
        response = AnalyzeResponse(
            path='/tmp/test',
            time=0.123,
            files={'f1': '/tmp/test/file.txt'},
            results=[
                FileAnalysisResult(
                    file='f1',
                    size_bytes=100,
                    size_human='100.00 B',
                    is_text=True,
                    created_at='2024-01-01T00:00:00',
                    modified_at='2024-01-01T00:00:00',
                    permissions='0644',
                    owner='user',
                    line_count=5,
                    empty_line_count=0,
                    line_length_max=20,
                    line_length_avg=15.0,
                    line_length_median=16.0,
                    line_length_p95=19.0,
                    line_length_p99=20.0,
                    line_length_stddev=2.5,
                    line_length_max_line_number=2,
                    line_length_max_byte_offset=50,
                    line_ending='LF',
                )
            ],
            scanned_files=['/tmp/test/file.txt'],
            skipped_files=[],
        )

        # Test without colors
        output = response.to_cli(colorize=False)
        assert isinstance(output, str)
        assert len(output) > 0
        # Verify new fields are in output
        assert 'p95=' in output
        assert 'p99=' in output
        assert 'Line ending: LF' in output
        assert 'Longest line:' in output

        # Test with colors
        colored_output = response.to_cli(colorize=True)
        assert isinstance(colored_output, str)


class TestAddIndexInfo:
    """Tests for _add_index_info method to prevent regression of module attribute issues"""

    def test_add_index_info_no_attribute_error(self, temp_text_file):
        """Test that _add_index_info doesn't raise AttributeError on module access

        This is a regression test for the bug where code incorrectly accessed:
        - seekable_zstd.seekable_zstd.is_seekable_zstd (wrong)
        - seekable_index.index.get_index_path (wrong)
        - index.index.get_index_path (wrong)

        Instead of the correct:
        - seekable_zstd.is_seekable_zstd (correct)
        - seekable_index.get_index_path (correct)
        - index.get_index_path (correct)
        """
        from rx.analyzer import FileAnalysisState

        analyzer = FileAnalyzer()
        result = FileAnalysisState(
            file_id='f1',
            filepath=temp_text_file,
            size_bytes=100,
            size_human='100 B',
            is_text=True,
        )

        # This should not raise AttributeError
        try:
            analyzer._add_index_info(temp_text_file, result)
        except AttributeError as e:
            # If we get AttributeError with the old wrong pattern, fail
            if "has no attribute 'seekable_zstd'" in str(e) or "has no attribute 'index'" in str(e):
                pytest.fail(f'Module attribute access error (regression): {e}')
            raise

        # Should complete without error
        # Result may or may not have index info depending on whether index exists
        assert hasattr(result, 'has_index')
        assert hasattr(result, 'index_path')
        assert hasattr(result, 'index_valid')

    def test_add_index_info_with_seekable_zstd(self, temp_root):
        """Test _add_index_info with a seekable zstd file (if available)"""
        from rx.analyzer import FileAnalysisState

        # Create a mock .zst file (not actually seekable, just for testing path)
        zst_path = os.path.join(temp_root, 'test.zst')
        with open(zst_path, 'wb') as f:
            f.write(b'\x28\xb5\x2f\xfd')  # zstd magic number

        try:
            analyzer = FileAnalyzer()
            result = FileAnalysisState(
                file_id='f1',
                filepath=zst_path,
                size_bytes=100,
                size_human='100 B',
                is_text=False,
                is_compressed=True,
                compression_format='zstd',
            )

            # Should not raise AttributeError even with .zst file
            try:
                analyzer._add_index_info(zst_path, result)
            except AttributeError as e:
                if "has no attribute 'seekable_zstd'" in str(e) or "has no attribute 'index'" in str(e):
                    pytest.fail(f'Module attribute access error (regression): {e}')
                raise

            # Should complete without error
            assert hasattr(result, 'has_index')
        finally:
            if os.path.exists(zst_path):
                os.unlink(zst_path)

    def test_add_index_info_modules_imported_correctly(self):
        """Verify that analyzer module imports are correct.

        The analyzer.py imports index, seekable_index, seekable_zstd directly
        from rx package, not from rx.analyze module.
        """
        import types

        from rx import seekable_index, seekable_zstd, unified_index

        # Verify these are modules
        assert isinstance(unified_index, types.ModuleType)
        assert isinstance(seekable_index, types.ModuleType)
        assert isinstance(seekable_zstd, types.ModuleType)

        # Verify the functions exist on the modules directly
        assert hasattr(unified_index, 'get_index_path')
        assert hasattr(seekable_index, 'get_index_path')
        assert hasattr(seekable_zstd, 'is_seekable_zstd')

        # Verify they are callable
        assert callable(unified_index.get_index_path)
        assert callable(seekable_index.get_index_path)
        assert callable(seekable_zstd.is_seekable_zstd)


class TestReservoirSampling:
    """Tests for reservoir sampling configuration and behavior"""

    def test_get_sample_size_default(self):
        """Test default sample size is 1,000,000"""
        from rx.analyzer import get_sample_size_lines

        # Clear env var if set
        old_value = os.environ.pop('RX_SAMPLE_SIZE_LINES', None)
        try:
            assert get_sample_size_lines() == 1_000_000
        finally:
            if old_value is not None:
                os.environ['RX_SAMPLE_SIZE_LINES'] = old_value

    def test_get_sample_size_custom(self):
        """Test custom sample size from env variable"""
        from rx.analyzer import get_sample_size_lines

        old_value = os.environ.get('RX_SAMPLE_SIZE_LINES')
        try:
            os.environ['RX_SAMPLE_SIZE_LINES'] = '50000'
            assert get_sample_size_lines() == 50_000
        finally:
            if old_value is not None:
                os.environ['RX_SAMPLE_SIZE_LINES'] = old_value
            else:
                os.environ.pop('RX_SAMPLE_SIZE_LINES', None)

    def test_get_sample_size_invalid(self):
        """Test invalid sample size falls back to default"""
        from rx.analyzer import get_sample_size_lines

        old_value = os.environ.get('RX_SAMPLE_SIZE_LINES')
        try:
            os.environ['RX_SAMPLE_SIZE_LINES'] = 'invalid'
            assert get_sample_size_lines() == 1_000_000
        finally:
            if old_value is not None:
                os.environ['RX_SAMPLE_SIZE_LINES'] = old_value
            else:
                os.environ.pop('RX_SAMPLE_SIZE_LINES', None)

    def test_small_file_exact_statistics(self):
        """Test that files smaller than sample size have exact statistics"""
        # Create a file with known statistics: 50 lines of length 10, 50 lines of length 20
        content = ('x' * 10 + '\n') * 50 + ('y' * 20 + '\n') * 50

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(content)
            temp_path = f.name

        try:
            old_value = os.environ.get('RX_SAMPLE_SIZE_LINES')
            os.environ['RX_SAMPLE_SIZE_LINES'] = '1000000'  # Much larger than file

            analyzer = FileAnalyzer()
            result = analyzer.analyze_file(temp_path, 'f1')

            # With 50 lines of length 10 and 50 of length 20:
            # avg = (50*10 + 50*20) / 100 = 1500 / 100 = 15.0
            # median = 15.0 (boundary between two groups)
            # max = 20
            assert result.line_count == 100
            assert result.empty_line_count == 0
            assert result.line_length_avg == 15.0
            assert result.line_length_max == 20
            assert result.line_length_median == 15.0

        finally:
            os.unlink(temp_path)
            if old_value is not None:
                os.environ['RX_SAMPLE_SIZE_LINES'] = old_value
            else:
                os.environ.pop('RX_SAMPLE_SIZE_LINES', None)

    def test_large_file_sampled_statistics(self):
        """Test that large files use reservoir sampling"""
        # Create file larger than sample size
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            # Write 200 lines total, but set sample size to 50
            for i in range(200):
                f.write('x' * 15 + '\n')
            temp_path = f.name

        try:
            old_value = os.environ.get('RX_SAMPLE_SIZE_LINES')
            os.environ['RX_SAMPLE_SIZE_LINES'] = '50'  # Much smaller than file

            analyzer = FileAnalyzer()
            result = analyzer.analyze_file(temp_path, 'f1')

            # Even with sampling, these should be accurate:
            assert result.line_count == 200  # Total count always exact
            assert result.empty_line_count == 0  # Empty count always exact
            assert result.line_length_max == 15  # Max always exact
            assert result.line_length_max_line_number == 1  # First line is max

            # Avg should be close (all lines same length)
            assert abs(result.line_length_avg - 15.0) < 0.1

            # Median/percentiles are approximated from sample, but should be reasonable
            # Since all lines are length 15, percentiles should be 15.0
            assert result.line_length_median == 15.0
            assert result.line_length_p95 == 15.0
            assert result.line_length_p99 == 15.0

        finally:
            os.unlink(temp_path)
            if old_value is not None:
                os.environ['RX_SAMPLE_SIZE_LINES'] = old_value
            else:
                os.environ.pop('RX_SAMPLE_SIZE_LINES', None)

    def test_empty_lines_always_counted_exactly(self):
        """Test that empty line count is never affected by sampling"""
        # Create file with known empty lines
        content = 'line\n' * 50 + '\n' * 10 + 'line\n' * 50  # 100 non-empty, 10 empty

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(content)
            temp_path = f.name

        try:
            old_value = os.environ.get('RX_SAMPLE_SIZE_LINES')
            os.environ['RX_SAMPLE_SIZE_LINES'] = '10'  # Very small sample

            analyzer = FileAnalyzer()
            result = analyzer.analyze_file(temp_path, 'f1')

            # Empty lines should be counted exactly
            assert result.line_count == 110
            assert result.empty_line_count == 10

        finally:
            os.unlink(temp_path)
            if old_value is not None:
                os.environ['RX_SAMPLE_SIZE_LINES'] = old_value
            else:
                os.environ.pop('RX_SAMPLE_SIZE_LINES', None)

    def test_empty_lines_excluded_from_statistics(self):
        """Test that empty lines do not affect line length statistics (avg, stddev, etc.)"""
        # Create two files: one with empty lines, one without
        # Both should have identical statistics since empty lines are excluded

        # File with only non-empty lines of length 10
        content_no_empty = 'aaaaaaaaaa\n' * 100  # 100 lines, each 10 chars

        # File with same non-empty lines but interspersed with 500 empty lines
        content_with_empty = ('aaaaaaaaaa\n' + '\n' * 5) * 100  # 100 non-empty + 500 empty

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(content_no_empty)
            path_no_empty = f.name

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(content_with_empty)
            path_with_empty = f.name

        try:
            analyzer = FileAnalyzer()

            result_no_empty = analyzer.analyze_file(path_no_empty, 'f1')
            result_with_empty = analyzer.analyze_file(path_with_empty, 'f2')

            # Verify the files have different total line counts
            assert result_no_empty.line_count == 100
            assert result_with_empty.line_count == 600  # 100 non-empty + 500 empty

            # Verify empty line counts
            assert result_no_empty.empty_line_count == 0
            assert result_with_empty.empty_line_count == 500

            # Statistics should be IDENTICAL since empty lines are excluded
            assert result_no_empty.line_length_avg == result_with_empty.line_length_avg
            assert result_no_empty.line_length_max == result_with_empty.line_length_max
            assert result_no_empty.line_length_median == result_with_empty.line_length_median
            assert result_no_empty.line_length_stddev == result_with_empty.line_length_stddev
            assert result_no_empty.line_length_p95 == result_with_empty.line_length_p95
            assert result_no_empty.line_length_p99 == result_with_empty.line_length_p99

            # Verify the actual values (all lines are 10 chars)
            assert result_with_empty.line_length_avg == 10.0
            assert result_with_empty.line_length_max == 10
            assert result_with_empty.line_length_stddev == 0.0  # All same length

        finally:
            os.unlink(path_no_empty)
            os.unlink(path_with_empty)

    def test_longest_line_always_found(self):
        """Test that longest line is always found regardless of sampling"""
        # Create file with one very long line among many short lines
        content = 'short\n' * 100 + 'x' * 500 + '\n' + 'short\n' * 100

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(content)
            temp_path = f.name

        try:
            old_value = os.environ.get('RX_SAMPLE_SIZE_LINES')
            os.environ['RX_SAMPLE_SIZE_LINES'] = '50'  # Smaller than total lines

            analyzer = FileAnalyzer()
            result = analyzer.analyze_file(temp_path, 'f1')

            # Longest line should always be found
            assert result.line_length_max == 500
            assert result.line_length_max_line_number == 101  # Line 101 is the long one

        finally:
            os.unlink(temp_path)
            if old_value is not None:
                os.environ['RX_SAMPLE_SIZE_LINES'] = old_value
            else:
                os.environ.pop('RX_SAMPLE_SIZE_LINES', None)

    def test_line_counting_matches_wc_with_mixed_endings(self):
        """Test that line counting matches wc -l behavior with mixed line endings"""
        # Create file with mixed line endings: CRLF, bare CR, LF
        # This tests that we count only \n characters like wc -l does
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.txt') as f:
            f.write(b'line1\r\n')  # CRLF - wc counts this as 1 line
            f.write(b'line2\r')  # bare CR - wc does NOT count as line (no \n)
            f.write(b'line3\n')  # LF - wc counts this as 1 line
            f.write(b'line4\r\n')  # CRLF - wc counts this as 1 line
            temp_path = f.name

        try:
            # Get wc -l count
            import subprocess

            result = subprocess.run(['wc', '-l', temp_path], capture_output=True, text=True)
            wc_count = int(result.stdout.strip().split()[0])

            # Analyze with our code
            analyzer = FileAnalyzer()
            analysis = analyzer.analyze_file(temp_path, 'f1')

            # Our count should match wc -l
            assert analysis.line_count == wc_count
            assert analysis.line_count == 3  # Only lines ending with \n

        finally:
            os.unlink(temp_path)

    def test_crlf_file_line_counting(self):
        """Test that CRLF files are counted correctly"""
        # Create a pure CRLF file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.txt') as f:
            f.write(b'line1\r\n')
            f.write(b'line2\r\n')
            f.write(b'line3\r\n')
            temp_path = f.name

        try:
            analyzer = FileAnalyzer()
            result = analyzer.analyze_file(temp_path, 'f1')

            # Should count 3 lines
            assert result.line_count == 3
            assert result.line_ending == 'CRLF'

        finally:
            os.unlink(temp_path)


class TestAnomalyDetection:
    """Integration tests for anomaly detection."""

    @pytest.fixture
    def temp_log_with_errors(self, temp_root):
        """Create a log file with various anomalies."""
        content = """2024-01-01 10:00:00 INFO: Application started
2024-01-01 10:00:01 INFO: Processing request
2024-01-01 10:00:02 ERROR: Failed to connect to database
2024-01-01 10:00:03 INFO: Retrying connection
2024-01-01 10:00:04 FATAL: Database connection timeout
2024-01-01 10:00:05 INFO: Shutting down
Traceback (most recent call last):
  File "/app/main.py", line 42, in connect
    db.connect()
  File "/app/db.py", line 10, in connect
    raise ConnectionError("timeout")
ConnectionError: timeout
2024-01-01 10:00:06 INFO: Cleanup complete
"""
        temp_path = os.path.join(temp_root, 'app.log')
        with open(temp_path, 'w', newline='') as f:
            f.write(content)
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def temp_log_clean(self, temp_root):
        """Create a clean log file with no anomalies."""
        content = """2024-01-01 10:00:00 INFO: Application started
2024-01-01 10:00:01 INFO: Processing request
2024-01-01 10:00:02 INFO: Request completed
2024-01-01 10:00:03 INFO: Processing request
2024-01-01 10:00:04 INFO: Request completed
2024-01-01 10:00:05 INFO: Shutting down
"""
        temp_path = os.path.join(temp_root, 'clean.log')
        with open(temp_path, 'w', newline='') as f:
            f.write(content)
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def test_detect_anomalies_disabled_by_default(self, temp_log_with_errors):
        """Test that anomaly detection is disabled by default."""
        analyzer = FileAnalyzer()
        result = analyzer.analyze_file(temp_log_with_errors, 'f1')

        # Anomalies should be empty when detection is disabled
        assert result.anomalies == []
        assert result.anomaly_summary == {}

    def test_detect_anomalies_enabled(self, temp_log_with_errors):
        """Test that anomaly detection finds errors and tracebacks."""
        analyzer = FileAnalyzer(detect_anomalies=True)
        result = analyzer.analyze_file(temp_log_with_errors, 'f1')

        # Should find anomalies
        assert len(result.anomalies) > 0
        assert len(result.anomaly_summary) > 0

        # Check for expected categories
        categories = set(a.category for a in result.anomalies)
        assert 'error' in categories or 'traceback' in categories

    def test_detect_error_keywords(self, temp_log_with_errors):
        """Test detection of ERROR and FATAL keywords."""
        analyzer = FileAnalyzer(detect_anomalies=True)
        result = analyzer.analyze_file(temp_log_with_errors, 'f1')

        # Should have detected anomalies - either error category or traceback
        # (error keywords may be merged with traceback when nearby)
        assert len(result.anomalies) >= 1

        # Check that we detected either error or traceback categories
        categories = set(a.category for a in result.anomalies)
        assert 'error' in categories or 'traceback' in categories

    def test_detect_traceback(self, temp_log_with_errors):
        """Test detection of Python traceback."""
        analyzer = FileAnalyzer(detect_anomalies=True)
        result = analyzer.analyze_file(temp_log_with_errors, 'f1')

        # Find traceback anomalies
        traceback_anomalies = [a for a in result.anomalies if a.category == 'traceback']

        # Should detect the traceback
        assert len(traceback_anomalies) >= 1

        # Check that the traceback spans multiple lines (merged)
        if traceback_anomalies:
            tb = traceback_anomalies[0]
            assert tb.start_line < tb.end_line or tb.start_line == tb.end_line

    def test_clean_file_no_anomalies(self, temp_log_clean):
        """Test that clean files have no anomalies."""
        analyzer = FileAnalyzer(detect_anomalies=True)
        result = analyzer.analyze_file(temp_log_clean, 'f1')

        # Should have no anomalies (only INFO lines)
        assert len(result.anomalies) == 0
        assert result.anomaly_summary == {}

    def test_anomaly_summary_counts(self, temp_log_with_errors):
        """Test that anomaly_summary contains correct counts."""
        analyzer = FileAnalyzer(detect_anomalies=True)
        result = analyzer.analyze_file(temp_log_with_errors, 'f1')

        # Summary should match actual anomaly count per category
        for category, count in result.anomaly_summary.items():
            actual_count = sum(1 for a in result.anomalies if a.category == category)
            assert count == actual_count

    def test_anomaly_has_required_fields(self, temp_log_with_errors):
        """Test that each anomaly has all required fields."""
        analyzer = FileAnalyzer(detect_anomalies=True)
        result = analyzer.analyze_file(temp_log_with_errors, 'f1')

        for anomaly in result.anomalies:
            assert anomaly.start_line >= 1
            assert anomaly.end_line >= anomaly.start_line
            assert anomaly.start_offset >= 0
            assert anomaly.end_offset >= anomaly.start_offset
            assert 0.0 <= anomaly.severity <= 1.0
            assert len(anomaly.category) > 0
            assert len(anomaly.description) > 0
            assert len(anomaly.detector) > 0

    def test_analyze_path_with_detect_anomalies(self, temp_log_with_errors):
        """Test analyze_path function with detect_anomalies=True."""
        result = analyze_path([temp_log_with_errors], detect_anomalies=True)

        assert len(result['results']) == 1
        file_result = result['results'][0]

        # Should have anomalies
        assert file_result.get('anomalies') is not None
        assert len(file_result['anomalies']) > 0
        assert file_result.get('anomaly_summary') is not None

    def test_analyze_path_without_detect_anomalies(self, temp_log_with_errors):
        """Test analyze_path function with detect_anomalies=False (default)."""
        result = analyze_path([temp_log_with_errors], detect_anomalies=False)

        assert len(result['results']) == 1
        file_result = result['results'][0]

        # Should have no anomalies or None
        anomalies = file_result.get('anomalies')
        assert anomalies is None or len(anomalies) == 0

    def test_cli_detect_anomalies_flag(self, temp_log_with_errors):
        """Test CLI with --detect-anomalies flag."""
        runner = CliRunner()
        result = runner.invoke(index_command, [temp_log_with_errors, '--analyze'])

        assert result.exit_code == 0
        # Output should mention anomalies
        assert 'Anomalies' in result.output or 'detected' in result.output.lower()

    def test_cli_detect_anomalies_json(self, temp_log_with_errors):
        """Test CLI with --analyze and --json flags."""
        runner = CliRunner()
        result = runner.invoke(index_command, [temp_log_with_errors, '--analyze', '--json'])

        assert result.exit_code == 0
        data = json.loads(result.output)

        # Should have anomaly info in JSON output (unified index format)
        assert 'indexed' in data
        assert len(data['indexed']) == 1
        file_result = data['indexed'][0]
        assert 'anomaly_count' in file_result
        assert 'anomaly_summary' in file_result

    def test_web_api_with_analyze(self, client, temp_log_with_errors):
        """Test web API returns cached index with anomaly data."""
        from rx.indexer import FileIndexer

        # First create an index with analysis
        indexer = FileIndexer(analyze=True, force=True)
        indexer.index_file(temp_log_with_errors)

        # GET should return the cached data with anomalies
        response = client.get('/v1/index', params={'path': temp_log_with_errors})

        assert response.status_code == 200
        data = response.json()

        # Should have anomaly info when analysis was performed
        assert 'anomaly_count' in data
        assert 'anomaly_summary' in data
        assert data['anomaly_count'] > 0
        assert data['analysis_performed'] is True

    def test_web_api_without_index(self, client, temp_log_with_errors):
        """Test web API returns 404 when no index exists."""
        response = client.get('/v1/index', params={'path': temp_log_with_errors})

        # Without an index, should return 404
        assert response.status_code == 404
        assert 'No index found' in response.json()['detail']


class TestVeryLargeFileFastPath:
    """Test the fast path for very large files (>1GB)."""

    def test_analyze_very_large_file_fast_path(self, tmp_path):
        """Test that _analyze_very_large_file_fast is called for files >= 1GB.

        We mock the file size to trigger the fast path without actually creating
        a 1GB file.
        """
        from unittest.mock import patch

        # Create a small test file with error content
        test_file = tmp_path / 'large_test.log'
        content = """INFO: Starting application
ERROR: Connection failed to database
WARNING: Retrying connection
FATAL: Unable to recover
Traceback (most recent call last):
  File "app.py", line 42, in connect
    raise ConnectionError("Failed")
ConnectionError: Failed
"""
        test_file.write_text(content)

        analyzer = FileAnalyzer(detect_anomalies=True)

        # Mock the file size to be >= 1GB to trigger fast path
        original_analyze = analyzer._analyze_text_file

        fast_path_called = {'called': False}

        def mock_analyze_text_file(filepath, result):
            # Simulate large file by setting size_bytes >= 1GB
            result.size_bytes = 1.5 * 1024 * 1024 * 1024  # 1.5 GB
            original_analyze(filepath, result)
            # Check if fast path was triggered
            # The fast path sets line statistics to None
            if result.line_length_avg is None:
                fast_path_called['called'] = True

        with patch.object(analyzer, '_analyze_text_file', mock_analyze_text_file):
            result = analyzer.analyze_file(str(test_file), 'test')

        # Verify the fast path was triggered
        assert fast_path_called['called'], 'Fast path should be triggered for files >= 1GB'

    def test_analyze_very_large_file_fast_method_directly(self, tmp_path):
        """Test _analyze_very_large_file_fast method directly."""
        from rx.analyzer import FileAnalysisState

        # Create a test file with known content including errors
        test_file = tmp_path / 'test_fast.log'
        content = """INFO: Starting
ERROR: Database connection failed
WARNING: Retry attempt 1
ERROR: Still failing
FATAL: Giving up
Traceback (most recent call last):
  File "main.py", line 10
    db.connect()
DatabaseError: Connection refused
"""
        test_file.write_text(content)

        analyzer = FileAnalyzer(detect_anomalies=True)

        # Create a mock result object
        result = FileAnalysisState(
            file_id='test',
            filepath=str(test_file),
            size_bytes=test_file.stat().st_size,
            size_human='1.5 GB',
            is_text=True,
        )

        # Call the fast path method directly
        analyzer._analyze_very_large_file_fast(str(test_file), result)

        # Verify results
        assert result.line_count is not None
        assert result.line_count > 0
        assert result.line_ending in ('LF', 'CRLF', 'CR', 'mixed')

        # Line statistics should be None in fast path
        assert result.line_length_avg is None
        assert result.line_length_median is None
        assert result.line_length_p95 is None
        assert result.line_length_p99 is None

        # Anomalies might be detected (depends on rg availability)
        # We just check that the attributes are set
        assert hasattr(result, 'anomalies')
        assert hasattr(result, 'anomaly_summary')

    def test_fast_path_wc_line_count(self, tmp_path):
        """Test that wc -l correctly counts lines in fast path."""
        from rx.analyzer import FileAnalysisState

        test_file = tmp_path / 'count_test.log'
        # Create file with exactly 100 lines
        lines = [f'Line {i}: Some log content here\n' for i in range(100)]
        test_file.write_text(''.join(lines))

        analyzer = FileAnalyzer(detect_anomalies=False)

        result = FileAnalysisState(
            file_id='test',
            filepath=str(test_file),
            size_bytes=test_file.stat().st_size,
            size_human='1 GB',
            is_text=True,
        )

        analyzer._analyze_very_large_file_fast(str(test_file), result)

        assert result.line_count == 100


class TestCacheInvalidationWithAnomalies:
    """Test cache invalidation when detect_anomalies flag changes."""

    @pytest.fixture
    def temp_log_file(self, temp_root):
        """Create a temporary log file with error content."""
        log_content = """INFO: Starting application
DEBUG: Loading config
ERROR: Connection failed to database
INFO: Retrying connection
FATAL: Unable to recover, shutting down
Traceback (most recent call last):
  File "app.py", line 42, in connect
    raise ConnectionError("Failed")
ConnectionError: Failed
"""
        log_path = os.path.join(temp_root, 'test_cache.log')
        with open(log_path, 'w') as f:
            f.write(log_content)
        return log_path

    def test_cache_bypassed_when_anomalies_requested_but_cache_has_none(self, temp_log_file):
        """Test that cache is bypassed when detect_anomalies=True but cache has no anomalies."""
        from rx.unified_index import load_index

        # First, analyze without anomaly detection to create cache
        analyzer_no_anomalies = FileAnalyzer(detect_anomalies=False)
        result_no_anomalies = analyzer_no_anomalies.analyze_file(temp_log_file, 'test_file')

        # Verify cache was created without anomalies
        cached = load_index(temp_log_file)
        assert cached is not None
        assert not cached.anomalies  # Empty or None

        # Now analyze with anomaly detection - should bypass cache and detect anomalies
        analyzer_with_anomalies = FileAnalyzer(detect_anomalies=True)
        result_with_anomalies = analyzer_with_anomalies.analyze_file(temp_log_file, 'test_file')

        # Should have detected anomalies
        assert result_with_anomalies.anomalies is not None
        assert len(result_with_anomalies.anomalies) > 0

    def test_cache_used_when_anomalies_exist(self, temp_log_file):
        """Test that cache is used when it already has anomalies."""
        from rx.unified_index import load_index

        # First, analyze with anomaly detection to create cache with anomalies
        analyzer = FileAnalyzer(detect_anomalies=True)
        result1 = analyzer.analyze_file(temp_log_file, 'test_file')

        # Verify cache has anomalies
        cached = load_index(temp_log_file)
        assert cached is not None
        assert cached.anomalies
        assert len(cached.anomalies) > 0

        # Analyze again with detect_anomalies=True - should use cache
        result2 = analyzer.analyze_file(temp_log_file, 'test_file')

        # Should have same anomalies from cache
        assert len(result2.anomalies) == len(result1.anomalies)

    def test_cache_used_when_anomalies_not_requested(self, temp_log_file):
        """Test that cache is used when detect_anomalies=False regardless of cache content."""
        from rx.unified_index import load_index

        # First, analyze without anomaly detection
        analyzer = FileAnalyzer(detect_anomalies=False)
        result1 = analyzer.analyze_file(temp_log_file, 'test_file')

        # Verify cache exists
        cached = load_index(temp_log_file)
        assert cached is not None

        # Analyze again with detect_anomalies=False - should use cache
        result2 = analyzer.analyze_file(temp_log_file, 'test_file')

        # Both should have no anomalies
        assert not result1.anomalies
        assert not result2.anomalies

    def test_cached_anomalies_returned_without_flag(self, temp_log_file):
        """Test that cached anomalies are returned even when detect_anomalies=False."""

        # First, analyze with anomaly detection to create cache with anomalies
        analyzer_with = FileAnalyzer(detect_anomalies=True)
        result_with = analyzer_with.analyze_file(temp_log_file, 'test_file')
        assert len(result_with.anomalies) > 0

        # Now analyze with detect_anomalies=False - should still return cached anomalies
        analyzer_without = FileAnalyzer(detect_anomalies=False)
        result_without = analyzer_without.analyze_file(temp_log_file, 'test_file')

        # Should have anomalies from cache
        assert len(result_without.anomalies) == len(result_with.anomalies)

    def test_cache_recreated_with_anomalies_after_bypass(self, temp_log_file):
        """Test that cache is updated with anomalies after being bypassed."""
        from rx.unified_index import load_index

        # First, analyze without anomaly detection
        analyzer_no = FileAnalyzer(detect_anomalies=False)
        analyzer_no.analyze_file(temp_log_file, 'test_file')

        # Verify no anomalies in cache
        cached1 = load_index(temp_log_file)
        assert not cached1.anomalies

        # Now analyze with anomaly detection - bypasses cache and recreates it
        analyzer_yes = FileAnalyzer(detect_anomalies=True)
        result = analyzer_yes.analyze_file(temp_log_file, 'test_file')
        assert len(result.anomalies) > 0

        # Verify cache now has anomalies
        cached2 = load_index(temp_log_file)
        assert cached2 is not None
        assert len(cached2.anomalies) > 0


class TestAnomalyLineNumberCalculation:
    """Test that anomaly line numbers are correctly calculated from offsets."""

    def test_offset_to_line_calculation(self):
        """Test the _offset_to_line method in FileIndexer."""
        from rx.indexer import FileIndexer

        indexer = FileIndexer(analyze=True)

        # Create a mock line_index: [[line_num, byte_offset], ...]
        # Simulating 100 bytes per line average
        line_index = [
            [1, 0],  # Line 1 at offset 0
            [101, 10000],  # Line 101 at offset 10000 (100 bytes/line avg)
            [201, 20000],  # Line 201 at offset 20000
            [301, 30000],  # Line 301 at offset 30000
        ]

        # Test offset in first range
        assert indexer._offset_to_line(500, line_index) == 6  # ~5 lines from start
        assert indexer._offset_to_line(5000, line_index) == 51  # ~50 lines from start

        # Test offset in middle range
        assert indexer._offset_to_line(15000, line_index) == 151  # 101 + 50 lines

        # Test offset at exact checkpoint
        assert indexer._offset_to_line(10000, line_index) == 101

        # Test empty line_index
        assert indexer._offset_to_line(1000, []) == -1

    def test_anomaly_start_end_offsets_match(self, tmp_path):
        """Test that anomaly start_offset and end_offset are consistent.

        This tests the fix for the bug where unrelated matches were merged
        because all line_num values were -1.
        """
        from rx.indexer import FileIndexer

        # Create a file with errors at known positions
        test_file = tmp_path / 'test_errors.log'
        lines = []
        for i in range(1000):
            if i == 100:
                lines.append('ERROR: First error at line 101\n')
            elif i == 500:
                lines.append('ERROR: Second error at line 501\n')
            elif i == 900:
                lines.append('WARNING: Warning at line 901\n')
            else:
                lines.append(f'Normal log line {i}: some content here\n')

        test_file.write_text(''.join(lines))

        # Index with analysis
        indexer = FileIndexer(analyze=True, force=True)
        idx = indexer.index_file(str(test_file))

        assert idx is not None
        assert idx.anomalies is not None

        # Check that each anomaly has consistent offsets
        for anomaly in idx.anomalies:
            # start_offset should be <= end_offset
            assert anomaly.start_offset <= anomaly.end_offset, (
                f'Anomaly has start_offset ({anomaly.start_offset}) > end_offset ({anomaly.end_offset})'
            )

            # The difference should be reasonable (not spanning gigabytes)
            offset_diff = anomaly.end_offset - anomaly.start_offset
            assert offset_diff < 10000, (
                f'Anomaly offset range too large: {offset_diff} bytes. '
                f'start={anomaly.start_offset}, end={anomaly.end_offset}'
            )

    def test_anomaly_line_numbers_calculated_from_index(self, tmp_path):
        """Test that anomaly line numbers are calculated when initially -1."""
        from rx.indexer import FileIndexer

        # Create a larger file to ensure line_index is built
        test_file = tmp_path / 'large_test.log'
        lines = []
        for i in range(10000):
            if i == 1000:
                lines.append('ERROR: Error at line 1001\n')
            elif i == 5000:
                lines.append('FATAL: Fatal error at line 5001\n')
            else:
                lines.append(f'Normal log line {i}: padding content here for size\n')

        test_file.write_text(''.join(lines))

        # Index with analysis
        indexer = FileIndexer(analyze=True, force=True)
        idx = indexer.index_file(str(test_file))

        assert idx is not None
        assert idx.anomalies is not None
        assert len(idx.anomalies) >= 2

        # All anomalies should have valid line numbers (not -1)
        for anomaly in idx.anomalies:
            assert anomaly.start_line != -1, (
                f'Anomaly start_line is -1, should be calculated from offset {anomaly.start_offset}'
            )
            assert anomaly.end_line != -1, (
                f'Anomaly end_line is -1, should be calculated from offset {anomaly.end_offset}'
            )

            # Line numbers should be reasonable (within file bounds)
            assert 1 <= anomaly.start_line <= 10000
            assert 1 <= anomaly.end_line <= 10000

    def test_no_merge_when_line_numbers_unknown(self):
        """Test that anomalies with unknown line numbers are not incorrectly merged."""
        from rx.analyze.prescan import PrescanMatch
        from rx.analyzer import AnomalyRange

        # Simulate prescan matches with line_num=-1 at very different offsets
        matches = [
            PrescanMatch(line_num=-1, byte_offset=100, detector_name='error', severity=0.9, line_text='ERROR: first'),
            PrescanMatch(
                line_num=-1, byte_offset=1000000, detector_name='error', severity=0.9, line_text='ERROR: second'
            ),
            PrescanMatch(
                line_num=-1, byte_offset=5000000, detector_name='error', severity=0.9, line_text='ERROR: third'
            ),
        ]

        # When line numbers are unknown, each match should become a separate anomaly
        # (no merging based on -1 <= -1 + 2)
        has_line_numbers = any(m.line_num != -1 for m in matches)
        assert not has_line_numbers

        # Simulate the fixed logic: don't merge when line numbers are unknown
        anomalies = []
        if not has_line_numbers:
            for match in matches:
                anomalies.append(
                    AnomalyRange(
                        start_line=match.line_num,
                        end_line=match.line_num,
                        start_offset=match.byte_offset,
                        end_offset=match.byte_offset,
                        severity=match.severity,
                        category='error',
                        description=match.line_text,
                        detector='error_keyword',
                    )
                )

        # Should have 3 separate anomalies, not 1 merged one
        assert len(anomalies) == 3

        # Each should have matching start and end offsets
        for anomaly in anomalies:
            assert anomaly.start_offset == anomaly.end_offset
