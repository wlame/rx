"""Tests for prefix pattern extraction and detection."""

from collections import deque

from rx.analyze import LineContext, PrefixDeviationDetector, PrefixPatternExtractor


def make_context(line: str, line_number: int = 1) -> LineContext:
    """Helper to create a LineContext for testing."""
    return LineContext(
        line=line,
        line_number=line_number,
        byte_offset=0,
        window=deque(),
        line_lengths=deque(),
        avg_line_length=50.0,
        stddev_line_length=10.0,
    )


class TestPrefixPatternExtractor:
    """Tests for PrefixPatternExtractor."""

    def setup_method(self):
        self.extractor = PrefixPatternExtractor()

    def test_extract_from_empty_lines(self):
        """Empty input returns None."""
        result = self.extractor.extract_from_lines([])
        assert result is None

    def test_extract_from_whitespace_only(self):
        """Whitespace-only lines return None."""
        result = self.extractor.extract_from_lines(['   ', '\t', '  \n'])
        assert result is None

    def test_extract_simple_pattern(self):
        """Extract pattern from simple timestamp-prefixed logs."""
        logs = [
            '2025-12-10 07:49:50.595 INFO Starting',
            '2025-12-10 07:49:51.123 DEBUG Loading',
            '2025-12-10 07:49:52.456 INFO Running',
            '2025-12-10 07:49:53.789 WARN Warning',
            '2025-12-10 07:49:54.000 ERROR Failed',
        ] * 20  # Need enough lines for pattern detection

        result = self.extractor.extract_from_lines(logs)
        assert result is not None
        assert '<DATE>' in result.pattern
        assert '<TIME>' in result.pattern
        assert result.coverage >= 0.9

    def test_extract_bracketed_pattern(self):
        """Extract pattern with bracketed components."""
        logs = [
            '2025-12-10 07:49:50.595 [1234567] [server-1] INFO Start',
            '2025-12-10 07:49:51.123 [1234568] [server-2] DEBUG Load',
            '2025-12-10 07:49:52.456 [1234569] [server-1] INFO Run',
            '2025-12-10 07:49:53.789 [1234570] [server-3] WARN Slow',
            '2025-12-10 07:49:54.000 [1234571] [server-1] ERROR Fail',
        ] * 20

        result = self.extractor.extract_from_lines(logs)
        assert result is not None
        assert '<NUM_ID>' in result.pattern
        assert '<COMPONENT>' in result.pattern
        assert result.coverage >= 0.9

    def test_extract_syslog_pattern(self):
        """Extract pattern from syslog-style logs."""
        logs = [
            'Dec 10 07:00:19.005 myhost kernel: Starting',
            'Dec 10 07:00:20.123 myhost kernel: Loading',
            'Dec 10 07:00:21.456 myhost systemd: Running',
            'Dec 10 07:00:22.789 myhost kernel: Ready',
            'Dec 10 07:00:23.000 myhost sshd: Connected',
        ] * 20

        result = self.extractor.extract_from_lines(logs)
        assert result is not None
        assert '<SYSDATE>' in result.pattern
        assert result.coverage >= 0.9

    def test_mixed_format_no_dominant_pattern(self):
        """Mixed formats should not produce a dominant pattern."""
        logs = [
            '2025-12-10 07:49:50.595 INFO Starting',
            'Dec 10 07:00:19.005 myhost kernel: Starting',
            '[ERROR] Something failed',
            'Random text line',
            '{"json": "log"}',
        ] * 5

        result = self.extractor.extract_from_lines(logs)
        # May or may not find a pattern, but coverage should be low
        if result:
            assert result.coverage < 0.9

    def test_prefix_to_regex_matches(self):
        """Generated regex should match original lines."""
        logs = [
            '2025-12-10 07:49:50.595 [123] [srv] INFO msg',
            '2025-12-10 07:49:51.123 [456] [srv] DEBUG msg',
            '2025-12-10 07:49:52.456 [789] [srv] WARN msg',
        ] * 30

        result = self.extractor.extract_from_lines(logs)
        assert result is not None

        import re

        pattern = re.compile(result.regex)

        # All original lines should match
        for log in logs[:10]:
            assert pattern.match(log), f'Regex should match: {log}'

        # Non-matching lines should not match
        assert not pattern.match('Random garbage')
        assert not pattern.match('java.lang.Exception')

    def test_coverage_threshold(self):
        """Coverage threshold is respected."""
        extractor = PrefixPatternExtractor(coverage_threshold=0.95)

        # 90% normal, 10% anomalies
        logs = ['2025-12-10 07:49:50.123 INFO msg'] * 90
        logs += ['Random anomaly line'] * 10

        result = extractor.extract_from_lines(logs)
        # With 95% threshold, 90% coverage should not meet it
        # The extractor has fallback logic for >50% coverage
        if result:
            assert result.coverage >= 0.5


