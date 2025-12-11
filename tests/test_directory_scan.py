"""Tests for directory scanning functionality"""

import os
import tempfile

import pytest

from rx.file_utils import parse_multiple_files, parse_paths, scan_directory_for_text_files


class TestDirectoryScanning:
    """Test directory scanning for text files"""

    def test_scan_directory_finds_text_files(self):
        """Test that scan_directory_for_text_files finds text files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create text files
            with open(os.path.join(tmpdir, 'file1.txt'), 'w') as f:
                f.write('test content')
            with open(os.path.join(tmpdir, 'file2.log'), 'w') as f:
                f.write('log content')

            text_files, skipped = scan_directory_for_text_files(tmpdir)

            assert len(text_files) == 2
            assert any('file1.txt' in f for f in text_files)
            assert any('file2.log' in f for f in text_files)
            assert len(skipped) == 0

    def test_scan_directory_skips_binary_files(self):
        """Test that binary files are skipped"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create text file
            with open(os.path.join(tmpdir, 'text.txt'), 'w') as f:
                f.write('text content')

            # Create binary file
            with open(os.path.join(tmpdir, 'binary.bin'), 'wb') as f:
                f.write(bytes([0, 1, 2, 255, 254]))

            text_files, skipped = scan_directory_for_text_files(tmpdir)

            assert len(text_files) == 1
            assert 'text.txt' in text_files[0]
            assert len(skipped) == 1
            assert 'binary.bin' in skipped[0]

    def test_scan_directory_recurses_into_subdirectories(self):
        """Test that subdirectories are recursively scanned"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file at root level
            with open(os.path.join(tmpdir, 'root.txt'), 'w') as f:
                f.write('root content')

            # Create 4 levels of nested directories with files
            level1 = os.path.join(tmpdir, 'level1')
            level2 = os.path.join(level1, 'level2')
            level3 = os.path.join(level2, 'level3')
            level4 = os.path.join(level3, 'level4')
            os.makedirs(level4)

            with open(os.path.join(level1, 'file1.txt'), 'w') as f:
                f.write('level 1 content')
            with open(os.path.join(level2, 'file2.txt'), 'w') as f:
                f.write('level 2 content')
            with open(os.path.join(level3, 'file3.txt'), 'w') as f:
                f.write('level 3 content')
            with open(os.path.join(level4, 'file4.txt'), 'w') as f:
                f.write('level 4 content')

            text_files, skipped = scan_directory_for_text_files(tmpdir)

            assert len(text_files) == 5, f'Expected 5 files, got {len(text_files)}: {text_files}'
            assert any('root.txt' in f for f in text_files)
            assert any('file1.txt' in f for f in text_files)
            assert any('file2.txt' in f for f in text_files)
            assert any('file3.txt' in f for f in text_files)
            assert any('file4.txt' in f for f in text_files)

    def test_parse_paths_with_nested_directories(self):
        """Test that parse_paths finds files in nested directories"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            subdir1 = os.path.join(tmpdir, 'src', 'components')
            subdir2 = os.path.join(tmpdir, 'src', 'utils')
            os.makedirs(subdir1)
            os.makedirs(subdir2)

            with open(os.path.join(subdir1, 'button.txt'), 'w') as f:
                f.write('error in button\n')
            with open(os.path.join(subdir2, 'helper.txt'), 'w') as f:
                f.write('error in helper\n')
            with open(os.path.join(tmpdir, 'main.txt'), 'w') as f:
                f.write('error in main\n')

            result = parse_paths([tmpdir], ['error'])

            assert len(result['matches']) == 3, f'Expected 3 matches, got {len(result["matches"])}'
            assert len(result['scanned_files']) == 3


class TestParseMultipleFiles:
    """Test parsing multiple files"""

    def test_parse_multiple_files_basic(self):
        """Test basic multi-file parsing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files with matches
            file1 = os.path.join(tmpdir, 'file1.txt')
            file2 = os.path.join(tmpdir, 'file2.txt')

            with open(file1, 'w') as f:
                f.write('line with error\n')
                f.write('normal line\n')

            with open(file2, 'w') as f:
                f.write('another error here\n')

            matches = parse_multiple_files([file1, file2], 'error')

            assert len(matches) == 2
            assert any(m['filepath'] == file1 for m in matches)
            assert any(m['filepath'] == file2 for m in matches)

    def test_parse_multiple_files_max_results(self):
        """Test max_results with multiple files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            for i in range(3):
                filepath = os.path.join(tmpdir, f'file{i}.txt')
                with open(filepath, 'w') as f:
                    f.write(f'error {i}\nerror {i}\n')
                files.append(filepath)

            # Should stop at max_results
            matches = parse_multiple_files(files, 'error', max_results=3)

            assert len(matches) <= 3


class TestParsePath:
    """Test parse_paths function (file or directory)"""

    def test_parse_path_single_file(self):
        """Test parse_paths with a single file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('error line\nnormal line\n')
            filepath = f.name

        try:
            result = parse_paths([filepath], ['error'])

            # Check ID-based structure
            assert 'patterns' in result
            assert 'files' in result
            assert 'matches' in result
            assert len(result['patterns']) == 1  # p1: error
            assert len(result['files']) == 1  # f1: filepath
            assert len(result['matches']) == 1
            # Match has pattern, file, offset
            assert result['matches'][0]['pattern'] == 'p1'
            assert result['matches'][0]['file'] == 'f1'
            assert result['files']['f1'] == filepath
            assert result['scanned_files'] == []
        finally:
            os.unlink(filepath)

    def test_parse_path_directory(self):
        """Test parse_paths with a directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files
            with open(os.path.join(tmpdir, 'file1.txt'), 'w') as f:
                f.write('error here\n')
            with open(os.path.join(tmpdir, 'file2.txt'), 'w') as f:
                f.write('another error\n')

            result = parse_paths([tmpdir], ['error'])

            # Check ID-based structure
            assert len(result['files']) == 2  # f1, f2
            assert len(result['matches']) == 2  # one match per file
            assert len(result['scanned_files']) == 2

    def test_parse_path_directory_with_binary(self):
        """Test parse_paths directory skips binary files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Text file
            with open(os.path.join(tmpdir, 'text.txt'), 'w') as f:
                f.write('error\n')

            # Binary file
            with open(os.path.join(tmpdir, 'binary.bin'), 'wb') as f:
                f.write(bytes([0, 1, 2, 255]))

            result = parse_paths([tmpdir], ['error'])

            assert len(result['scanned_files']) == 1
            assert len(result['skipped_files']) == 1
            assert 'binary.bin' in result['skipped_files'][0]

    def test_parse_path_nonexistent(self):
        """Test parse_paths with nonexistent path"""
        with pytest.raises(FileNotFoundError):
            parse_paths(['/nonexistent/path'], ['error'])
