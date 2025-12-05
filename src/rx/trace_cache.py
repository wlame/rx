"""Trace cache module for caching pattern match results on large files.

This module provides functionality to cache and retrieve trace results for
large files, enabling fast lookups without re-running the dd|rg pipeline.

Cache files are stored in ~/.cache/rx/trace_cache/ and contain:
- Source file metadata (path, size, modification time)
- Patterns and flags used for the search
- Match results (pattern index, byte offset, line number)

Cache is only written for complete scans (no max_results truncation) on
files >= get_large_file_threshold_bytes().
"""

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rx.cli import prometheus as prom
from rx.file_utils import get_context_by_lines
from rx.index import get_large_file_threshold_bytes
from rx.models import ContextLine, Submatch
from rx.utils import get_int_env

logger = logging.getLogger(__name__)

# Constants
TRACE_CACHE_VERSION = 1
TRACE_CACHE_DIR_NAME = "rx/trace_cache"

# Flags that affect matching and must be part of cache key
MATCHING_FLAGS = {"-i", "-w", "-x", "-F", "-P", "--case-sensitive", "--ignore-case"}


def get_trace_cache_dir() -> Path:
    """Get the trace cache directory path, creating it if necessary."""
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        base = Path(xdg_cache)
    else:
        base = Path.home() / ".cache"

    cache_dir = base / TRACE_CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def compute_patterns_hash(patterns: list[str], rg_flags: list[str]) -> str:
    """Compute a hash of patterns and relevant matching flags.

    Args:
        patterns: List of regex patterns
        rg_flags: List of ripgrep flags

    Returns:
        First 16 chars of SHA256 hash
    """
    # Sort patterns for consistent hashing
    sorted_patterns = sorted(patterns)

    # Extract only flags that affect matching
    relevant_flags = sorted([f for f in rg_flags if f in MATCHING_FLAGS])

    # Combine patterns and flags into hash input
    hash_input = json.dumps({"patterns": sorted_patterns, "flags": relevant_flags}, sort_keys=True)

    return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


def get_trace_cache_path(source_path: str, patterns: list[str], rg_flags: list[str]) -> Path:
    """Generate the cache file path for a source file and patterns.

    Uses SHA256 hash of absolute path plus patterns hash to create a unique
    but identifiable cache filename. Structure is:
    <cache_dir>/<patterns_hash>/<path_hash>_<filename>.json

    Args:
        source_path: Path to the source file
        patterns: List of regex patterns
        rg_flags: List of ripgrep flags

    Returns:
        Path to the cache file in cache directory
    """
    abs_path = os.path.abspath(source_path)
    path_hash = hashlib.sha256(abs_path.encode()).hexdigest()[:16]
    patterns_hash = compute_patterns_hash(patterns, rg_flags)
    filename = os.path.basename(source_path)
    cache_filename = f"{path_hash}_{filename}.json"
    return get_trace_cache_dir() / patterns_hash / cache_filename


def is_trace_cache_valid(source_path: str, patterns: list[str], rg_flags: list[str]) -> bool:
    """Check if a valid trace cache exists for the source file and patterns.

    A cache is valid if:
    - Cache file exists
    - Source file modification time matches
    - Source file size matches
    - Patterns hash matches

    Args:
        source_path: Path to the source file
        patterns: List of regex patterns
        rg_flags: List of ripgrep flags

    Returns:
        True if valid cache exists, False otherwise
    """
    cache_path = get_trace_cache_path(source_path, patterns, rg_flags)
    if not cache_path.exists():
        return False

    try:
        cache_data = load_trace_cache(cache_path)
        if cache_data is None:
            return False

        source_stat = os.stat(source_path)
        source_mtime = datetime.fromtimestamp(source_stat.st_mtime).isoformat()

        # Validate file metadata
        if cache_data.get("source_modified_at") != source_mtime:
            logger.debug(f"Cache invalid: mtime mismatch for {source_path}")
            return False
        if cache_data.get("source_size_bytes") != source_stat.st_size:
            logger.debug(f"Cache invalid: size mismatch for {source_path}")
            return False

        # Validate patterns hash
        expected_hash = compute_patterns_hash(patterns, rg_flags)
        if cache_data.get("patterns_hash") != expected_hash:
            logger.debug(f"Cache invalid: patterns hash mismatch for {source_path}")
            return False

        return True
    except (OSError, json.JSONDecodeError, KeyError) as e:
        logger.debug(f"Cache validation failed for {source_path}: {e}")
        return False


