"""Unified analysis module for file indexing and anomaly detection.

This module provides:
- Anomaly detectors for log analysis
- Prefix pattern extraction using Drain3
- Memory-efficient helpers for large files
- Parallel prescan using ripgrep
"""

from .detectors import (
    AnomalyDetector,
    AnomalyRange,
    ErrorKeywordDetector,
    FormatDeviationDetector,
    HighEntropyDetector,
    IndentationBlockDetector,
    JsonDumpDetector,
    LineContext,
    LineLengthSpikeDetector,
    PrefixDeviationDetector,
    TimestampGapDetector,
    TracebackDetector,
    WarningKeywordDetector,
    default_detectors,
)
from .helpers import BoundedAnomalyHeap, SparseLineOffsets
from .prefix_pattern import PrefixPattern, PrefixPatternExtractor
from .prescan import PrescanMatch, rg_prescan_all_detectors, rg_prescan_keywords


__all__ = [
    # Base classes and data models
    'AnomalyDetector',
    'AnomalyRange',
    'LineContext',
    # Detectors
    'ErrorKeywordDetector',
    'FormatDeviationDetector',
    'HighEntropyDetector',
    'IndentationBlockDetector',
    'JsonDumpDetector',
    'LineLengthSpikeDetector',
    'PrefixDeviationDetector',
    'TimestampGapDetector',
    'TracebackDetector',
    'WarningKeywordDetector',
    # Factory
    'default_detectors',
    # Prefix pattern extraction
    'PrefixPattern',
    'PrefixPatternExtractor',
    # Helpers
    'BoundedAnomalyHeap',
    'SparseLineOffsets',
    # Prescan
    'PrescanMatch',
    'rg_prescan_all_detectors',
    'rg_prescan_keywords',
]
