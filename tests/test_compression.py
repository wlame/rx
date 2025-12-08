"""Tests for compression detection and compressed file handling."""

import gzip
import os
import tempfile

import pytest

from rx.compression import (
    COMPOUND_ARCHIVE_SUFFIXES,
    DECOMPRESSOR_COMMANDS,
    EXTENSION_MAP,
    MAGIC_BYTES,
    CompressionFormat,
    check_decompressor_available,
    decompress_file,
    decompress_to_stdout,
    detect_compression,
    detect_compression_by_extension,
    detect_compression_by_magic,
    get_available_decompressors,
    get_decompressed_size,
    get_decompressor_command,
    is_compound_archive,
    is_compressed,
)


@pytest.fixture
def temp_gzip_file():
    """Create a temporary gzip file with known content."""
    content = b"Line 1: First line with ERROR here\nLine 2: Second line ok\nLine 3: Third line WARNING there\n"
    with tempfile.NamedTemporaryFile(delete=False, suffix=".gz") as f:
        temp_path = f.name

    with gzip.open(temp_path, "wb") as gz:
        gz.write(content)

    yield temp_path, content

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_gzip_multiline():
    """Create a temporary gzip file with many lines for index testing."""
    lines = []
    for i in range(1, 1001):
        if i % 100 == 0:
            lines.append(f"Line {i:04d}: ERROR found here\n")
        elif i % 50 == 0:
            lines.append(f"Line {i:04d}: WARNING detected\n")
        else:
            lines.append(f"Line {i:04d}: Normal content here\n")

    content = "".join(lines).encode("utf-8")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".gz") as f:
        temp_path = f.name

    with gzip.open(temp_path, "wb") as gz:
        gz.write(content)

    yield temp_path, content, lines

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_text_file():
    """Create a temporary plain text file."""
    content = b"Line 1: First line\nLine 2: Second line\n"
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestCompressionFormat:
    """Tests for CompressionFormat enum."""

    def test_all_formats_have_values(self):
        """Test that all formats have string values."""
        assert CompressionFormat.NONE.value == "none"
        assert CompressionFormat.GZIP.value == "gzip"
        assert CompressionFormat.ZSTD.value == "zstd"
        assert CompressionFormat.XZ.value == "xz"
        assert CompressionFormat.BZ2.value == "bz2"

    def test_from_string_valid(self):
        """Test creating format from valid string."""
        assert CompressionFormat.from_string("gzip") == CompressionFormat.GZIP
        assert CompressionFormat.from_string("zstd") == CompressionFormat.ZSTD
        assert CompressionFormat.from_string("xz") == CompressionFormat.XZ
        assert CompressionFormat.from_string("bz2") == CompressionFormat.BZ2

    def test_from_string_invalid(self):
        """Test creating format from invalid string returns NONE."""
        assert CompressionFormat.from_string("invalid") == CompressionFormat.NONE
        assert CompressionFormat.from_string("") == CompressionFormat.NONE


class TestDetectionByExtension:
    """Tests for extension-based compression detection."""

    def test_detect_gzip_extensions(self):
        """Test detection of gzip files by extension."""
        assert detect_compression_by_extension("file.gz") == CompressionFormat.GZIP
        assert detect_compression_by_extension("file.gzip") == CompressionFormat.GZIP
        assert detect_compression_by_extension("/path/to/file.gz") == CompressionFormat.GZIP

    def test_detect_zstd_extensions(self):
        """Test detection of zstd files by extension."""
        assert detect_compression_by_extension("file.zst") == CompressionFormat.ZSTD
        assert detect_compression_by_extension("file.zstd") == CompressionFormat.ZSTD

    def test_detect_xz_extension(self):
        """Test detection of xz files by extension."""
        assert detect_compression_by_extension("file.xz") == CompressionFormat.XZ

    def test_detect_bz2_extensions(self):
        """Test detection of bz2 files by extension."""
        assert detect_compression_by_extension("file.bz2") == CompressionFormat.BZ2
        assert detect_compression_by_extension("file.bzip2") == CompressionFormat.BZ2

    def test_detect_no_compression(self):
        """Test detection returns NONE for non-compressed extensions."""
        assert detect_compression_by_extension("file.txt") == CompressionFormat.NONE
        assert detect_compression_by_extension("file.log") == CompressionFormat.NONE
        assert detect_compression_by_extension("file") == CompressionFormat.NONE

    def test_case_insensitive(self):
        """Test extension detection is case insensitive."""
        assert detect_compression_by_extension("file.GZ") == CompressionFormat.GZIP
        assert detect_compression_by_extension("file.Gz") == CompressionFormat.GZIP


class TestDetectionByMagic:
    """Tests for magic byte-based compression detection."""

    def test_detect_gzip_magic(self, temp_gzip_file):
        """Test detection of gzip file by magic bytes."""
        temp_path, _ = temp_gzip_file
        assert detect_compression_by_magic(temp_path) == CompressionFormat.GZIP

    def test_detect_plain_text_magic(self, temp_text_file):
        """Test detection returns NONE for plain text files."""
        assert detect_compression_by_magic(temp_text_file) == CompressionFormat.NONE

    def test_detect_nonexistent_file(self):
        """Test detection handles non-existent files."""
        assert detect_compression_by_magic("/nonexistent/file.gz") == CompressionFormat.NONE


