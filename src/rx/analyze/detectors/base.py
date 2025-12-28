"""Base classes and data models for anomaly detection."""

import re
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass


# =============================================================================
# Detector Registry
# =============================================================================

# Global registry of detector classes
_detector_registry: dict[str, type['AnomalyDetector']] = {}

# Category descriptions
CATEGORY_DESCRIPTIONS: dict[str, str] = {
    'error': 'Error-level log messages indicating failures or exceptions',
    'warning': 'Warning-level log messages indicating potential issues',
    'traceback': 'Stack traces and exception backtraces from various languages',
    'format': 'Format anomalies such as unusually long lines, JSON dumps, or prefix deviations',
    'security': 'Potential secrets, tokens, API keys, or other sensitive data',
    'timing': 'Timestamp gaps or timing anomalies in log sequences',
    'multiline': 'Multi-line content blocks such as indented data or configurations',
}

# Severity scale definition
SEVERITY_SCALE = [
    {
        'min': 0.8,
        'max': 1.0,
        'label': 'critical',
        'description': 'Critical issues: FATAL errors, exposed secrets, system panics',
    },
    {
        'min': 0.6,
        'max': 0.8,
        'label': 'high',
        'description': 'High severity: ERROR messages, crashes, large timestamp gaps',
    },
    {
        'min': 0.4,
        'max': 0.6,
        'label': 'medium',
        'description': 'Medium severity: warnings, format deviations, potential issues',
    },
    {'min': 0.0, 'max': 0.4, 'label': 'low', 'description': 'Low severity: minor deviations, informational anomalies'},
]


def register_detector(cls: type['AnomalyDetector']) -> type['AnomalyDetector']:
    """Decorator to register a detector class in the global registry.

    Usage:
        @register_detector
        class MyDetector(AnomalyDetector):
            ...
    """
    # Create a temporary instance to get name
    # We need to handle detectors that require filepath arg
    try:
        instance = cls(filepath=None)  # type: ignore
    except TypeError:
        try:
            instance = cls()  # type: ignore
        except TypeError:
            # Can't instantiate, skip registration
            return cls

    _detector_registry[instance.name] = cls
    return cls


def get_registered_detectors() -> dict[str, type['AnomalyDetector']]:
    """Get all registered detector classes."""
    return _detector_registry.copy()


def get_detector_info_list() -> list[dict]:
    """Get metadata for all registered detectors.

    Returns:
        List of detector info dictionaries with name, category, description,
        severity_range, and examples.
    """
    result = []
    for name, cls in _detector_registry.items():
        try:
            instance = cls(filepath=None)  # type: ignore
        except TypeError:
            try:
                instance = cls()  # type: ignore
            except TypeError:
                continue

        info = {
            'name': instance.name,
            'category': instance.category,
            'description': instance.detector_description,
            'severity_range': {
                'min': instance.severity_min,
                'max': instance.severity_max,
            },
            'examples': instance.examples,
        }
        result.append(info)

    # Sort by category then name
    result.sort(key=lambda x: (x['category'], x['name']))
    return result


def get_category_info_list() -> list[dict]:
    """Get metadata for all categories with their detectors.

    Returns:
        List of category info dictionaries.
    """
    # Collect detectors by category
    categories: dict[str, list[str]] = {}
    for name, cls in _detector_registry.items():
        try:
            instance = cls(filepath=None)  # type: ignore
        except TypeError:
            try:
                instance = cls()  # type: ignore
            except TypeError:
                continue

        cat = instance.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(instance.name)

    result = []
    for cat_name, detector_names in sorted(categories.items()):
        result.append(
            {
                'name': cat_name,
                'description': CATEGORY_DESCRIPTIONS.get(cat_name, f'Anomalies of type {cat_name}'),
                'detectors': sorted(detector_names),
            }
        )

    return result


def get_severity_scale() -> list[dict]:
    """Get the severity scale definition."""
    return SEVERITY_SCALE.copy()


@dataclass
class AnomalyRange:
    """Represents a detected anomaly in a file.

    Anomalies are line ranges that have been flagged by detectors as
    interesting or potentially problematic (e.g., stack traces, errors).
    """

    start_line: int  # First line of anomaly (1-based)
    end_line: int  # Last line of anomaly (inclusive, 1-based)
    start_offset: int  # Byte offset of start
    end_offset: int  # Byte offset of end
    severity: float  # 0.0 to 1.0 (higher = more severe)
    category: str  # e.g., "traceback", "error", "format_deviation"
    description: str  # Human-readable description
    detector: str  # Name of detector that found it


@dataclass
class LineContext:
    """Context provided to each anomaly detector for a line.

    This provides both the current line and surrounding context
    to allow detectors to make informed decisions.
    """

    line: str  # Current line content
    line_number: int  # 1-based line number
    byte_offset: int  # Byte offset in file
    window: deque[str]  # Sliding window of previous N lines
    line_lengths: deque[int]  # Lengths of lines in window
    avg_line_length: float  # Running average line length
    stddev_line_length: float  # Running stddev of line length


class AnomalyDetector(ABC):
    """Base class for all anomaly detectors.

    Subclass this to create custom anomaly detectors. Each detector
    should focus on detecting a specific type of anomaly.

    To register a detector for the /v1/detectors API, use the @register_detector
    decorator and implement the metadata properties (detector_description,
    severity_min, severity_max, examples).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Detector identifier (e.g., 'traceback', 'error_keyword')."""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """Anomaly category (e.g., 'traceback', 'error', 'format')."""
        pass

    @property
    def detector_description(self) -> str:
        """Human-readable description of what the detector finds.

        Override this to provide a meaningful description for the API.
        """
        return f'Detects {self.category} anomalies'

    @property
    def severity_min(self) -> float:
        """Minimum severity score this detector produces.

        Override this to specify the actual range.
        """
        return 0.0

    @property
    def severity_max(self) -> float:
        """Maximum severity score this detector produces.

        Override this to specify the actual range.
        """
        return 1.0

    @property
    def examples(self) -> list[str]:
        """Example patterns or keywords this detector looks for.

        Override this to provide examples for the API.
        """
        return []

    @abstractmethod
    def check_line(self, ctx: LineContext) -> float | None:
        """Check if current line is anomalous.

        Args:
            ctx: Line context with current line and surrounding context.

        Returns:
            Severity score (0.0-1.0) if anomalous, None otherwise.
        """
        pass

    def should_merge_with_previous(self, ctx: LineContext, prev_severity: float) -> bool:
        """Return True if this line should be merged with previous anomaly.

        Override this for multi-line anomalies (e.g., stack traces).

        Args:
            ctx: Current line context.
            prev_severity: Severity of the previous anomaly line.

        Returns:
            True if this line should be merged with the previous anomaly.
        """
        return False

    def get_description(self, lines: list[str]) -> str:
        """Generate description for a detected anomaly range.

        Override to provide more specific descriptions.

        Args:
            lines: List of lines in the anomaly range.

        Returns:
            Human-readable description of the anomaly.
        """
        return f'Detected by {self.name}'

    def get_prescan_patterns(self) -> list[tuple[re.Pattern, float]]:
        """Return regex patterns for ripgrep prescan optimization.

        Override to enable fast prescan using ripgrep. Return a list of
        (pattern, severity) tuples that can identify potential anomaly lines.

        Returns:
            List of (compiled regex pattern, severity) tuples, or empty list
            if this detector doesn't support prescan.
        """
        return []
