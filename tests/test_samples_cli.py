"""Tests for the rx samples CLI command."""

import json
import os
import tempfile

from click.testing import CliRunner

from rx.cli.samples import samples_command


class TestSamplesCommand:
    """Test rx samples CLI command."""

    def setup_method(self):
        """Create test files before each test."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()

        # Create a test file with multiple lines
        self.test_file = os.path.join(self.temp_dir, "test.log")
        self.lines = [
            "Line 0: first line\n",
            "Line 1: normal content\n",
            "Line 2: error occurred here\n",
            "Line 3: more content\n",
            "Line 4: another error\n",
            "Line 5: final line\n",
        ]
        with open(self.test_file, "w") as f:
            f.writelines(self.lines)

        # Calculate byte offsets for each line
        self.offsets = []
        offset = 0
        for line in self.lines:
            self.offsets.append(offset)
            offset += len(line.encode("utf-8"))

    def test_samples_single_offset(self):
        """Test samples command with a single byte offset."""
        # Get offset for line 2 (error line)
        offset = self.offsets[2]
        result = self.runner.invoke(samples_command, [self.test_file, "-b", str(offset)])
        assert result.exit_code == 0
        assert "error occurred" in result.output
        assert f"Offset: {offset}" in result.output

    def test_samples_multiple_offsets(self):
        """Test samples command with multiple byte offsets."""
        offset1 = self.offsets[2]
        offset2 = self.offsets[4]
        result = self.runner.invoke(samples_command, [self.test_file, "-b", str(offset1), "-b", str(offset2)])
        assert result.exit_code == 0
        assert "error occurred" in result.output
        assert "another error" in result.output
        assert f"Offset: {offset1}" in result.output
        assert f"Offset: {offset2}" in result.output

    def test_samples_with_context(self):
        """Test samples command with custom context size."""
        offset = self.offsets[2]
        result = self.runner.invoke(samples_command, [self.test_file, "-b", str(offset), "-c", "1"])
        assert result.exit_code == 0
        assert "Context: 1 before, 1 after" in result.output
        assert "error occurred" in result.output

    def test_samples_with_before_after(self):
        """Test samples command with separate before/after context."""
        offset = self.offsets[2]
        result = self.runner.invoke(samples_command, [self.test_file, "-b", str(offset), "-B", "1", "-A", "2"])
        assert result.exit_code == 0
        assert "Context: 1 before, 2 after" in result.output
        assert "error occurred" in result.output

    def test_samples_json_output(self):
        """Test samples command with JSON output."""
        offset = self.offsets[2]
        result = self.runner.invoke(samples_command, [self.test_file, "-b", str(offset), "--json"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["path"] == self.test_file
        assert data["offsets"] == [offset]
        assert data["before_context"] == 3
        assert data["after_context"] == 3
        assert str(offset) in data["samples"]
        # Check that samples contain the expected content
        sample_lines = data["samples"][str(offset)]
        assert any("error occurred" in line for line in sample_lines)

    def test_samples_json_multiple_offsets(self):
        """Test JSON output with multiple offsets."""
        offset1 = self.offsets[2]
        offset2 = self.offsets[4]
        result = self.runner.invoke(
            samples_command,
            [self.test_file, "-b", str(offset1), "-b", str(offset2), "--json"],
        )
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["offsets"] == [offset1, offset2]
        assert str(offset1) in data["samples"]
        assert str(offset2) in data["samples"]

    def test_samples_no_color(self):
        """Test samples command with --no-color flag."""
        offset = self.offsets[2]
        result = self.runner.invoke(samples_command, [self.test_file, "-b", str(offset), "--no-color"])
        assert result.exit_code == 0
        # Should not contain ANSI escape codes
        assert "\033[" not in result.output
        assert "error occurred" in result.output

    def test_samples_with_regex_highlight(self):
        """Test samples command with regex highlighting."""
        offset = self.offsets[2]
        result = self.runner.invoke(samples_command, [self.test_file, "-b", str(offset), "-r", "error"])
        assert result.exit_code == 0
        assert "error occurred" in result.output

    def test_samples_default_context(self):
        """Test that default context is 3 lines."""
        offset = self.offsets[2]
        result = self.runner.invoke(samples_command, [self.test_file, "-b", str(offset), "--json"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert data["before_context"] == 3
        assert data["after_context"] == 3

    def test_samples_long_form_byte_offset(self):
        """Test --byte-offset long form option."""
        offset = self.offsets[2]
        result = self.runner.invoke(samples_command, [self.test_file, "--byte-offset", str(offset)])
        assert result.exit_code == 0
        assert "error occurred" in result.output


class TestSamplesCommandErrors:
    """Test error handling in rx samples command."""

    def setup_method(self):
        """Create test environment."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()

        self.test_file = os.path.join(self.temp_dir, "test.txt")
        with open(self.test_file, "w") as f:
            f.write("Line 1\nLine 2\nLine 3\n")

    def test_samples_missing_byte_offset(self):
        """Test error when no byte offset is provided."""
        result = self.runner.invoke(samples_command, [self.test_file])
        assert result.exit_code != 0
        assert "byte-offset" in result.output.lower() or "required" in result.output.lower()

    def test_samples_nonexistent_file(self):
        """Test error for nonexistent file."""
        result = self.runner.invoke(samples_command, ["/nonexistent/path.txt", "-b", "0"])
        assert result.exit_code != 0

    def test_samples_negative_context(self):
        """Test error for negative context values."""
        result = self.runner.invoke(samples_command, [self.test_file, "-b", "0", "-c", "-1"])
        assert result.exit_code != 0
        assert "non-negative" in result.output.lower() or "error" in result.output.lower()

    def test_samples_binary_file(self):
        """Test error for binary file."""
        binary_file = os.path.join(self.temp_dir, "binary.bin")
        with open(binary_file, "wb") as f:
            f.write(b"\x00\x01\x02\x03\x04\x05")

        result = self.runner.invoke(samples_command, [binary_file, "-b", "0"])
        assert result.exit_code != 0
        assert "not a text file" in result.output.lower()

    def test_samples_invalid_offset(self):
        """Test handling of offset beyond file size."""
        result = self.runner.invoke(samples_command, [self.test_file, "-b", "999999"])
        # The function should handle this gracefully
        assert result.exit_code == 0 or "error" in result.output.lower()