class TestDetectCompression:
    """Tests for the combined detection function."""

    def test_detect_by_extension_first(self, temp_gzip_file):
        """Test that extension is checked first."""
        temp_path, _ = temp_gzip_file
        assert detect_compression(temp_path) == CompressionFormat.GZIP

    def test_detect_falls_back_to_magic(self, temp_gzip_file):
        """Test fallback to magic bytes when extension doesn't match."""
        temp_path, content = temp_gzip_file
        # Rename to remove .gz extension
        new_path = temp_path.replace(".gz", ".log")
        os.rename(temp_path, new_path)
        try:
            assert detect_compression(new_path) == CompressionFormat.GZIP
        finally:
            os.rename(new_path, temp_path)

    def test_detect_plain_text(self, temp_text_file):
        """Test detection of plain text file."""
        assert detect_compression(temp_text_file) == CompressionFormat.NONE


class TestIsCompressed:
    """Tests for is_compressed helper function."""

    def test_is_compressed_true(self, temp_gzip_file):
        """Test is_compressed returns True for compressed files."""
        temp_path, _ = temp_gzip_file
        assert is_compressed(temp_path) is True

    def test_is_compressed_false(self, temp_text_file):
        """Test is_compressed returns False for plain files."""
        assert is_compressed(temp_text_file) is False


class TestDecompressorCommands:
    """Tests for decompressor command generation."""

    def test_get_decompressor_command_gzip(self):
        """Test gzip decompressor command."""
        cmd = get_decompressor_command(CompressionFormat.GZIP)
        assert cmd == ["gzip", "-d", "-c"]

    def test_get_decompressor_command_zstd(self):
        """Test zstd decompressor command."""
        cmd = get_decompressor_command(CompressionFormat.ZSTD)
        assert cmd == ["zstd", "-d", "-c", "-q"]

    def test_get_decompressor_command_xz(self):
        """Test xz decompressor command."""
        cmd = get_decompressor_command(CompressionFormat.XZ)
        assert cmd == ["xz", "-d", "-c"]

    def test_get_decompressor_command_bz2(self):
        """Test bz2 decompressor command."""
        cmd = get_decompressor_command(CompressionFormat.BZ2)
        assert cmd == ["bzip2", "-d", "-c"]

    def test_get_decompressor_command_with_filepath(self):
        """Test decompressor command with filepath appended."""
        cmd = get_decompressor_command(CompressionFormat.GZIP, "/path/to/file.gz")
        assert cmd == ["gzip", "-d", "-c", "/path/to/file.gz"]

    def test_get_decompressor_command_none_raises(self):
        """Test that NONE format raises ValueError."""
        with pytest.raises(ValueError):
            get_decompressor_command(CompressionFormat.NONE)


class TestDecompressorAvailability:
    """Tests for decompressor availability checking."""

    def test_check_gzip_available(self):
        """Test that gzip is typically available."""
        # gzip should be available on most systems
        assert check_decompressor_available(CompressionFormat.GZIP) is True

    def test_check_none_always_available(self):
        """Test that NONE format is always available."""
        assert check_decompressor_available(CompressionFormat.NONE) is True

    def test_get_available_decompressors(self):
        """Test getting availability of all decompressors."""
        available = get_available_decompressors()
        assert "gzip" in available
        assert "zstd" in available
        assert "xz" in available
        assert "bz2" in available
        # gzip should typically be available
        assert available["gzip"] is True


class TestDecompression:
    """Tests for actual decompression functionality."""

    def test_decompress_to_stdout(self, temp_gzip_file):
        """Test decompressing to stdout process."""
        temp_path, expected_content = temp_gzip_file
        proc = decompress_to_stdout(temp_path)
        output = proc.stdout.read()
        proc.wait()
        assert output == expected_content

    def test_decompress_file(self, temp_gzip_file):
        """Test decompressing entire file to bytes."""
        temp_path, expected_content = temp_gzip_file
        output = decompress_file(temp_path)
        assert output == expected_content

    def test_decompress_noncompressed_raises(self, temp_text_file):
        """Test that decompressing plain text raises ValueError."""
        with pytest.raises(ValueError):
            decompress_to_stdout(temp_text_file)

    def test_decompress_auto_detect(self, temp_gzip_file):
        """Test decompression with auto-detection."""
        temp_path, expected_content = temp_gzip_file
        # Don't specify format, let it auto-detect
        output = decompress_file(temp_path)
        assert output == expected_content


