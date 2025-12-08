"""Tests for seekable zstd compression module."""


import pytest

from rx.seekable_zstd import (
    DEFAULT_COMPRESSION_LEVEL,
    DEFAULT_FRAME_SIZE_BYTES,
    SEEK_TABLE_FOOTER_MAGIC,
    FrameInfo,
    SeekableZstdInfo,
    check_t2sz_available,
    check_zstd_available,
    create_seekable_zstd,
    decompress_frame,
    decompress_range,
    find_frame_for_offset,
    find_frames_for_range,
    get_seekable_zstd_info,
    is_seekable_zstd,
    read_seek_table,
)

# Check if zstandard module is available
try:
    import zstandard

    ZSTANDARD_AVAILABLE = True
except ImportError:
    ZSTANDARD_AVAILABLE = False

# Check if either t2sz or zstandard is available for compression
CAN_CREATE_SEEKABLE = check_t2sz_available() or ZSTANDARD_AVAILABLE


class TestSeekableZstdDetection:
    """Test detection of seekable zstd files."""

    def test_is_seekable_zstd_nonexistent_file(self, tmp_path):
        """Test detection returns False for nonexistent file."""
        assert is_seekable_zstd(tmp_path / "nonexistent.zst") is False

    def test_is_seekable_zstd_wrong_extension(self, tmp_path):
        """Test detection returns False for non-.zst file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        assert is_seekable_zstd(test_file) is False

    def test_is_seekable_zstd_regular_zstd(self, tmp_path):
        """Test detection returns False for non-seekable zstd."""
        # Create a simple zstd file without seek table
        test_file = tmp_path / "test.zst"
        try:
            import zstandard as zstd

            cctx = zstd.ZstdCompressor()
            compressed = cctx.compress(b"hello world")
            test_file.write_bytes(compressed)
            assert is_seekable_zstd(test_file) is False
        except ImportError:
            pytest.skip("zstandard not installed")

    def test_is_seekable_zstd_empty_file(self, tmp_path):
        """Test detection returns False for empty .zst file."""
        test_file = tmp_path / "empty.zst"
        test_file.write_bytes(b"")
        assert is_seekable_zstd(test_file) is False

    def test_is_seekable_zstd_too_small(self, tmp_path):
        """Test detection returns False for file too small for footer."""
        test_file = tmp_path / "small.zst"
        test_file.write_bytes(b"12345")  # Less than 9 bytes for footer
        assert is_seekable_zstd(test_file) is False


class TestFrameInfo:
    """Test FrameInfo dataclass."""

    def test_frame_info_creation(self):
        """Test creating FrameInfo object."""
        frame = FrameInfo(
            index=0,
            compressed_offset=0,
            compressed_size=1000,
            decompressed_offset=0,
            decompressed_size=5000,
        )
        assert frame.index == 0
        assert frame.compressed_offset == 0
        assert frame.compressed_size == 1000
        assert frame.decompressed_offset == 0
        assert frame.decompressed_size == 5000

    def test_frame_info_compressed_end(self):
        """Test compressed_end property."""
        frame = FrameInfo(
            index=0,
            compressed_offset=100,
            compressed_size=200,
            decompressed_offset=0,
            decompressed_size=1000,
        )
        assert frame.compressed_end == 300

    def test_frame_info_decompressed_end(self):
        """Test decompressed_end property."""
        frame = FrameInfo(
            index=0,
            compressed_offset=0,
            compressed_size=200,
            decompressed_offset=500,
            decompressed_size=1000,
        )
        assert frame.decompressed_end == 1500


class TestSeekableZstdInfo:
    """Test SeekableZstdInfo dataclass."""

    def test_seekable_zstd_info_creation(self):
        """Test creating SeekableZstdInfo object."""
        info = SeekableZstdInfo(
            path="/test/file.zst",
            compressed_size=1000,
            decompressed_size=5000,
            frame_count=3,
        )
        assert info.path == "/test/file.zst"
        assert info.compressed_size == 1000
        assert info.decompressed_size == 5000
        assert info.frame_count == 3

    def test_is_seekable_property_with_matching_frames(self):
        """Test is_seekable property when frame count matches."""
        frames = [
            FrameInfo(0, 0, 100, 0, 500),
            FrameInfo(1, 100, 100, 500, 500),
            FrameInfo(2, 200, 100, 1000, 500),
        ]
        info = SeekableZstdInfo(
            path="/test/file.zst",
            compressed_size=300,
            decompressed_size=1500,
            frame_count=3,
            frames=frames,
        )
        assert info.is_seekable is True

    def test_is_seekable_property_with_mismatched_frames(self):
        """Test is_seekable property when frame count doesn't match."""
        frames = [
            FrameInfo(0, 0, 100, 0, 500),
            FrameInfo(1, 100, 100, 500, 500),
        ]
        info = SeekableZstdInfo(
            path="/test/file.zst",
            compressed_size=300,
            decompressed_size=1500,
            frame_count=3,  # Says 3 but only 2 frames
            frames=frames,
        )
        assert info.is_seekable is False