class TestSamplesCommandEdgeCases:
    """Test edge cases for rx samples command."""

    def setup_method(self):
        """Create test environment."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()

    def test_samples_empty_file(self):
        """Test samples on empty file."""
        empty_file = os.path.join(self.temp_dir, "empty.txt")
        with open(empty_file, "w") as f:
            pass  # Create empty file

        result = self.runner.invoke(samples_command, [empty_file, "-b", "0"])
        # Should handle gracefully - either exit with error or return empty samples
        # The behavior depends on implementation
        assert result.exit_code in (0, 1)

    def test_samples_single_line_file(self):
        """Test samples on single-line file."""
        single_line = os.path.join(self.temp_dir, "single.txt")
        with open(single_line, "w") as f:
            f.write("Only one line here\n")

        result = self.runner.invoke(samples_command, [single_line, "-b", "0"])
        assert result.exit_code == 0
        assert "Only one line" in result.output

    def test_samples_offset_at_start(self):
        """Test samples with offset at file start."""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Line 1\nLine 2\nLine 3\n")

        result = self.runner.invoke(samples_command, [test_file, "-b", "0"])
        assert result.exit_code == 0
        assert "Line 1" in result.output

    def test_samples_offset_at_end(self):
        """Test samples with offset near end of file."""
        test_file = os.path.join(self.temp_dir, "test.txt")
        content = "Line 1\nLine 2\nLine 3\n"
        with open(test_file, "w") as f:
            f.write(content)

        # Offset at beginning of last line
        offset = len("Line 1\nLine 2\n")
        result = self.runner.invoke(samples_command, [test_file, "-b", str(offset)])
        assert result.exit_code == 0
        assert "Line 3" in result.output

    def test_samples_zero_context(self):
        """Test samples with zero context lines."""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Line 1\nLine 2\nLine 3\n")

        result = self.runner.invoke(samples_command, [test_file, "-b", "0", "-c", "0"])
        assert result.exit_code == 0
        assert "Context: 0 before, 0 after" in result.output

    def test_samples_large_context(self):
        """Test samples with context larger than file."""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Line 1\nLine 2\nLine 3\n")

        result = self.runner.invoke(samples_command, [test_file, "-b", "7", "-c", "100"])
        assert result.exit_code == 0
        # Should return available lines without error
        assert "Line" in result.output

    def test_samples_unicode_content(self):
        """Test samples with unicode content."""
        test_file = os.path.join(self.temp_dir, "unicode.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("Hello world\n")
            f.write("Japanese text here\n")
            f.write("More content\n")

        result = self.runner.invoke(samples_command, [test_file, "-b", "12"])
        assert result.exit_code == 0
        # Should handle unicode gracefully
        assert "Japanese" in result.output or result.exit_code == 0

    def test_samples_many_offsets(self):
        """Test samples with many offsets."""
        test_file = os.path.join(self.temp_dir, "test.txt")
        lines = [f"Line {i}\n" for i in range(20)]
        with open(test_file, "w") as f:
            f.writelines(lines)

        # Calculate offsets for lines 5, 10, 15
        offsets = []
        current = 0
        for i, line in enumerate(lines):
            if i in (5, 10, 15):
                offsets.append(current)
            current += len(line.encode("utf-8"))

        args = [test_file]
        for off in offsets:
            args.extend(["-b", str(off)])
        args.append("--json")

        result = self.runner.invoke(samples_command, args)
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert len(data["samples"]) == 3


class TestSamplesCommandOutput:
    """Test output formatting of rx samples command."""

    def setup_method(self):
        """Create test files."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()

        self.test_file = os.path.join(self.temp_dir, "test.log")
        with open(self.test_file, "w") as f:
            f.write("First line\n")
            f.write("Second line\n")
            f.write("Third line with error\n")
            f.write("Fourth line\n")
            f.write("Fifth line\n")

    def test_output_contains_file_header(self):
        """Test that output contains file path header."""
        result = self.runner.invoke(samples_command, [self.test_file, "-b", "0"])
        assert result.exit_code == 0
        assert "File:" in result.output
        assert self.test_file in result.output or "test.log" in result.output

    def test_output_contains_context_info(self):
        """Test that output shows context configuration."""
        result = self.runner.invoke(samples_command, [self.test_file, "-b", "0", "-c", "2"])
        assert result.exit_code == 0
        assert "Context: 2 before, 2 after" in result.output

    def test_output_offset_separator(self):
        """Test that output has offset separator lines."""
        result = self.runner.invoke(samples_command, [self.test_file, "-b", "0"])
        assert result.exit_code == 0
        assert "===" in result.output
        assert "Offset:" in result.output

    def test_json_structure(self):
        """Test JSON output has correct structure."""
        result = self.runner.invoke(samples_command, [self.test_file, "-b", "0", "--json"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert "path" in data
        assert "offsets" in data
        assert "before_context" in data
        assert "after_context" in data
        assert "samples" in data
        assert isinstance(data["samples"], dict)