class TestGetDecompressedSize:
    """Tests for decompressed size estimation."""

    def test_get_gzip_decompressed_size(self, temp_gzip_file):
        """Test getting decompressed size from gzip file."""
        temp_path, expected_content = temp_gzip_file
        size = get_decompressed_size(temp_path, CompressionFormat.GZIP)
        # gzip stores size mod 2^32, so for small files this should be exact
        assert size == len(expected_content)

    def test_get_size_other_formats_returns_none(self, temp_text_file):
        """Test that other formats return None."""
        size = get_decompressed_size(temp_text_file, CompressionFormat.ZSTD)
        assert size is None


class TestMagicBytesConstants:
    """Tests for magic bytes constants."""

    def test_all_formats_have_magic_bytes(self):
        """Test that all compressed formats have magic bytes defined."""
        formats_with_magic = set(MAGIC_BYTES.values())
        assert "gzip" in formats_with_magic
        assert "zstd" in formats_with_magic
        assert "xz" in formats_with_magic
        assert "bz2" in formats_with_magic

    def test_all_formats_have_extensions(self):
        """Test that all compressed formats have extensions defined."""
        formats_with_ext = set(EXTENSION_MAP.values())
        assert "gzip" in formats_with_ext
        assert "zstd" in formats_with_ext
        assert "xz" in formats_with_ext
        assert "bz2" in formats_with_ext

    def test_all_formats_have_decompressors(self):
        """Test that all compressed formats have decompressor commands."""
        assert "gzip" in DECOMPRESSOR_COMMANDS
        assert "zstd" in DECOMPRESSOR_COMMANDS
        assert "xz" in DECOMPRESSOR_COMMANDS
        assert "bz2" in DECOMPRESSOR_COMMANDS


class TestCompoundArchives:
    """Tests for compound archive detection and skipping."""

    def test_is_compound_archive_tar_gz(self):
        """Test that .tar.gz is detected as compound archive."""
        assert is_compound_archive("file.tar.gz") is True
        assert is_compound_archive("/path/to/archive.tar.gz") is True

    def test_is_compound_archive_tgz(self):
        """Test that .tgz is detected as compound archive."""
        assert is_compound_archive("file.tgz") is True

    def test_is_compound_archive_tar_xz(self):
        """Test that .tar.xz is detected as compound archive."""
        assert is_compound_archive("file.tar.xz") is True
        assert is_compound_archive("file.txz") is True

    def test_is_compound_archive_tar_bz2(self):
        """Test that .tar.bz2 is detected as compound archive."""
        assert is_compound_archive("file.tar.bz2") is True
        assert is_compound_archive("file.tbz2") is True
        assert is_compound_archive("file.tbz") is True

    def test_is_compound_archive_tar_zst(self):
        """Test that .tar.zst is detected as compound archive."""
        assert is_compound_archive("file.tar.zst") is True
        assert is_compound_archive("file.tzst") is True

    def test_is_not_compound_archive_simple_gz(self):
        """Test that simple .gz is not a compound archive."""
        assert is_compound_archive("file.gz") is False
        assert is_compound_archive("file.log.gz") is False

    def test_is_not_compound_archive_plain_file(self):
        """Test that plain files are not compound archives."""
        assert is_compound_archive("file.txt") is False
        assert is_compound_archive("file.log") is False

    def test_detect_compression_skips_tar_gz(self):
        """Test that .tar.gz files are not detected as compressed."""
        assert detect_compression("file.tar.gz") == CompressionFormat.NONE
        assert detect_compression("/var/log/archive.tar.gz") == CompressionFormat.NONE

    def test_detect_compression_skips_tgz(self):
        """Test that .tgz files are not detected as compressed."""
        assert detect_compression("file.tgz") == CompressionFormat.NONE

    def test_detect_compression_skips_tar_xz(self):
        """Test that .tar.xz files are not detected as compressed."""
        assert detect_compression("file.tar.xz") == CompressionFormat.NONE
        assert detect_compression("file.txz") == CompressionFormat.NONE

    def test_detect_compression_skips_tar_bz2(self):
        """Test that .tar.bz2 files are not detected as compressed."""
        assert detect_compression("file.tar.bz2") == CompressionFormat.NONE

    def test_is_compressed_false_for_tar_gz(self):
        """Test that is_compressed returns False for .tar.gz."""
        assert is_compressed("file.tar.gz") is False
        assert is_compressed("archive.tgz") is False

    def test_is_compressed_true_for_simple_gz(self):
        """Test that is_compressed still works for simple .gz files."""
        assert is_compressed("file.log.gz") is True
        assert is_compressed("syslog.1.gz") is True

    def test_compound_archive_suffixes_complete(self):
        """Test that all expected compound suffixes are defined."""
        assert ".tar.gz" in COMPOUND_ARCHIVE_SUFFIXES
        assert ".tgz" in COMPOUND_ARCHIVE_SUFFIXES
        assert ".tar.xz" in COMPOUND_ARCHIVE_SUFFIXES
        assert ".txz" in COMPOUND_ARCHIVE_SUFFIXES
        assert ".tar.bz2" in COMPOUND_ARCHIVE_SUFFIXES
        assert ".tbz2" in COMPOUND_ARCHIVE_SUFFIXES
        assert ".tar.zst" in COMPOUND_ARCHIVE_SUFFIXES
