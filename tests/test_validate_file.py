"""Tests for file validation including compressed file handling.

These tests ensure that:
1. Binary files are properly rejected
2. Text files are accepted
3. Compressed files (gzip, zstd, xz, bz2) are accepted
4. Seekable zstd files are accepted
5. Compound archives (tar.gz, etc.) are rejected
"""

import gzip
import os
import tempfile

import pytest

from rx.file_utils import is_text_file, validate_file


class TestIsTextFile:
    """Test is_text_file function."""

    def test_text_file_returns_true(self, tmp_path):
        """Test that plain text file is detected as text."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("Hello, this is plain text content.\nLine 2\n")
        assert is_text_file(str(text_file)) is True

    def test_binary_file_returns_false(self, tmp_path):
        """Test that binary file with null bytes is detected as binary."""
        binary_file = tmp_path / "test.bin"
        binary_file.write_bytes(b"Hello\x00World\x00Binary")
        assert is_text_file(str(binary_file)) is False

    def test_empty_file_returns_true(self, tmp_path):
        """Test that empty file is considered text."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_bytes(b"")
        assert is_text_file(str(empty_file)) is True

    def test_gzip_file_returns_false(self, tmp_path):
        """Test that gzip file appears as binary (has null bytes)."""
        gz_file = tmp_path / "test.gz"
        with gzip.open(gz_file, "wt") as f:
            f.write("This is compressed text\n")
        # Gzip files contain null bytes, so is_text_file returns False
        assert is_text_file(str(gz_file)) is False


class TestValidateFile:
    """Test validate_file function."""

    def test_validate_text_file_passes(self, tmp_path):
        """Test that valid text file passes validation."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("Hello, world!\n")
        # Should not raise
        validate_file(str(text_file))

    def test_validate_nonexistent_file_raises(self, tmp_path):
        """Test that nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            validate_file(str(tmp_path / "nonexistent.txt"))

    def test_validate_directory_raises(self, tmp_path):
        """Test that directory raises ValueError."""
        with pytest.raises(ValueError, match="not a file"):
            validate_file(str(tmp_path))

    def test_validate_binary_file_raises(self, tmp_path):
        """Test that binary file raises ValueError."""
        binary_file = tmp_path / "test.bin"
        binary_file.write_bytes(b"Binary\x00content\x00here")
        with pytest.raises(ValueError, match="binary"):
            validate_file(str(binary_file))


class TestValidateFileCompressedFormats:
    """Test that compressed files are accepted by validate_file."""

    def test_validate_gzip_file_passes(self, tmp_path):
        """Test that gzip compressed file passes validation."""
        gz_file = tmp_path / "test.gz"
        with gzip.open(gz_file, "wt") as f:
            f.write("This is compressed text content\n" * 100)
        # Should not raise - gzip files are processable
        validate_file(str(gz_file))

    def test_validate_gzip_file_with_log_extension_passes(self, tmp_path):
        """Test that .log.gz file passes validation."""
        gz_file = tmp_path / "app.log.gz"
        with gzip.open(gz_file, "wt") as f:
            f.write("2024-01-01 ERROR: Something went wrong\n" * 50)
        validate_file(str(gz_file))

    def test_validate_zstd_file_passes(self, tmp_path):
        """Test that zstd compressed file passes validation."""
        try:
            import zstandard as zstd
        except ImportError:
            pytest.skip("zstandard not installed")

        zst_file = tmp_path / "test.zst"
        cctx = zstd.ZstdCompressor()
        compressed = cctx.compress(b"This is zstd compressed content\n" * 100)
        zst_file.write_bytes(compressed)
        validate_file(str(zst_file))

    def test_validate_xz_file_passes(self, tmp_path):
        """Test that xz compressed file passes validation."""
        import lzma

        xz_file = tmp_path / "test.xz"
        with lzma.open(xz_file, "wt") as f:
            f.write("This is xz compressed content\n" * 100)
        validate_file(str(xz_file))

    def test_validate_bz2_file_passes(self, tmp_path):
        """Test that bz2 compressed file passes validation."""
        import bz2

        bz2_file = tmp_path / "test.bz2"
        with bz2.open(bz2_file, "wt") as f:
            f.write("This is bz2 compressed content\n" * 100)
        validate_file(str(bz2_file))


class TestValidateFileCompoundArchives:
    """Test that compound archives are rejected."""

    def test_validate_tar_gz_raises(self, tmp_path):
        """Test that .tar.gz file is rejected (compound archive)."""
        import tarfile

        # Create a tar.gz file
        tar_gz_file = tmp_path / "archive.tar.gz"
        inner_file = tmp_path / "inner.txt"
        inner_file.write_text("Content inside tar\n")

        with tarfile.open(tar_gz_file, "w:gz") as tar:
            tar.add(inner_file, arcname="inner.txt")

        # tar.gz should be rejected - it's a compound archive
        with pytest.raises(ValueError, match="binary"):
            validate_file(str(tar_gz_file))

    def test_validate_tgz_raises(self, tmp_path):
        """Test that .tgz file is rejected (compound archive)."""
        import tarfile

        tgz_file = tmp_path / "archive.tgz"
        inner_file = tmp_path / "inner.txt"
        inner_file.write_text("Content inside tar\n")

        with tarfile.open(tgz_file, "w:gz") as tar:
            tar.add(inner_file, arcname="inner.txt")

        with pytest.raises(ValueError, match="binary"):
            validate_file(str(tgz_file))


class TestValidateFileByMagicBytes:
    """Test that files are validated by magic bytes, not just extension."""

    def test_gzip_with_wrong_extension_passes(self, tmp_path):
        """Test that gzip file with .log extension passes (detected by magic)."""
        # Create a gzip file but name it .log
        gz_file = tmp_path / "compressed.log"
        with gzip.open(gz_file, "wt") as f:
            f.write("This is actually gzip compressed\n" * 100)
        # Should pass because magic bytes detect gzip
        validate_file(str(gz_file))

    def test_text_with_gz_extension_passes(self, tmp_path):
        """Test that plain text file with .gz extension passes as text."""
        # Create a plain text file named .gz (not actually compressed)
        fake_gz = tmp_path / "not_really.gz"
        fake_gz.write_text("This is plain text, not gzip\n" * 100)
        # Should pass as text file (no gzip magic bytes)
        validate_file(str(fake_gz))

    def test_binary_with_txt_extension_raises(self, tmp_path):
        """Test that binary file with .txt extension is rejected."""
        binary_txt = tmp_path / "binary.txt"
        binary_txt.write_bytes(b"Binary\x00content\x00with\x00nulls")
        with pytest.raises(ValueError, match="binary"):
            validate_file(str(binary_txt))


class TestValidateFileEdgeCases:
    """Test edge cases in file validation."""

    def test_small_gzip_file_passes(self, tmp_path):
        """Test that very small gzip file passes."""
        gz_file = tmp_path / "tiny.gz"
        with gzip.open(gz_file, "wt") as f:
            f.write("x")
        validate_file(str(gz_file))

    def test_gzip_with_empty_content_passes(self, tmp_path):
        """Test that gzip file with empty content passes."""
        gz_file = tmp_path / "empty.gz"
        with gzip.open(gz_file, "wt") as f:
            f.write("")
        validate_file(str(gz_file))

    def test_multiple_extensions_gzip(self, tmp_path):
        """Test file with multiple extensions like .log.1.gz passes."""
        gz_file = tmp_path / "app.log.1.gz"
        with gzip.open(gz_file, "wt") as f:
            f.write("Rotated log content\n" * 50)
        validate_file(str(gz_file))