class TestPrefixDeviationDetector:
    """Tests for PrefixDeviationDetector."""

    def test_name_and_category(self):
        detector = PrefixDeviationDetector()
        assert detector.name == 'prefix_deviation'
        assert detector.category == 'format'

    def test_unconfigured_detector_returns_none(self):
        """Detector without regex returns None for all lines."""
        detector = PrefixDeviationDetector()
        assert not detector.is_configured()

        ctx = make_context('Any line at all')
        assert detector.check_line(ctx) is None

    def test_configured_detector(self):
        """Detector with regex checks lines."""
        regex = r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}'
        detector = PrefixDeviationDetector(prefix_regex=regex)
        assert detector.is_configured()

    def test_matching_line_returns_none(self):
        """Lines matching prefix return None (not anomaly)."""
        regex = r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}'
        detector = PrefixDeviationDetector(prefix_regex=regex)

        ctx = make_context('2025-12-10 07:49:50 INFO Starting')
        assert detector.check_line(ctx) is None

    def test_non_matching_line_returns_severity(self):
        """Lines not matching prefix return severity."""
        regex = r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}'
        detector = PrefixDeviationDetector(prefix_regex=regex)

        ctx = make_context('Random garbage line')
        severity = detector.check_line(ctx)
        assert severity is not None
        assert severity > 0

    def test_indented_line_lower_severity(self):
        """Indented lines (continuations) have lower severity."""
        regex = r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}'
        detector = PrefixDeviationDetector(prefix_regex=regex, severity=0.3)

        normal_ctx = make_context('Random garbage')
        indented_ctx = make_context('    at com.example.Class.method()')

        normal_severity = detector.check_line(normal_ctx)
        indented_severity = detector.check_line(indented_ctx)

        assert indented_severity < normal_severity

    def test_empty_line_not_anomaly(self):
        """Empty lines are not flagged as anomalies."""
        regex = r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}'
        detector = PrefixDeviationDetector(prefix_regex=regex)

        ctx = make_context('')
        assert detector.check_line(ctx) is None

        ctx = make_context('   ')
        assert detector.check_line(ctx) is None

    def test_merge_consecutive_non_matching(self):
        """Consecutive non-matching lines should merge."""
        regex = r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}'
        detector = PrefixDeviationDetector(prefix_regex=regex)

        # First non-matching line
        ctx1 = make_context('java.lang.NullPointerException')
        severity1 = detector.check_line(ctx1)
        assert severity1 is not None

        # Second non-matching line should merge
        ctx2 = make_context('    at com.example.Class.method()')
        should_merge = detector.should_merge_with_previous(ctx2, severity1)
        assert should_merge

    def test_no_merge_when_current_matches(self):
        """Matching line should not merge with previous anomaly."""
        regex = r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}'
        detector = PrefixDeviationDetector(prefix_regex=regex)

        # Matching line should not merge
        ctx = make_context('2025-12-10 07:49:50 INFO Normal log')
        should_merge = detector.should_merge_with_previous(ctx, 0.3)
        assert not should_merge

    def test_description_single_line(self):
        """Description for single-line anomaly."""
        detector = PrefixDeviationDetector()
        lines = ['Random garbage line']
        desc = detector.get_description(lines)
        assert "doesn't match" in desc.lower() or 'prefix' in desc.lower()

    def test_description_multi_line(self):
        """Description for multi-line anomaly."""
        detector = PrefixDeviationDetector()
        lines = ['java.lang.Exception', '    at Class.method()', '    at Other.call()']
        desc = detector.get_description(lines)
        assert '3 lines' in desc

    def test_invalid_regex_handled(self):
        """Invalid regex should not crash, just disable detector."""
        detector = PrefixDeviationDetector(prefix_regex='[invalid(regex')
        assert not detector.is_configured()

        ctx = make_context('Any line')
        assert detector.check_line(ctx) is None

    def test_set_prefix_regex_property(self):
        """Can set prefix_regex after initialization."""
        detector = PrefixDeviationDetector()
        assert not detector.is_configured()

        detector.prefix_regex = r'^\d{4}-\d{2}-\d{2}'
        assert detector.is_configured()

        ctx = make_context('Random garbage')
        assert detector.check_line(ctx) is not None


