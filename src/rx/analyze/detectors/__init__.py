"""Anomaly detection modules.

This package contains all anomaly detectors for log analysis.
"""

from .base import AnomalyDetector, AnomalyRange, LineContext
from .error_keyword import ErrorKeywordDetector
from .format_deviation import FormatDeviationDetector
from .high_entropy import HighEntropyDetector
from .indentation import IndentationBlockDetector
from .json_dump import JsonDumpDetector
from .line_length import LineLengthSpikeDetector
from .prefix_deviation import PrefixDeviationDetector
from .timestamp_gap import TimestampGapDetector
from .traceback import TracebackDetector
from .warning_keyword import WarningKeywordDetector


__all__ = [
    # Base classes
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
]


def default_detectors(filepath: str | None = None) -> list[AnomalyDetector]:
    """Get list of default anomaly detectors.

    Args:
        filepath: Path to file being analyzed (for logging context).

    Returns:
        List of instantiated detector objects.
    """
    return [
        TracebackDetector(filepath=filepath),
        ErrorKeywordDetector(filepath=filepath),
        WarningKeywordDetector(filepath=filepath),
        LineLengthSpikeDetector(filepath=filepath),
        IndentationBlockDetector(filepath=filepath),
        TimestampGapDetector(filepath=filepath),
        HighEntropyDetector(filepath=filepath),
        JsonDumpDetector(filepath=filepath),
        FormatDeviationDetector(filepath=filepath),
    ]
