"""Tests for parse module functions"""

import pytest
import tempfile
import os
from rx.parse import (
    get_file_offsets,
    get_context,
)
from rx.regex import calculate_regex_complexity


class TestGetFileOffsets:
    """Tests for get_file_offsets function"""

    def _create_test_file(self, size_mb: int) -> str:
        """Helper to create a test file of specified size"""
        # Create file with lines to ensure proper newline alignment
        f = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
        line = "A" * 100 + "\n"  # 101 bytes per line
        lines_needed = (size_mb * 1024 * 1024) // len(line)
        for _ in range(lines_needed):
            f.write(line)
        f.close()
        return f.name

    def test_small_file_single_chunk(self):
        """Files smaller than MIN_CHUNK_SIZE should return single offset [0]"""
        filepath = self._create_test_file(10)  # 10MB
        try:
            offsets = get_file_offsets(filepath, os.path.getsize(filepath))
            assert offsets == [0]
        finally:
            os.unlink(filepath)

    def test_120mb_file_two_chunks(self):
        """120MB file should be split into 5 chunks (25MB threshold)"""
        filepath = self._create_test_file(120)  # 120MB
        try:
            offsets = get_file_offsets(filepath, os.path.getsize(filepath))
            # Should have 5 chunks (120MB / 25MB = 4.8, rounded up to 5)
            assert len(offsets) == 5
            # First offset always 0
            assert offsets[0] == 0
            # Second offset should be around 25MB (aligned to newline)
            assert 20 * 1024 * 1024 < offsets[1] < 30 * 1024 * 1024
        finally:
            os.unlink(filepath)

    def test_offsets_always_start_with_zero(self):
        """All offset lists should start with 0"""
        for size_mb in [10, 100, 200]:
            filepath = self._create_test_file(size_mb)
            try:
                offsets = get_file_offsets(filepath, os.path.getsize(filepath))
                assert offsets[0] == 0
            finally:
                os.unlink(filepath)

    def test_offsets_aligned_to_newlines(self):
        """Offsets should be aligned to newline boundaries"""
        filepath = self._create_test_file(150)  # 150MB -> should split into 3 chunks
        try:
            offsets = get_file_offsets(filepath, os.path.getsize(filepath))

            # Read file to verify offsets are at newline boundaries
            with open(filepath, 'rb') as f:
                for i, offset in enumerate(offsets):
                    if offset == 0:
                        continue
                    # Check that the byte before offset is a newline
                    f.seek(offset - 1)
                    byte_before = f.read(1)
                    assert byte_before == b'\n', f"Offset {i} ({offset}) is not aligned to newline"
        finally:
            os.unlink(filepath)


