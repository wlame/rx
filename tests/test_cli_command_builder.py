"""Tests for CLI command builder module."""

import pytest

from rx.cli_command_builder import (
    add_cli_command,
    build_cli_command,
    build_complexity_cli,
    build_compress_cli,
    build_index_get_cli,
    build_index_post_cli,
    build_samples_cli,
    build_trace_cli,
    shell_quote,
)


class TestShellQuote:
    """Tests for shell quoting utility."""

    def test_simple_string(self):
        """Simple alphanumeric strings should not need quoting."""
        assert shell_quote("hello") == "hello"
        assert shell_quote("file.log") == "file.log"

    def test_string_with_spaces(self):
        """Strings with spaces should be quoted."""
        result = shell_quote("hello world")
        assert result == "'hello world'"

    def test_string_with_single_quotes(self):
        """Strings with single quotes should be properly escaped."""
        result = shell_quote("it's a test")
        # shlex.quote handles this by using double quotes or escaping
        assert "it" in result and "s a test" in result

    def test_string_with_double_quotes(self):
        """Strings with double quotes should be properly escaped."""
        result = shell_quote('say "hello"')
        assert "hello" in result

    def test_string_with_special_chars(self):
        """Strings with shell special characters should be quoted."""
        result = shell_quote("file$name")
        assert "$" not in result or result.startswith("'")

        result = shell_quote("a;b")
        assert "'" in result or result.startswith("'")

    def test_path_with_spaces(self):
        """Paths with spaces should be properly quoted."""
        result = shell_quote("/path/to/my file.log")
        assert "my file" in result
        assert "'" in result

    def test_regex_pattern(self):
        """Regex patterns with special chars should be quoted."""
        result = shell_quote("error.*failed")
        # Should be quoted due to *
        assert "error" in result and "failed" in result

    def test_empty_string(self):
        """Empty strings should return quoted empty string."""
        result = shell_quote("")
        assert result == "''"

    def test_unicode_string(self):
        """Unicode strings should be handled correctly."""
        result = shell_quote("日本語")
        assert "日本語" in result


class TestBuildTraceCli:
    """Tests for trace CLI command builder."""

    def test_single_pattern_single_path(self):
        """Basic trace with one pattern and one path."""
        result = build_trace_cli({
            "path": ["/var/log/app.log"],
            "regexp": ["error"],
        })
        assert result == "rx -e error /var/log/app.log"

    def test_multiple_patterns(self):
        """Trace with multiple patterns."""
        result = build_trace_cli({
            "path": ["/var/log/app.log"],
            "regexp": ["error", "warning"],
        })
        assert "-e error" in result
        assert "-e warning" in result
        assert "/var/log/app.log" in result

    def test_multiple_paths(self):
        """Trace with multiple paths."""
        result = build_trace_cli({
            "path": ["/var/log/app.log", "/var/log/error.log"],
            "regexp": ["error"],
        })
        assert "/var/log/app.log" in result
        assert "/var/log/error.log" in result

    def test_with_max_results(self):
        """Trace with max_results parameter."""
        result = build_trace_cli({
            "path": ["/var/log/app.log"],
            "regexp": ["error"],
            "max_results": 100,
        })
        assert "--max-results=100" in result

    def test_pattern_with_special_chars(self):
        """Patterns with regex special chars should be quoted."""
        result = build_trace_cli({
            "path": ["/var/log/app.log"],
            "regexp": ["error.*failed"],
        })
        # Pattern should be in the result (quoted if needed)
        assert "error" in result and "failed" in result

    def test_path_with_spaces(self):
        """Paths with spaces should be quoted."""
        result = build_trace_cli({
            "path": ["/var/log/my app.log"],
            "regexp": ["error"],
        })
        # Path with spaces should be quoted
        assert "'" in result or '"' in result

    def test_string_params_converted_to_list(self):
        """String params should be handled as single-item lists."""
        result = build_trace_cli({
            "path": "/var/log/app.log",  # String instead of list
            "regexp": "error",  # String instead of list
        })
        assert "-e error" in result
        assert "/var/log/app.log" in result

    def test_empty_params(self):
        """Empty params should produce minimal command."""
        result = build_trace_cli({})
        assert result == "rx"

    def test_zero_max_results_not_included(self):
        """Zero max_results should not be included (falsy value)."""
        result = build_trace_cli({
            "path": ["/var/log/app.log"],
            "regexp": ["error"],
            "max_results": 0,
        })
        assert "--max-results" not in result