class TestFindFrameFunctions:
    """Test frame finding utilities."""

    @pytest.fixture
    def sample_frames(self):
        """Create sample frame info list."""
        return [
            FrameInfo(0, 0, 100, 0, 1000),
            FrameInfo(1, 100, 150, 1000, 1500),
            FrameInfo(2, 250, 120, 2500, 1200),
        ]

    def test_find_frame_for_offset_first_frame(self, sample_frames):
        """Test finding frame for offset in first frame."""
        assert find_frame_for_offset(sample_frames, 0) == 0
        assert find_frame_for_offset(sample_frames, 500) == 0
        assert find_frame_for_offset(sample_frames, 999) == 0

    def test_find_frame_for_offset_middle_frame(self, sample_frames):
        """Test finding frame for offset in middle frame."""
        assert find_frame_for_offset(sample_frames, 1000) == 1
        assert find_frame_for_offset(sample_frames, 1500) == 1
        assert find_frame_for_offset(sample_frames, 2499) == 1

    def test_find_frame_for_offset_last_frame(self, sample_frames):
        """Test finding frame for offset in last frame."""
        assert find_frame_for_offset(sample_frames, 2500) == 2
        assert find_frame_for_offset(sample_frames, 3000) == 2
        assert find_frame_for_offset(sample_frames, 3699) == 2

    def test_find_frame_for_offset_out_of_range(self, sample_frames):
        """Test finding frame for offset out of range raises error."""
        with pytest.raises(ValueError):
            find_frame_for_offset(sample_frames, 4000)

    def test_find_frames_for_range_single_frame(self, sample_frames):
        """Test finding frames for range within single frame."""
        frames = find_frames_for_range(sample_frames, 100, 500)
        assert frames == [0]

    def test_find_frames_for_range_multiple_frames(self, sample_frames):
        """Test finding frames for range spanning multiple frames."""
        frames = find_frames_for_range(sample_frames, 500, 2000)
        assert frames == [0, 1]

    def test_find_frames_for_range_all_frames(self, sample_frames):
        """Test finding frames for range spanning all frames."""
        frames = find_frames_for_range(sample_frames, 0, 4000)
        assert frames == [0, 1, 2]

    def test_find_frames_for_range_empty(self, sample_frames):
        """Test finding frames for range with no overlap."""
        frames = find_frames_for_range(sample_frames, 5000, 6000)
        assert frames == []


class TestToolAvailability:
    """Test tool availability checks."""

    def test_check_zstd_available(self):
        """Test zstd availability check."""
        # This should return True on most systems with zstd installed
        result = check_zstd_available()
        assert isinstance(result, bool)

    def test_check_t2sz_available(self):
        """Test t2sz availability check."""
        # This may return False if t2sz is not installed
        result = check_t2sz_available()
        assert isinstance(result, bool)


class TestConstants:
    """Test module constants."""

    def test_default_frame_size(self):
        """Test default frame size is 4MB."""
        assert DEFAULT_FRAME_SIZE_BYTES == 4 * 1024 * 1024

    def test_default_compression_level(self):
        """Test default compression level."""
        assert DEFAULT_COMPRESSION_LEVEL == 3

    def test_seek_table_footer_magic(self):
        """Test seek table footer magic value."""
        assert SEEK_TABLE_FOOTER_MAGIC == 0x8F92EAB1