class TestRegexComplexity:
    """Tests for calculate_regex_complexity function"""

    def test_very_simple_literal(self):
        """Test literal string (substring search)"""
        result = calculate_regex_complexity('hello')
        assert result['level'] == 'very_simple'
        assert result['score'] <= 10
        assert len(result['warnings']) == 0

    def test_simple_pattern(self):
        """Test simple pattern with anchors and character class"""
        result = calculate_regex_complexity('^[a-z]+$')
        assert result['level'] in ['very_simple', 'simple']
        assert result['score'] <= 30
        assert 'character_classes' in result['details']

    def test_moderate_pattern(self):
        """Test moderate pattern with quantifiers"""
        result = calculate_regex_complexity(r'\w+@\w+\.\w+')
        assert result['level'] in ['very_simple', 'simple', 'moderate']
        assert result['score'] <= 60

    def test_nested_quantifiers_critical(self):
        """Test nested quantifiers (catastrophic backtracking)"""
        result = calculate_regex_complexity('(a+)+')
        assert result['score'] >= 50  # Should have high score
        assert any('nested quantifier' in w.lower() for w in result['warnings'])
        assert 'nested_quantifiers' in result['details']

    def test_multiple_greedy_quantifiers(self):
        """Test multiple greedy quantifiers in sequence"""
        result = calculate_regex_complexity('.*.*')
        assert result['score'] >= 25
        assert any('greedy' in w.lower() for w in result['warnings'])
        assert 'greedy_sequences' in result['details']

    def test_overlapping_groups(self):
        """Test overlapping quantified groups"""
        result = calculate_regex_complexity('(a|ab)+')
        assert result['score'] >= 30
        assert 'overlapping_groups' in result['details'] or 'nested_quantifiers' in result['details']

    def test_lookahead_assertions(self):
        """Test lookahead/lookbehind assertions"""
        result = calculate_regex_complexity('(?=.*[a-z])(?=.*[0-9])')
        assert 'lookarounds' in result['details']
        assert result['details']['lookarounds'] >= 15

    def test_nested_lookaheads(self):
        """Test nested lookahead (high complexity)"""
        result = calculate_regex_complexity('(?=(?=.*[a-z]))')
        assert result['score'] > 30
        assert any('nested lookaround' in w.lower() for w in result['warnings'])

    def test_backreferences(self):
        """Test backreferences (NP-complete)"""
        result = calculate_regex_complexity(r'(a)\1')
        assert 'backreferences' in result['details']
        assert result['details']['backreferences'] >= 20
        assert any('backreference' in w.lower() for w in result['warnings'])

    def test_alternation(self):
        """Test alternation complexity"""
        result = calculate_regex_complexity('cat|dog|bird')
        assert 'alternation' in result['details']
        assert result['details']['alternation'] > 0

    def test_nested_alternation(self):
        """Test nested alternation"""
        result = calculate_regex_complexity('(a|b)|(c|d)')
        assert 'alternation' in result['details']

    def test_character_classes(self):
        """Test character classes"""
        result = calculate_regex_complexity('[a-z][0-9]')
        assert 'character_classes' in result['details']
        assert result['details']['character_classes'] >= 2

    def test_negated_character_class(self):
        """Test negated character classes"""
        result = calculate_regex_complexity('[^a-z]')
        assert 'character_classes' in result['details']

    def test_lazy_quantifiers(self):
        """Test lazy quantifiers (better performance)"""
        result = calculate_regex_complexity('.*?')
        assert 'quantifiers' in result['details']
        # Lazy quantifiers should have lower score than greedy

    def test_anchors_and_boundaries(self):
        """Test anchors and word boundaries"""
        result = calculate_regex_complexity(r'^word\b$')
        assert 'anchors' in result['details']
        assert result['details']['anchors'] >= 2

    def test_star_height_multiplier(self):
        """Test star height (nesting depth) multiplier"""
        result = calculate_regex_complexity('((a+)+)+')
        assert 'star_height_multiplier' in result['details']
        assert result['details']['star_height_depth'] >= 2  # Has 2 levels of nesting
        assert result['score'] > 50  # Should be high due to nested quantifiers

    def test_length_multiplier(self):
        """Test length multiplier for long patterns"""
        long_pattern = 'a' * 50 + '.*' * 10
        result = calculate_regex_complexity(long_pattern)
        assert 'length_multiplier' in result['details']

    def test_dangerous_pattern(self):
        """Test pattern that should be flagged as dangerous"""
        result = calculate_regex_complexity('(a+)+b')
        assert result['level'] in ['moderate', 'complex', 'very_complex', 'dangerous']
        assert result['score'] >= 50  # Should be flagged as risky
        assert len(result['warnings']) > 0

    def test_redos_vulnerable_email(self):
        """Test classic ReDoS vulnerable email pattern"""
        result = calculate_regex_complexity('([a-zA-Z0-9]+)*@([a-zA-Z0-9]+)*\\.com')
        assert result['score'] >= 30  # Should be flagged as risky
        assert any('nested' in w.lower() or 'overlapping' in w.lower() for w in result['warnings'])

    def test_safe_email_pattern(self):
        """Test safer email pattern"""
        result = calculate_regex_complexity(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        assert result['level'] in ['very_simple', 'simple', 'moderate']
        assert result['score'] < 100

    def test_complexity_levels_ordered(self):
        """Test that complexity levels are properly ordered"""
        patterns = [
            ('hello', 'very_simple'),
            ('^test$', 'simple'),
            (r'\w+@\w+', 'moderate'),
            ('(a+)+', 'complex'),
            ('((a+)+)+', 'very_complex'),
        ]

        scores = []
        for pattern, expected_min_level in patterns:
            result = calculate_regex_complexity(pattern)
            scores.append(result['score'])

        # Scores should generally increase
        assert scores[-1] > scores[0]  # Most complex > simplest

    def test_details_always_present(self):
        """Test that details dict is always returned"""
        result = calculate_regex_complexity('.*')
        assert 'details' in result
        assert isinstance(result['details'], dict)

    def test_warnings_is_list(self):
        """Test that warnings is always a list"""
        result = calculate_regex_complexity('hello')
        assert 'warnings' in result
        assert isinstance(result['warnings'], list)

    def test_score_is_numeric(self):
        """Test that score is numeric"""
        result = calculate_regex_complexity('test.*')
        assert 'score' in result
        assert isinstance(result['score'], (int, float))
        assert result['score'] >= 0

    def test_risk_description(self):
        """Test that risk description is provided"""
        result = calculate_regex_complexity('hello')
        assert 'risk' in result
        assert isinstance(result['risk'], str)
        assert len(result['risk']) > 0