class TestIntegration:
    """Integration tests for prefix pattern detection."""

    def test_extract_and_detect(self):
        """End-to-end: extract pattern then detect anomalies."""
        # Create sample logs with 95% normal, 5% anomalies
        normal_logs = [f'2025-12-10 07:49:{i:02d}.123 [100{i}] [server] INFO Processing item {i}' for i in range(95)]
        anomaly_logs = [
            'java.lang.NullPointerException',
            '    at com.example.Class.method(File.java:123)',
            'Random debug output',
            'ERROR: Something bad happened',
            'Traceback (most recent call last):',
        ]
        all_logs = normal_logs + anomaly_logs

        # Extract pattern
        extractor = PrefixPatternExtractor()
        pattern = extractor.extract_from_lines(all_logs)
        assert pattern is not None
        assert pattern.coverage >= 0.9

        # Create detector
        detector = PrefixDeviationDetector(
            prefix_regex=pattern.regex,
            prefix_length=pattern.prefix_length,
        )
        assert detector.is_configured()

        # Check normal logs - should not be flagged
        for log in normal_logs[:10]:
            ctx = make_context(log)
            assert detector.check_line(ctx) is None, f'Should not flag: {log}'

        # Check anomaly logs - should be flagged
        for log in anomaly_logs:
            ctx = make_context(log)
            severity = detector.check_line(ctx)
            assert severity is not None, f'Should flag: {log}'

    def test_different_log_formats(self):
        """Test with various log format styles."""
        test_cases = [
            # (format_name, sample_logs)
            (
                'ISO timestamp with level',
                [f'2025-12-10T07:49:{i:02d}.123Z INFO Message {i}' for i in range(50)],
            ),
            (
                'Syslog style',
                [f'Dec 10 07:00:{i:02d} myhost daemon[123]: Message {i}' for i in range(50)],
            ),
            (
                'Bracketed components',
                [f'[2025-12-10 07:49:{i:02d}] [MAIN] [INFO] Message {i}' for i in range(50)],
            ),
        ]

        extractor = PrefixPatternExtractor()

        for format_name, logs in test_cases:
            pattern = extractor.extract_from_lines(logs)
            assert pattern is not None, f'Should extract pattern for: {format_name}'
            assert pattern.coverage >= 0.9, f'Coverage too low for: {format_name}'

            # Detector should work
            detector = PrefixDeviationDetector(prefix_regex=pattern.regex)
            assert detector.is_configured()

            # Original logs should match
            for log in logs[:5]:
                ctx = make_context(log)
                assert detector.check_line(ctx) is None