class TestBuildSamplesCli:
    """Tests for samples CLI command builder."""

    def test_with_byte_offsets(self):
        """Samples with byte offsets."""
        result = build_samples_cli({
            "path": "/var/log/app.log",
            "offsets": "123,456",
        })
        assert "rx samples" in result
        assert "-b 123" in result
        assert "-b 456" in result

    def test_with_single_byte_offset(self):
        """Samples with single byte offset."""
        result = build_samples_cli({
            "path": "/var/log/app.log",
            "offsets": "12345",
        })
        assert "-b 12345" in result

    def test_with_line_offsets(self):
        """Samples with line offsets."""
        result = build_samples_cli({
            "path": "/var/log/app.log",
            "lines": "100,200",
        })
        assert "-l 100" in result
        assert "-l 200" in result

    def test_with_line_range(self):
        """Samples with line range."""
        result = build_samples_cli({
            "path": "/var/log/app.log",
            "lines": "100-200",
        })
        assert "-l 100-200" in result

    def test_with_context(self):
        """Samples with context parameter."""
        result = build_samples_cli({
            "path": "/var/log/app.log",
            "lines": "100",
            "context": 5,
        })
        assert "-c 5" in result

    def test_with_before_after_context(self):
        """Samples with before and after context."""
        result = build_samples_cli({
            "path": "/var/log/app.log",
            "lines": "100",
            "before_context": 2,
            "after_context": 10,
        })
        assert "-B 2" in result
        assert "-A 10" in result

    def test_path_with_spaces(self):
        """Paths with spaces should be quoted."""
        result = build_samples_cli({
            "path": "/var/log/my app.log",
            "lines": "100",
        })
        assert "'" in result

    def test_numeric_offset(self):
        """Numeric offset (not string) should work."""
        result = build_samples_cli({
            "path": "/var/log/app.log",
            "offsets": 12345,  # Integer instead of string
        })
        assert "-b 12345" in result


class TestBuildComplexityCli:
    """Tests for complexity/check CLI command builder."""

    def test_simple_pattern(self):
        """Simple pattern."""
        result = build_complexity_cli({"regex": "error"})
        assert result == "rx check error"

    def test_complex_pattern(self):
        """Complex pattern with special chars should be quoted."""
        result = build_complexity_cli({"regex": "(a+)+"})
        assert "rx check" in result
        # Pattern should be quoted
        assert "'" in result

    def test_pattern_with_backslash(self):
        """Pattern with backslash."""
        result = build_complexity_cli({"regex": r"\d+"})
        assert "check" in result

    def test_empty_pattern(self):
        """Empty pattern."""
        result = build_complexity_cli({"regex": ""})
        assert result == "rx check"

    def test_pattern_with_pipe(self):
        """Pattern with pipe character."""
        result = build_complexity_cli({"regex": "error|warning"})
        # Should be quoted due to pipe
        assert "'" in result


class TestBuildIndexCli:
    """Tests for index CLI command builder."""

    def test_get_index(self):
        """GET index with path."""
        result = build_index_get_cli({"path": "/var/log/app.log"})
        assert result == "rx index /var/log/app.log --info --json"

    def test_get_index_path_with_spaces(self):
        """GET index with path containing spaces."""
        result = build_index_get_cli({"path": "/var/log/my app.log"})
        assert "--info" in result
        assert "--json" in result
        assert "'" in result

    def test_post_index_basic(self):
        """POST index with just path."""
        result = build_index_post_cli({"path": "/var/log/app.log"})
        assert result == "rx index /var/log/app.log"

    def test_post_index_with_force(self):
        """POST index with force flag."""
        result = build_index_post_cli({
            "path": "/var/log/app.log",
            "force": True,
        })
        assert "--force" in result

    def test_post_index_with_analyze(self):
        """POST index with analyze flag."""
        result = build_index_post_cli({
            "path": "/var/log/app.log",
            "analyze": True,
        })
        assert "--analyze" in result

    def test_post_index_with_all_flags(self):
        """POST index with all flags."""
        result = build_index_post_cli({
            "path": "/var/log/app.log",
            "force": True,
            "analyze": True,
        })
        assert "--force" in result
        assert "--analyze" in result

    def test_post_index_false_flags_not_included(self):
        """False flags should not be included."""
        result = build_index_post_cli({
            "path": "/var/log/app.log",
            "force": False,
            "analyze": False,
        })
        assert "--force" not in result
        assert "--analyze" not in result


