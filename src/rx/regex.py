"""Regex tools"""

import re
import math


def calculate_regex_complexity(regex: str) -> dict:
    """
    Calculate complexity score for a regex pattern to predict performance characteristics.

    This function analyzes regex patterns for structures that can lead to poor performance,
    particularly catastrophic backtracking (exponential time complexity). The scoring system
    is based on research into ReDoS (Regular Expression Denial of Service) vulnerabilities
    and regex engine behavior.

    Complexity Factors:

    CRITICAL (Catastrophic Backtracking Risk):
    - Nested Quantifiers: (a+)+, (a*)*, ((a|b)+)+
      Score: +50 each (exponential O(2^n) complexity)
    - Overlapping Quantified Groups: (a|ab)+, (a+|a)+
      Score: +30 each (ambiguous repetition)
    - Multiple Greedy Quantifiers: .*.*., .+.+, .*a.*b
      Score: +25 each (quadratic+ complexity)

    MODERATE:
    - Lookahead/Lookbehind: (?=...), (?!...), (?<=...), (?<!...)
      Score: +15 each, +30 if nested (requires re-scanning)
    - Backreferences: \\1, \\2, etc.
      Score: +20 each (NP-complete, not regular)
    - Complex Alternation: (pattern1|pattern2|...)
      Score: +5 per branch, +10 if nested

    LOW:
    - Character Classes: [a-z], \\d, \\w: +1 each
    - Simple Quantifiers: +, *, ?, {n,m}: +3 each
    - Lazy Quantifiers: +?, *?: +2 each (better performance)
    - Anchors/Boundaries: ^, $, \\b: +1 each (very efficient)
    - Literal Characters: +0.1 per char

    Multipliers:
    - Star Height (nesting depth): 1.5^depth
    - Pattern Length: log(length)/10

    Score Interpretation:
    - 0-10: Very Simple (literal/substring search)
    - 11-30: Simple (basic patterns, anchors, character classes)
    - 31-60: Moderate (some quantifiers, alternations)
    - 61-100: Complex (multiple quantifiers, lookaheads)
    - 101-200: Very Complex (nested structures, backreferences)
    - 201+: Extremely Complex/Dangerous (ReDoS risk)

    Args:
        regex: Regular expression pattern to analyze

    Returns:
        Dictionary with:
        - score: Numeric complexity score
        - level: Complexity level (very_simple, simple, moderate, complex, very_complex, dangerous)
        - warnings: List of potential performance issues found
        - details: Breakdown of scoring components
    """
    score = 0
    warnings = []
    details = {}

    # CRITICAL: Nested quantifiers (catastrophic backtracking)
    nested_quantifier_patterns = [
        r'\([^)]*[+*{][^)]*\)[+*{]',  # (a+)+, (a*){2,}, etc.
        r'\([^)]*\|[^)]*\)[+*{]',  # (a|b)+
    ]
    nested_count = 0
    for pattern in nested_quantifier_patterns:
        matches = re.findall(pattern, regex)
        nested_count += len(matches)

    if nested_count > 0:
        score += nested_count * 50
        details['nested_quantifiers'] = nested_count * 50
        warnings.append(f"Found {nested_count} nested quantifier(s) - CRITICAL ReDoS risk")

    # CRITICAL: Multiple greedy quantifiers (e.g., .*.*, .+.+)
    # First check for adjacent greedy quantifiers
    greedy_seq_pattern = r'[.+*]\s*[.+*]'
    greedy_seq = len(re.findall(greedy_seq_pattern, regex))

    # Also check for multiple .* or .+ anywhere in the pattern (catastrophic backtracking risk)
    dot_star_pattern = r'\.\*'
    dot_plus_pattern = r'\.\+'
    any_star_pattern = r'(?<!\\)\*'  # * not preceded by backslash

    dot_stars = len(re.findall(dot_star_pattern, regex))
    dot_plus = len(re.findall(dot_plus_pattern, regex))
    unanchored_stars = len(re.findall(any_star_pattern, regex))

    # Calculate score based on combinations
    greedy_score = 0
    greedy_count = 0

    # Adjacent greedy quantifiers are most dangerous
    if greedy_seq > 0:
        greedy_score += greedy_seq * 25
        greedy_count += greedy_seq

    # Multiple .* patterns (even if not adjacent) cause exponential backtracking
    if dot_stars >= 2:
        # Score increases with count: 2=30, 3=60, 4=100, etc.
        multiple_dotstar_score = (dot_stars - 1) * 30
        greedy_score += multiple_dotstar_score
        greedy_count += dot_stars

    # Multiple .+ patterns
    if dot_plus >= 2:
        multiple_dotplus_score = (dot_plus - 1) * 25
        greedy_score += multiple_dotplus_score
        greedy_count += dot_plus

    # Multiple bare * (like at start of pattern)
    if unanchored_stars >= 2:
        greedy_score += (unanchored_stars - 1) * 20
        greedy_count += unanchored_stars

    if greedy_score > 0:
        score += greedy_score
        details['greedy_sequences'] = greedy_score

        # Build detailed warning
        warning_parts = []
        if greedy_seq > 0:
            warning_parts.append(f"{greedy_seq} adjacent greedy quantifier(s)")
        if dot_stars >= 2:
            warning_parts.append(f"{dot_stars} .* pattern(s)")
        if dot_plus >= 2:
            warning_parts.append(f"{dot_plus} .+ pattern(s)")
        if unanchored_stars >= 2:
            warning_parts.append(f"{unanchored_stars} bare * quantifier(s)")

        warnings.append(f"Found {', '.join(warning_parts)} - CRITICAL backtracking risk")

    # CRITICAL: Overlapping quantified groups (e.g., (a|ab)+)
    # This is harder to detect perfectly, but we can check for common patterns
    overlap_pattern = r'\([^)]*\|[^)]*[^)]+\)[+*]'
    overlap_count = len(re.findall(overlap_pattern, regex))
    if overlap_count > 0:
        score += overlap_count * 30
        details['overlapping_groups'] = overlap_count * 30
        warnings.append(f"Found {overlap_count} potentially overlapping quantified group(s)")

    # MODERATE: Lookahead/Lookbehind assertions
    lookahead_pattern = r'\(\?[=!<]'
    lookarounds = re.findall(lookahead_pattern, regex)
    lookaround_count = len(lookarounds)

    # Check for nested lookarounds
    nested_lookaround = len(re.findall(r'\(\?[=!<][^)]*\(\?[=!<]', regex))

    if lookaround_count > 0:
        lookaround_score = lookaround_count * 15 + nested_lookaround * 15
        score += lookaround_score
        details['lookarounds'] = lookaround_score
        if nested_lookaround > 0:
            warnings.append(f"Found {nested_lookaround} nested lookaround(s) - performance impact")

    # MODERATE: Backreferences
    backref_pattern = r'\\[1-9]\d*'
    backrefs = len(re.findall(backref_pattern, regex))
    if backrefs > 0:
        score += backrefs * 20
        details['backreferences'] = backrefs * 20
        warnings.append(f"Found {backrefs} backreference(s) - NP-complete matching")

    # MODERATE: Alternation complexity
    # Count pipes, but account for groups
    pipe_count = regex.count('|')
    if pipe_count > 0:
        # Simple alternation
        alternation_score = pipe_count * 5

        # Check for nested alternation (alternation inside groups that are alternated)
        nested_alt = len(re.findall(r'\([^)]*\|[^)]*\)[^)]*\|', regex))
        alternation_score += nested_alt * 10

        score += alternation_score
        details['alternation'] = alternation_score
        if nested_alt > 0:
            warnings.append(f"Found nested alternation - increases backtracking")

    # LOW: Character classes
    char_class_pattern = r'\[[^\]]+\]'
    char_classes = len(re.findall(char_class_pattern, regex))
    negated_classes = len(re.findall(r'\[\^[^\]]+\]', regex))

    char_class_score = char_classes * 1 + negated_classes * 1  # negated already counted, so +1 more
    score += char_class_score
    details['character_classes'] = char_class_score

    # LOW: Quantifiers
    simple_quantifiers = len(re.findall(r'[^\\][+*?]|{\d+,?\d*}', regex))
    lazy_quantifiers = len(re.findall(r'[+*?]\?', regex))

    quantifier_score = simple_quantifiers * 3 + lazy_quantifiers * 2
    score += quantifier_score
    details['quantifiers'] = quantifier_score

    # LOW: Anchors and boundaries (very efficient)
    anchors = len(re.findall(r'[\^$]|\\[bBAGzZ]', regex))
    anchor_score = anchors * 1
    score += anchor_score
    details['anchors'] = anchor_score

    # LOW: Literal characters (most efficient)
    # Rough estimate: total length minus special chars
    special_chars = len(re.findall(r'[\\()\[\]{}|+*?.^$]', regex))
    literals = max(0, len(regex) - special_chars)
    literal_score = literals * 0.1
    score += literal_score
    details['literals'] = round(literal_score, 1)

    # Calculate star height (nesting depth)
    max_depth = 0
    current = 0
    for char in regex:
        if char == '(':
            current += 1
            max_depth = max(max_depth, current)
        elif char == ')':
            current -= 1

    # Apply star height multiplier
    if max_depth > 1:
        star_height_multiplier = 1.5 ** (max_depth - 1)
        score = score * star_height_multiplier
        details['star_height_multiplier'] = round(star_height_multiplier, 2)
        details['star_height_depth'] = max_depth
        if max_depth >= 3:
            warnings.append(f"Deep nesting (depth {max_depth}) - complexity multiplier applied")

    # Apply length multiplier for very long patterns
    if len(regex) > 20:
        length_multiplier = math.log(len(regex)) / 10
        score = score * length_multiplier
        details['length_multiplier'] = round(length_multiplier, 2)

    # Round final score
    score = round(score, 1)

    # Determine complexity level
    if score <= 10:
        level = "very_simple"
        risk = "Very low - essentially substring search"
    elif score <= 30:
        level = "simple"
        risk = "Low - basic pattern matching"
    elif score <= 60:
        level = "moderate"
        risk = "Medium - reasonable performance expected"
    elif score <= 100:
        level = "complex"
        risk = "High - monitor performance on large files"
    elif score <= 200:
        level = "very_complex"
        risk = "Very high - significant performance impact likely"
    else:
        level = "dangerous"
        risk = "CRITICAL - ReDoS risk, catastrophic backtracking likely"
        warnings.append("DANGER: This pattern may cause catastrophic backtracking!")

    return {
        'score': score,
        'level': level,
        'risk': risk,
        'warnings': warnings,
        'details': details,
        'pattern_length': len(regex),
    }