def load_trace_cache(cache_path: Path | str) -> dict | None:
    """Load a trace cache file from disk.

    Args:
        cache_path: Path to the cache file

    Returns:
        Cache data dictionary, or None if loading fails
    """
    start_time = time.time()
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate version
        if data.get("version") != TRACE_CACHE_VERSION:
            logger.warning(f"Cache version mismatch: {data.get('version')} != {TRACE_CACHE_VERSION}")
            prom.trace_cache_load_duration_seconds.observe(time.time() - start_time)
            return None

        prom.trace_cache_load_duration_seconds.observe(time.time() - start_time)
        return data
    except (OSError, json.JSONDecodeError) as e:
        logger.debug(f"Failed to load trace cache {cache_path}: {e}")
        prom.trace_cache_load_duration_seconds.observe(time.time() - start_time)
        return None


def save_trace_cache(cache_data: dict, cache_path: Path | str) -> bool:
    """Save a trace cache to disk.

    Args:
        cache_data: Cache data dictionary
        cache_path: Path to save the cache

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2)

        prom.trace_cache_writes_total.inc()
        logger.info(f"Trace cache saved to {cache_path}")
        return True
    except OSError as e:
        logger.error(f"Failed to save trace cache {cache_path}: {e}")
        return False


def delete_trace_cache(source_path: str, patterns: list[str], rg_flags: list[str]) -> bool:
    """Delete the trace cache file for a source file and patterns.

    Args:
        source_path: Path to the source file
        patterns: List of regex patterns
        rg_flags: List of ripgrep flags

    Returns:
        True if deleted (or didn't exist), False on error
    """
    cache_path = get_trace_cache_path(source_path, patterns, rg_flags)
    try:
        if cache_path.exists():
            cache_path.unlink()
            logger.info(f"Deleted trace cache for {source_path}")
        return True
    except OSError as e:
        logger.error(f"Failed to delete trace cache {cache_path}: {e}")
        return False


def get_cached_matches(
    source_path: str,
    patterns: list[str],
    rg_flags: list[str],
) -> list[dict] | None:
    """Get cached matches for a file and patterns.

    Args:
        source_path: Path to the source file
        patterns: List of regex patterns
        rg_flags: List of ripgrep flags

    Returns:
        List of cached match dicts, or None if no valid cache
    """
    if not is_trace_cache_valid(source_path, patterns, rg_flags):
        prom.trace_cache_misses_total.inc()
        return None

    cache_path = get_trace_cache_path(source_path, patterns, rg_flags)
    cache_data = load_trace_cache(cache_path)

    if cache_data is None:
        prom.trace_cache_misses_total.inc()
        return None

    prom.trace_cache_hits_total.inc()
    logger.info(f"Trace cache hit for {source_path} with {len(cache_data.get('matches', []))} matches")
    return cache_data.get("matches", [])


def build_cache_from_matches(
    source_path: str,
    patterns: list[str],
    rg_flags: list[str],
    matches: list[dict],
) -> dict:
    """Build a cache data structure from match results.

    Args:
        source_path: Path to the source file
        patterns: List of regex patterns
        rg_flags: List of ripgrep flags
        matches: List of match dicts from trace processing

    Returns:
        Cache data dictionary ready to be saved
    """
    abs_path = os.path.abspath(source_path)
    source_stat = os.stat(source_path)
    source_mtime = datetime.fromtimestamp(source_stat.st_mtime).isoformat()

    # Convert matches to cache format
    # We need to map pattern_id back to pattern_index
    pattern_id_to_index = {f"p{i + 1}": i for i in range(len(patterns))}

    cached_matches = []
    for match in matches:
        pattern_id = match.get("pattern", "p1")
        pattern_index = pattern_id_to_index.get(pattern_id, 0)

        cached_matches.append(
            {
                "pattern_index": pattern_index,
                "offset": match.get("offset", 0),
                "line_number": match.get("relative_line_number", 0),
            }
        )

    # Extract relevant flags for cache key
    relevant_flags = sorted([f for f in rg_flags if f in MATCHING_FLAGS])

    return {
        "version": TRACE_CACHE_VERSION,
        "source_path": abs_path,
        "source_modified_at": source_mtime,
        "source_size_bytes": source_stat.st_size,
        "patterns": patterns,
        "patterns_hash": compute_patterns_hash(patterns, rg_flags),
        "rg_flags": relevant_flags,
        "created_at": datetime.now().isoformat(),
        "matches": cached_matches,
    }


def reconstruct_match_data(
    source_path: str,
    cached_match: dict,
    patterns: list[str],
    pattern_ids: dict[str, str],
    file_id: str,
    rg_flags: list[str],
    context_before: int = 0,
    context_after: int = 0,
) -> tuple[dict, list[ContextLine]]:
    """Reconstruct full match data from a cached match entry.

    This function retrieves the actual line content and re-extracts submatches
    from the cached offset/line_number information.

    Args:
        source_path: Path to the source file
        cached_match: Cached match dict with pattern_index, offset, line_number
        patterns: List of regex patterns
        pattern_ids: Dict mapping pattern_id to pattern string
        file_id: File ID for this file (e.g., 'f1')
        rg_flags: List of ripgrep flags
        context_before: Number of context lines before match
        context_after: Number of context lines after match

    Returns:
        Tuple of (match_dict, context_lines)
    """
    line_number = cached_match.get("line_number", 1)
    offset = cached_match.get("offset", 0)
    pattern_index = cached_match.get("pattern_index", 0)

    # Get pattern info
    pattern = patterns[pattern_index] if pattern_index < len(patterns) else patterns[0]
    pattern_id = f"p{pattern_index + 1}"

    # Get line content + context using existing infrastructure
    context_data = get_context_by_lines(
        source_path,
        [line_number],
        context_before,
        context_after,
        use_index=True,
    )

    all_lines = context_data.get(line_number, [])

    # Find the matched line (middle of context window if context was requested)
    if context_before > 0 and len(all_lines) > context_before:
        matched_line_idx = context_before
    else:
        matched_line_idx = 0

    matched_line = all_lines[matched_line_idx] if all_lines else ""

    # Extract submatches by running pattern on line
    flags = re.IGNORECASE if "-i" in rg_flags else 0
    submatches = []
    try:
        for m in re.finditer(pattern, matched_line, flags):
            submatches.append(
                Submatch(
                    text=m.group(),
                    start=m.start(),
                    end=m.end(),
                )
            )
    except re.error as e:
        logger.debug(f"Failed to extract submatches for pattern {pattern}: {e}")

    # Build match dict in the same format as trace.py produces
    match_dict = {
        "pattern": pattern_id,
        "file": file_id,
        "offset": offset,
        "relative_line_number": line_number,
        "line_text": matched_line,
        "submatches": submatches,
    }

    # Build context lines
    context_lines = []
    start_line = max(1, line_number - context_before)

    for i, line in enumerate(all_lines):
        ctx_line_num = start_line + i
        # For the matched line, use the known offset; for others, use -1
        ctx_offset = offset if ctx_line_num == line_number else -1

        context_lines.append(
            ContextLine(
                relative_line_number=ctx_line_num,
                line_text=line,
                absolute_offset=ctx_offset,
            )
        )

    return match_dict, context_lines


def should_cache_file(
    file_size: int,
    max_results: int | None,
    scan_completed: bool,
) -> bool:
    """Determine if a file's trace results should be cached.

    Args:
        file_size: Size of the file in bytes
        max_results: Max results limit (None if no limit)
        scan_completed: Whether the scan completed without interruption

    Returns:
        True if the file should be cached
    """
    threshold = get_large_file_threshold_bytes()

    # Only cache large files
    if file_size < threshold:
        logger.debug(f"File too small for caching: {file_size} < {threshold}")
        prom.trace_cache_skip_total.inc()
        return False

    # Only cache complete scans (no max_results limit)
    if max_results is not None:
        logger.debug(f"Skipping cache: max_results={max_results} was set")
        prom.trace_cache_skip_total.inc()
        return False

    # Only cache if scan completed successfully
    if not scan_completed:
        logger.debug("Skipping cache: scan did not complete")
        prom.trace_cache_skip_total.inc()
        return False

    return True


def get_trace_cache_info(source_path: str, patterns: list[str], rg_flags: list[str]) -> dict | None:
    """Get information about an existing trace cache.

    Args:
        source_path: Path to the source file
        patterns: List of regex patterns
        rg_flags: List of ripgrep flags

    Returns:
        Dictionary with cache info, or None if no cache exists
    """
    cache_path = get_trace_cache_path(source_path, patterns, rg_flags)
    if not cache_path.exists():
        return None

    cache_data = load_trace_cache(cache_path)
    if cache_data is None:
        return None

    return {
        "cache_path": str(cache_path),
        "source_path": cache_data.get("source_path"),
        "source_size_bytes": cache_data.get("source_size_bytes"),
        "source_modified_at": cache_data.get("source_modified_at"),
        "created_at": cache_data.get("created_at"),
        "patterns": cache_data.get("patterns"),
        "patterns_hash": cache_data.get("patterns_hash"),
        "rg_flags": cache_data.get("rg_flags"),
        "match_count": len(cache_data.get("matches", [])),
        "is_valid": is_trace_cache_valid(source_path, patterns, rg_flags),
    }