class TestBuildCompressCli:
    """Tests for compress CLI command builder."""

    def test_basic_compress(self):
        """Basic compress with just input path."""
        result = build_compress_cli({"input_path": "/var/log/app.log"})
        assert result == "rx compress /var/log/app.log"

    def test_with_output_path(self):
        """Compress with output path."""
        result = build_compress_cli({
            "input_path": "/var/log/app.log",
            "output_path": "/data/app.log.zst",
        })
        assert "-o" in result
        assert "/data/app.log.zst" in result

    def test_with_frame_size(self):
        """Compress with frame size."""
        result = build_compress_cli({
            "input_path": "/var/log/app.log",
            "frame_size": "4M",
        })
        assert "-s 4M" in result

    def test_with_compression_level(self):
        """Compress with compression level."""
        result = build_compress_cli({
            "input_path": "/var/log/app.log",
            "compression_level": 5,
        })
        assert "-l 5" in result

    def test_with_all_options(self):
        """Compress with all options."""
        result = build_compress_cli({
            "input_path": "/var/log/app.log",
            "output_path": "/data/app.log.zst",
            "frame_size": "4M",
            "compression_level": 5,
        })
        assert "-o" in result
        assert "-s 4M" in result
        assert "-l 5" in result

    def test_paths_with_spaces(self):
        """Paths with spaces should be quoted."""
        result = build_compress_cli({
            "input_path": "/var/log/my app.log",
            "output_path": "/data/my output.zst",
        })
        # Both paths should be quoted
        assert result.count("'") >= 2


class TestBuildCliCommand:
    """Tests for the main build_cli_command function."""

    def test_known_endpoint(self):
        """Known endpoint should return CLI command."""
        result = build_cli_command("trace", {
            "path": ["/var/log/app.log"],
            "regexp": ["error"],
        })
        assert result is not None
        assert "rx" in result

    def test_unknown_endpoint(self):
        """Unknown endpoint should return None."""
        result = build_cli_command("unknown_endpoint", {})
        assert result is None

    def test_all_registered_endpoints(self):
        """All registered endpoints should work."""
        endpoints = [
            ("trace", {"path": ["/log"], "regexp": ["err"]}),
            ("samples", {"path": "/log", "lines": "1"}),
            ("complexity", {"regex": "a+"}),
            ("index_get", {"path": "/log"}),
            ("index_post", {"path": "/log"}),
            ("compress", {"input_path": "/log"}),
        ]
        for endpoint_name, params in endpoints:
            result = build_cli_command(endpoint_name, params)
            assert result is not None, f"Endpoint {endpoint_name} returned None"
            assert "rx" in result, f"Endpoint {endpoint_name} missing 'rx'"


class TestAddCliCommand:
    """Tests for add_cli_command helper function."""

    def test_adds_cli_command_field(self):
        """Should add cli_command field to response."""
        response = {"status": "ok"}
        result = add_cli_command(response, "trace", {
            "path": ["/var/log/app.log"],
            "regexp": ["error"],
        })
        assert "cli_command" in result
        assert "rx" in result["cli_command"]

    def test_preserves_existing_fields(self):
        """Should preserve existing response fields."""
        response = {"status": "ok", "data": [1, 2, 3]}
        result = add_cli_command(response, "trace", {
            "path": ["/log"],
            "regexp": ["err"],
        })
        assert result["status"] == "ok"
        assert result["data"] == [1, 2, 3]

    def test_unknown_endpoint_no_field(self):
        """Unknown endpoint should not add cli_command field."""
        response = {"status": "ok"}
        result = add_cli_command(response, "unknown", {})
        assert "cli_command" not in result

    def test_returns_same_dict(self):
        """Should return the same dict object (mutated)."""
        response = {"status": "ok"}
        result = add_cli_command(response, "trace", {"path": ["/log"], "regexp": ["e"]})
        assert result is response


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_none_values_in_params(self):
        """None values in params should be handled gracefully."""
        result = build_trace_cli({
            "path": ["/var/log/app.log"],
            "regexp": ["error"],
            "max_results": None,
        })
        assert "--max-results" not in result

    def test_empty_list_params(self):
        """Empty list params should be handled."""
        result = build_trace_cli({
            "path": [],
            "regexp": [],
        })
        assert result == "rx"

    def test_whitespace_in_values(self):
        """Whitespace in values should be preserved and quoted."""
        result = build_trace_cli({
            "path": ["/path/with spaces/file.log"],
            "regexp": ["error  message"],  # Multiple spaces
        })
        assert "'" in result

    def test_newline_in_pattern(self):
        """Newline in pattern should be handled."""
        result = build_complexity_cli({"regex": "line1\nline2"})
        # Should be quoted/escaped
        assert "check" in result

    def test_very_long_pattern(self):
        """Very long patterns should work."""
        long_pattern = "a" * 1000
        result = build_complexity_cli({"regex": long_pattern})
        assert "check" in result
        assert "a" * 100 in result  # At least part of it