@pytest.mark.skipif(not CAN_CREATE_SEEKABLE, reason="Neither t2sz nor zstandard available")
class TestCreateSeekableZstd:
    """Test seekable zstd file creation."""

    def test_create_seekable_zstd_basic(self, tmp_path):
        """Test creating a basic seekable zstd file."""
        # Create input file with some content
        input_file = tmp_path / "input.txt"
        content = "Line {}\n".format(1) * 10000  # ~70KB of text
        input_file.write_text(content)

        output_file = tmp_path / "output.zst"

        # Create seekable zstd with small frame size for testing
        info = create_seekable_zstd(
            input_file,
            output_file,
            frame_size_bytes=10 * 1024,  # 10KB frames
            compression_level=1,
        )

        assert output_file.exists()
        assert info.frame_count > 1  # Should have multiple frames
        assert info.decompressed_size == len(content.encode())
        assert is_seekable_zstd(output_file)

    def test_create_seekable_zstd_nonexistent_input(self, tmp_path):
        """Test creating seekable zstd from nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            create_seekable_zstd(
                tmp_path / "nonexistent.txt",
                tmp_path / "output.zst",
            )

    def test_create_seekable_zstd_adds_extension(self, tmp_path):
        """Test that .zst extension is added if missing."""
        input_file = tmp_path / "input.txt"
        input_file.write_text("test content\n" * 100)

        output_base = tmp_path / "output"  # No .zst extension

        info = create_seekable_zstd(
            input_file,
            output_base,
            frame_size_bytes=1024,
        )

        # Should have created output.zst
        expected_output = tmp_path / "output.zst"
        assert expected_output.exists()
        assert info.path == str(expected_output)


@pytest.mark.skipif(not CAN_CREATE_SEEKABLE, reason="Neither t2sz nor zstandard available")
class TestDecompressFrame:
    """Test frame decompression."""

    @pytest.fixture
    def seekable_zstd_file(self, tmp_path):
        """Create a seekable zstd file for testing."""
        input_file = tmp_path / "input.txt"
        # Create content that will span multiple frames
        lines = [f"This is line number {i}\n" for i in range(1000)]
        content = "".join(lines)
        input_file.write_text(content)

        output_file = tmp_path / "output.zst"
        info = create_seekable_zstd(
            input_file,
            output_file,
            frame_size_bytes=1024,  # Small frames for testing
            compression_level=1,
        )
        return output_file, info, content

    def test_decompress_first_frame(self, seekable_zstd_file):
        """Test decompressing the first frame."""
        zst_file, info, original = seekable_zstd_file

        frame_data = decompress_frame(zst_file, 0)
        assert isinstance(frame_data, bytes)
        assert len(frame_data) > 0
        # First frame should start with beginning of original content
        assert original.encode()[:100] in frame_data[:200]

    def test_decompress_invalid_frame_index(self, seekable_zstd_file):
        """Test decompressing invalid frame index raises error."""
        zst_file, info, _ = seekable_zstd_file

        with pytest.raises(ValueError):
            decompress_frame(zst_file, info.frame_count + 10)

    def test_decompress_negative_frame_index(self, seekable_zstd_file):
        """Test decompressing negative frame index raises error."""
        zst_file, _, _ = seekable_zstd_file

        with pytest.raises(ValueError):
            decompress_frame(zst_file, -1)


@pytest.mark.skipif(not CAN_CREATE_SEEKABLE, reason="Neither t2sz nor zstandard available")
class TestReadSeekTable:
    """Test reading seek table from files."""

    @pytest.fixture
    def seekable_file_with_frames(self, tmp_path):
        """Create seekable zstd with known frame structure."""
        input_file = tmp_path / "input.txt"
        content = "x" * 50000  # 50KB of content
        input_file.write_text(content)

        output_file = tmp_path / "output.zst"
        info = create_seekable_zstd(
            input_file,
            output_file,
            frame_size_bytes=10 * 1024,  # 10KB frames
            compression_level=1,
        )
        return output_file, info

    def test_read_seek_table_returns_frames(self, seekable_file_with_frames):
        """Test reading seek table returns list of FrameInfo."""
        zst_file, expected_info = seekable_file_with_frames

        frames = read_seek_table(zst_file)
        assert isinstance(frames, list)
        assert len(frames) == expected_info.frame_count
        assert all(isinstance(f, FrameInfo) for f in frames)

    def test_read_seek_table_frame_offsets_are_sequential(self, seekable_file_with_frames):
        """Test that frame offsets are sequential and non-overlapping."""
        zst_file, _ = seekable_file_with_frames

        frames = read_seek_table(zst_file)

        # Check compressed offsets
        for i in range(1, len(frames)):
            assert frames[i].compressed_offset == frames[i - 1].compressed_end

        # Check decompressed offsets
        for i in range(1, len(frames)):
            assert frames[i].decompressed_offset == frames[i - 1].decompressed_end

    def test_read_seek_table_invalid_file(self, tmp_path):
        """Test reading seek table from non-seekable file raises error."""
        invalid_file = tmp_path / "invalid.zst"
        invalid_file.write_bytes(b"not a valid zstd file")

        with pytest.raises(ValueError):
            read_seek_table(invalid_file)


@pytest.mark.skipif(not CAN_CREATE_SEEKABLE, reason="Neither t2sz nor zstandard available")
class TestDecompressRange:
    """Test decompressing byte ranges."""

    @pytest.fixture
    def seekable_file_with_content(self, tmp_path):
        """Create seekable zstd with known content."""
        input_file = tmp_path / "input.txt"
        # Create predictable content
        content = "".join([f"LINE{i:05d}\n" for i in range(5000)])
        input_file.write_text(content)

        output_file = tmp_path / "output.zst"
        info = create_seekable_zstd(
            input_file,
            output_file,
            frame_size_bytes=5 * 1024,  # 5KB frames
            compression_level=1,
        )
        return output_file, info, content

    def test_decompress_range_from_start(self, seekable_file_with_content):
        """Test decompressing range from start of file."""
        zst_file, _, original = seekable_file_with_content

        data = decompress_range(zst_file, 0, 100)
        assert data == original.encode()[:100]

    def test_decompress_range_from_middle(self, seekable_file_with_content):
        """Test decompressing range from middle of file."""
        zst_file, _, original = seekable_file_with_content

        data = decompress_range(zst_file, 1000, 100)
        assert data == original.encode()[1000:1100]

    def test_decompress_range_spanning_frames(self, seekable_file_with_content):
        """Test decompressing range that spans multiple frames."""
        zst_file, info, original = seekable_file_with_content

        # Get a range that should span frame boundaries
        if info.frame_count > 1:
            # Find boundary between first two frames
            frames = read_seek_table(zst_file)
            boundary = frames[0].decompressed_end
            # Get range spanning the boundary
            start = boundary - 50
            length = 100
            data = decompress_range(zst_file, start, length)
            assert data == original.encode()[start : start + length]


@pytest.mark.skipif(not CAN_CREATE_SEEKABLE, reason="Neither t2sz nor zstandard available")
class TestGetSeekableZstdInfo:
    """Test getting info about seekable zstd files."""

    def test_get_info_basic(self, tmp_path):
        """Test getting basic info about seekable zstd."""
        input_file = tmp_path / "input.txt"
        content = "test\n" * 1000
        input_file.write_text(content)

        output_file = tmp_path / "output.zst"
        create_seekable_zstd(input_file, output_file, frame_size_bytes=1024)

        info = get_seekable_zstd_info(output_file)
        assert info.path == str(output_file)
        assert info.decompressed_size == len(content.encode())
        assert info.frame_count > 0
        assert len(info.frames) == info.frame_count

    def test_get_info_invalid_file(self, tmp_path):
        """Test getting info from non-seekable file raises error."""
        invalid_file = tmp_path / "invalid.zst"
        invalid_file.write_bytes(b"invalid content")

        with pytest.raises(ValueError):
            get_seekable_zstd_info(invalid_file)
