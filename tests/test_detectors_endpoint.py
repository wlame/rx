"""Tests for /v1/detectors endpoint and detector registry."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from rx.analyze.detectors.base import (
    CATEGORY_DESCRIPTIONS,
    get_category_info_list,
    get_detector_info_list,
    get_registered_detectors,
    get_severity_scale,
)
from rx.web import app


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests and set it as search root."""
    tmp_dir = tempfile.mkdtemp()
    resolved_tmp_dir = os.path.realpath(tmp_dir)
    old_env = os.environ.get('RX_SEARCH_ROOT')
    os.environ['RX_SEARCH_ROOT'] = resolved_tmp_dir
    yield resolved_tmp_dir
    import shutil

    shutil.rmtree(resolved_tmp_dir, ignore_errors=True)
    if old_env is not None:
        os.environ['RX_SEARCH_ROOT'] = old_env
    elif 'RX_SEARCH_ROOT' in os.environ:
        del os.environ['RX_SEARCH_ROOT']


@pytest.fixture
def client(temp_dir):
    """Create test client with search root set to temp directory."""
    with TestClient(app) as c:
        yield c


class TestDetectorRegistry:
    """Tests for the detector registry system."""

    def test_registry_contains_all_detectors(self):
        """Test that all expected detectors are registered."""
        # Import detectors to trigger registration
        import rx.analyze.detectors  # noqa: F401

        registry = get_registered_detectors()

        # Check that we have the expected detectors
        expected_detectors = [
            'traceback',
            'error_keyword',
            'warning_keyword',
            'line_length_spike',
            'indentation_block',
            'format_deviation',
            'high_entropy',
            'timestamp_gap',
            'json_dump',
            'prefix_deviation',
        ]

        for detector_name in expected_detectors:
            assert detector_name in registry, f'Detector {detector_name} not registered'

    def test_get_detector_info_list_returns_all_detectors(self):
        """Test that get_detector_info_list returns info for all detectors."""
        import rx.analyze.detectors  # noqa: F401

        info_list = get_detector_info_list()

        # Should have at least 10 detectors
        assert len(info_list) >= 10

        # Each entry should have required fields
        for info in info_list:
            assert 'name' in info
            assert 'category' in info
            assert 'description' in info
            assert 'severity_range' in info
            assert 'examples' in info

            # Severity range should have min and max
            assert 'min' in info['severity_range']
            assert 'max' in info['severity_range']
            assert 0.0 <= info['severity_range']['min'] <= 1.0
            assert 0.0 <= info['severity_range']['max'] <= 1.0
            assert info['severity_range']['min'] <= info['severity_range']['max']

    def test_get_category_info_list_returns_categories(self):
        """Test that get_category_info_list returns category info."""
        import rx.analyze.detectors  # noqa: F401

        categories = get_category_info_list()

        # Should have multiple categories
        assert len(categories) >= 4

        # Each category should have required fields
        for cat in categories:
            assert 'name' in cat
            assert 'description' in cat
            assert 'detectors' in cat
            assert isinstance(cat['detectors'], list)
            assert len(cat['detectors']) > 0  # Each category should have at least one detector

    def test_get_severity_scale_returns_scale(self):
        """Test that get_severity_scale returns the severity scale."""
        scale = get_severity_scale()

        # Should have 4 levels
        assert len(scale) == 4

        # Each level should have required fields
        for level in scale:
            assert 'min' in level
            assert 'max' in level
            assert 'label' in level
            assert 'description' in level
            assert 0.0 <= level['min'] <= 1.0
            assert 0.0 <= level['max'] <= 1.0

        # Check that labels are correct
        labels = [level['label'] for level in scale]
        assert 'critical' in labels
        assert 'high' in labels
        assert 'medium' in labels
        assert 'low' in labels

    def test_category_descriptions_complete(self):
        """Test that CATEGORY_DESCRIPTIONS has entries for known categories."""
        import rx.analyze.detectors  # noqa: F401

        categories = get_category_info_list()
        category_names = {cat['name'] for cat in categories}

        # All categories used by detectors should have descriptions
        for cat_name in category_names:
            assert cat_name in CATEGORY_DESCRIPTIONS, f'Missing description for category: {cat_name}'


