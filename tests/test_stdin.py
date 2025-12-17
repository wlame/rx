"""Tests for stdin input functionality."""

import json

from click.testing import CliRunner

from rx.cli.trace import trace_command


class TestStdinBasic:
    """Test basic stdin functionality."""

    def setup_method(self):
        """Create test runner before each test."""
        self.runner = CliRunner()

    def test_stdin_pipe_basic(self):
        """Test basic piped stdin input."""
        input_text = 'line 1: hello\nline 2: world\nline 3: hello world\n'
        result = self.runner.invoke(trace_command, ['hello'], input=input_text)

        assert result.exit_code == 0
        assert 'Matches: 2' in result.output
        assert 'hello' in result.output

    def test_stdin_explicit_dash(self):
        """Test explicit '-' argument for stdin."""
        input_text = 'line 1: error occurred\nline 2: success\nline 3: another error\n'
        result = self.runner.invoke(trace_command, ['error', '-'], input=input_text)

        assert result.exit_code == 0
        assert 'Matches: 2' in result.output
        assert 'error' in result.output

    def test_stdin_json_output(self):
        """Test stdin with JSON output."""
        input_text = 'line 1: test\nline 2: test again\n'
        result = self.runner.invoke(trace_command, ['test', '--json'], input=input_text)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data['matches']) == 2
        assert 'p1' in data['patterns']
        assert data['patterns']['p1'] == 'test'

    def test_stdin_no_matches(self):
        """Test stdin with no matches."""
        input_text = 'line 1: hello\nline 2: world\n'
        result = self.runner.invoke(trace_command, ['nomatch'], input=input_text)

        assert result.exit_code == 0
        assert 'Matches: 0' in result.output

    def test_stdin_empty_input(self):
        """Test with empty stdin."""
        result = self.runner.invoke(trace_command, ['pattern'], input='')

        # Should default to current directory when stdin is empty
        assert result.exit_code == 0


class TestStdinWithOptions:
    """Test stdin with various options."""

    def setup_method(self):
        """Create test runner before each test."""
        self.runner = CliRunner()

    def test_stdin_with_max_results(self):
        """Test stdin with max_results limit."""
        input_text = 'match\nmatch\nmatch\nmatch\nmatch\n'
        result = self.runner.invoke(trace_command, ['match', '--max-results=2'], input=input_text)

        assert result.exit_code == 0
        # Check the "Matches: N" summary line
        assert 'Matches: 2' in result.output

    def test_stdin_with_samples(self):
        """Test stdin with --samples flag."""
        input_text = 'line 1\nline 2: match\nline 3\n'
        result = self.runner.invoke(trace_command, ['match', '--samples', '--context=1'], input=input_text)

        assert result.exit_code == 0
        assert 'Samples (context: 1 before, 1 after)' in result.output
        assert 'match' in result.output

    def test_stdin_case_insensitive(self):
        """Test stdin with case-insensitive search."""
        input_text = 'line 1: HELLO\nline 2: hello\nline 3: HeLLo\n'
        result = self.runner.invoke(trace_command, ['hello', '-i'], input=input_text)

        assert result.exit_code == 0
        # Should match all three variations
        assert 'Matches: 3' in result.output

    def test_stdin_multiple_patterns(self):
        """Test stdin with multiple patterns using -e."""
        input_text = 'line 1: error\nline 2: warning\nline 3: info\n'
        result = self.runner.invoke(trace_command, ['-e', 'error', '-e', 'warning'], input=input_text)

        assert result.exit_code == 0
        assert 'Matches: 2' in result.output
        assert 'error' in result.output
        assert 'warning' in result.output


class TestStdinEdgeCases:
    """Test edge cases for stdin functionality."""

    def setup_method(self):
        """Create test runner before each test."""
        self.runner = CliRunner()

    def test_stdin_multiline_match(self):
        """Test matching patterns across multiple lines."""
        input_text = 'error: connection failed\nwarning: timeout\nerror: retry\n'
        result = self.runner.invoke(trace_command, ['error'], input=input_text)

        assert result.exit_code == 0
        assert 'Matches: 2' in result.output

    def test_stdin_special_characters(self):
        """Test stdin with special characters."""
        input_text = 'line 1: test@example.com\nline 2: user@test.com\n'
        result = self.runner.invoke(trace_command, [r'\S+@\S+\.com'], input=input_text)

        assert result.exit_code == 0
        assert 'Matches: 2' in result.output

    def test_stdin_unicode(self):
        """Test stdin with unicode characters."""
        input_text = 'line 1: hello 世界\nline 2: test 测试\nline 3: hello test\n'
        result = self.runner.invoke(trace_command, ['hello'], input=input_text)

        assert result.exit_code == 0
        assert 'Matches: 2' in result.output

    def test_stdin_large_input(self):
        """Test stdin with large input."""
        # Generate 1000 lines
        input_text = '\n'.join([f'line {i}: test data' for i in range(1000)])
        result = self.runner.invoke(trace_command, ['test'], input=input_text)

        assert result.exit_code == 0
        assert 'Matches: 1000' in result.output

    def test_stdin_no_trailing_newline(self):
        """Test stdin input without trailing newline."""
        input_text = 'line 1: hello'  # No trailing newline
        result = self.runner.invoke(trace_command, ['hello'], input=input_text)

        assert result.exit_code == 0
        assert 'Matches: 1' in result.output


class TestStdinCombinations:
    """Test stdin combined with other features."""

    def setup_method(self):
        """Create test runner before each test."""
        self.runner = CliRunner()

    def test_stdin_with_context_json(self):
        """Test stdin with context and JSON output."""
        input_text = 'line 1\nline 2: match\nline 3\n'
        result = self.runner.invoke(trace_command, ['match', '--samples', '--context=1', '--json'], input=input_text)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data['matches']) == 1
        assert data['before_context'] == 1
        assert data['after_context'] == 1
        assert data['context_lines'] is not None

    def test_stdin_word_boundary(self):
        """Test stdin with word boundary matching."""
        input_text = 'testing test tested\n'
        result = self.runner.invoke(trace_command, ['test', '-w'], input=input_text)

        assert result.exit_code == 0
        # Only 'test' should match, not 'testing' or 'tested'
        assert 'Matches: 1' in result.output