class TestDetectorsEndpoint:
    """Tests for the /v1/detectors API endpoint."""

    def test_detectors_endpoint_returns_200(self, client):
        """Test that /v1/detectors returns 200."""
        response = client.get('/v1/detectors')
        assert response.status_code == 200

    def test_detectors_endpoint_returns_valid_structure(self, client):
        """Test that /v1/detectors returns the expected structure."""
        response = client.get('/v1/detectors')
        assert response.status_code == 200

        data = response.json()

        # Check top-level keys
        assert 'detectors' in data
        assert 'categories' in data
        assert 'severity_scale' in data

        # Check types
        assert isinstance(data['detectors'], list)
        assert isinstance(data['categories'], list)
        assert isinstance(data['severity_scale'], list)

    def test_detectors_endpoint_contains_all_detectors(self, client):
        """Test that all detectors are included in the response."""
        response = client.get('/v1/detectors')
        assert response.status_code == 200

        data = response.json()
        detector_names = [d['name'] for d in data['detectors']]

        # Check for expected detectors
        expected = [
            'traceback',
            'error_keyword',
            'warning_keyword',
            'line_length_spike',
            'indentation_block',
            'format_deviation',
            'high_entropy',
            'timestamp_gap',
            'json_dump',
            'prefix_deviation',
        ]

        for name in expected:
            assert name in detector_names, f'Detector {name} not in response'

    def test_detectors_have_valid_metadata(self, client):
        """Test that each detector has valid metadata."""
        response = client.get('/v1/detectors')
        assert response.status_code == 200

        data = response.json()

        for detector in data['detectors']:
            # Required fields
            assert 'name' in detector
            assert 'category' in detector
            assert 'description' in detector
            assert 'severity_range' in detector
            assert 'examples' in detector

            # Description should not be empty
            assert len(detector['description']) > 10, f'Detector {detector["name"]} has too short description'

            # Severity range validation
            severity = detector['severity_range']
            assert 'min' in severity
            assert 'max' in severity
            assert 0.0 <= severity['min'] <= 1.0
            assert 0.0 <= severity['max'] <= 1.0
            assert severity['min'] <= severity['max']

            # Examples should be a list
            assert isinstance(detector['examples'], list)

    def test_categories_have_valid_metadata(self, client):
        """Test that each category has valid metadata."""
        response = client.get('/v1/detectors')
        assert response.status_code == 200

        data = response.json()

        for category in data['categories']:
            assert 'name' in category
            assert 'description' in category
            assert 'detectors' in category

            # Description should not be empty
            assert len(category['description']) > 10

            # Detectors list should not be empty
            assert len(category['detectors']) > 0

    def test_severity_scale_is_complete(self, client):
        """Test that severity scale has all expected levels."""
        response = client.get('/v1/detectors')
        assert response.status_code == 200

        data = response.json()
        scale = data['severity_scale']

        # Should have 4 levels
        assert len(scale) == 4

        labels = [level['label'] for level in scale]
        assert 'critical' in labels
        assert 'high' in labels
        assert 'medium' in labels
        assert 'low' in labels

    def test_severity_scale_covers_full_range(self, client):
        """Test that severity scale covers 0.0 to 1.0."""
        response = client.get('/v1/detectors')
        assert response.status_code == 200

        data = response.json()
        scale = data['severity_scale']

        # Find min and max across all levels
        all_mins = [level['min'] for level in scale]
        all_maxs = [level['max'] for level in scale]

        assert min(all_mins) == 0.0
        assert max(all_maxs) == 1.0

    def test_detectors_sorted_by_category_and_name(self, client):
        """Test that detectors are sorted by category then name."""
        response = client.get('/v1/detectors')
        assert response.status_code == 200

        data = response.json()
        detectors = data['detectors']

        # Extract category-name pairs
        pairs = [(d['category'], d['name']) for d in detectors]

        # Check if sorted
        assert pairs == sorted(pairs)

    def test_category_detectors_match_detector_list(self, client):
        """Test that category detector lists match the actual detectors."""
        response = client.get('/v1/detectors')
        assert response.status_code == 200

        data = response.json()

        # Build category -> detectors mapping from detectors list
        detector_categories = {}
        for d in data['detectors']:
            cat = d['category']
            if cat not in detector_categories:
                detector_categories[cat] = []
            detector_categories[cat].append(d['name'])

        # Check that each category's detector list matches
        for category in data['categories']:
            cat_name = category['name']
            assert cat_name in detector_categories, f'Category {cat_name} has no detectors'
            expected_detectors = sorted(detector_categories[cat_name])
            actual_detectors = sorted(category['detectors'])
            assert expected_detectors == actual_detectors, f'Detector mismatch for category {cat_name}'


class TestDetectorMetadataProperties:
    """Tests for individual detector metadata properties."""

    def test_traceback_detector_metadata(self):
        """Test traceback detector has correct metadata."""
        from rx.analyze.detectors.traceback import TracebackDetector

        detector = TracebackDetector(filepath=None)

        assert detector.name == 'traceback'
        assert detector.category == 'traceback'
        assert detector.severity_min > 0.5  # Should be high severity
        assert detector.severity_max <= 1.0
        assert len(detector.detector_description) > 10
        assert len(detector.examples) > 0

    def test_error_keyword_detector_metadata(self):
        """Test error keyword detector has correct metadata."""
        from rx.analyze.detectors.error_keyword import ErrorKeywordDetector

        detector = ErrorKeywordDetector(filepath=None)

        assert detector.name == 'error_keyword'
        assert detector.category == 'error'
        assert detector.severity_min >= 0.5
        assert detector.severity_max <= 1.0
        assert len(detector.examples) > 0

    def test_high_entropy_detector_metadata(self):
        """Test high entropy detector has correct metadata."""
        from rx.analyze.detectors.high_entropy import HighEntropyDetector

        detector = HighEntropyDetector(filepath=None)

        assert detector.name == 'high_entropy'
        assert detector.category == 'security'
        assert len(detector.detector_description) > 10
        assert 'secret' in detector.detector_description.lower() or 'token' in detector.detector_description.lower()

    def test_timestamp_gap_detector_metadata(self):
        """Test timestamp gap detector has correct metadata."""
        from rx.analyze.detectors.timestamp_gap import TimestampGapDetector

        detector = TimestampGapDetector(filepath=None)

        assert detector.name == 'timestamp_gap'
        assert detector.category == 'timing'
        assert len(detector.detector_description) > 10
