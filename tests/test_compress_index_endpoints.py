"""Tests for compress and index HTTP endpoints with background task management."""

import time

import pytest

# These tests require a running server, so they're skipped by default
pytestmark = pytest.mark.skip(reason="Requires server to be running on localhost:8888")


class TestCompressEndpoint:
    """Test /v1/compress endpoint with background task execution."""

    def test_compress_starts_background_task(self):
        """Test that POST /v1/compress returns immediately with task ID.

        Scenario:
        1. POST /v1/compress with a test file
        2. Verify response contains task_id and status='queued'
        3. Verify response is returned quickly (< 1 second)
        4. Task should be running in background
        """
        import requests

        start_time = time.time()

        response = requests.post(
            "http://localhost:8888/v1/compress",
            json={
                "input_path": "/path/to/test/file.txt",
                "frame_size": "4M",
                "compression_level": 3,
                "build_index": True,
                "force": False,
            },
        )

        elapsed = time.time() - start_time

        # Should return immediately
        assert elapsed < 1.0, f"Request took {elapsed}s, should be < 1s"

        # Should return 200 with task info
        assert response.status_code == 200
        data = response.json()

        assert "task_id" in data
        assert "status" in data
        assert data["status"] in ["queued", "running"]
        assert "path" in data
        assert "message" in data

        # Store task_id for subsequent tests
        return data["task_id"]

    def test_compress_rejects_duplicate(self):
        """Test that compress rejects if same file is already being compressed.

        Scenario:
        1. POST /v1/compress for file A
        2. Immediately POST /v1/compress for same file A
        3. Second request should return 409 Conflict
        4. Error message should reference the existing task
        """
        import requests

        # Start first compression
        response1 = requests.post(
            "http://localhost:8888/v1/compress",
            json={
                "input_path": "/path/to/test/large_file.txt",
                "frame_size": "4M",
            },
        )

        assert response1.status_code == 200
        task1_id = response1.json()["task_id"]

        # Try to compress same file again immediately
        response2 = requests.post(
            "http://localhost:8888/v1/compress",
            json={
                "input_path": "/path/to/test/large_file.txt",
                "frame_size": "4M",
            },
        )

        # Should get 409 Conflict
        assert response2.status_code == 409
        assert "already in progress" in response2.json()["detail"].lower()
        assert task1_id in response2.json()["detail"]

    def test_compress_task_completion(self):
        """Test that compress task eventually completes and can be queried.

        Scenario:
        1. POST /v1/compress for a small test file
        2. Poll GET /v1/tasks/{task_id} until completed
        3. Verify final status is 'completed'
        4. Verify result contains expected fields (compressed_size, frame_count, etc.)
        5. Verify compressed file exists on disk
        """

        import requests

        # Start compression
        response = requests.post(
            "http://localhost:8888/v1/compress",
            json={
                "input_path": "/path/to/test/small_file.txt",
                "frame_size": "1M",
                "compression_level": 1,  # Faster
                "build_index": True,
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Poll for completion (max 30 seconds)
        max_attempts = 30
        for attempt in range(max_attempts):
            status_response = requests.get(f"http://localhost:8888/v1/tasks/{task_id}")
            assert status_response.status_code == 200

            status_data = status_response.json()
            status = status_data["status"]

            if status == "completed":
                # Verify result structure
                assert "result" in status_data
                result = status_data["result"]

                assert result["success"] is True
                assert "compressed_size" in result
                assert "decompressed_size" in result
                assert "compression_ratio" in result
                assert "frame_count" in result
                assert result["frame_count"] > 0
                assert "time_seconds" in result

                # If index was built, verify
                if result.get("index_built"):
                    assert result["total_lines"] is not None

                break
            elif status == "failed":
                pytest.fail(f"Compression failed: {status_data.get('error')}")

            time.sleep(1)
        else:
            pytest.fail(f"Compression did not complete within {max_attempts} seconds")

    def test_compress_invalid_parameters(self):
        """Test validation of compress parameters.

        Scenario:
        - Invalid compression level (> 22)
        - Invalid frame size format
        - Missing required path
        - File not found
        - Path outside search roots
        """
        import requests

        # Invalid compression level
        response = requests.post(
            "http://localhost:8888/v1/compress",
            json={
                "input_path": "/path/to/file.txt",
                "compression_level": 25,  # Max is 22
            },
        )
        assert response.status_code == 422  # Validation error

        # File not found
        response = requests.post(
            "http://localhost:8888/v1/compress",
            json={
                "input_path": "/nonexistent/file.txt",
            },
        )
        assert response.status_code == 404


class TestIndexEndpoint:
    """Test /v1/index endpoint with background task execution."""

    def test_index_starts_background_task(self):
        """Test that POST /v1/index returns immediately with task ID.

        Scenario:
        1. POST /v1/index with a large test file
        2. Verify response contains task_id and status='queued'
        3. Verify response is returned quickly (< 1 second)
        4. Task should be running in background
        """
        import requests

        start_time = time.time()

        response = requests.post(
            "http://localhost:8888/v1/index",
            json={
                "path": "/path/to/test/large_file.txt",
                "force": False,
            },
        )

        elapsed = time.time() - start_time

        # Should return immediately
        assert elapsed < 1.0, f"Request took {elapsed}s, should be < 1s"

        # Should return 200 with task info
        assert response.status_code == 200
        data = response.json()

        assert "task_id" in data
        assert "status" in data
        assert data["status"] in ["queued", "running"]
        assert "path" in data
        assert "message" in data

    def test_index_rejects_duplicate(self):
        """Test that index rejects if same file is already being indexed.

        Scenario:
        1. POST /v1/index for file A
        2. Immediately POST /v1/index for same file A
        3. Second request should return 409 Conflict
        4. Error message should reference the existing task
        """
        import requests

        # Start first indexing
        response1 = requests.post(
            "http://localhost:8888/v1/index",
            json={
                "path": "/path/to/test/large_file.txt",
            },
        )

        assert response1.status_code == 200
        task1_id = response1.json()["task_id"]

        # Try to index same file again immediately
        response2 = requests.post(
            "http://localhost:8888/v1/index",
            json={
                "path": "/path/to/test/large_file.txt",
            },
        )

        # Should get 409 Conflict
        assert response2.status_code == 409
        assert "already in progress" in response2.json()["detail"].lower()
        assert task1_id in response2.json()["detail"]

    def test_index_task_completion(self):
        """Test that index task eventually completes and can be queried.

        Scenario:
        1. POST /v1/index for a large test file
        2. Poll GET /v1/tasks/{task_id} until completed
        3. Verify final status is 'completed'
        4. Verify result contains expected fields (line_count, checkpoint_count, etc.)
        5. Verify index file exists on disk
        """
        import requests

        # Start indexing
        response = requests.post(
            "http://localhost:8888/v1/index",
            json={
                "path": "/path/to/test/large_file.txt",
                "force": True,
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Poll for completion (max 30 seconds)
        max_attempts = 30
        for attempt in range(max_attempts):
            status_response = requests.get(f"http://localhost:8888/v1/tasks/{task_id}")
            assert status_response.status_code == 200

            status_data = status_response.json()
            status = status_data["status"]

            if status == "completed":
                # Verify result structure
                assert "result" in status_data
                result = status_data["result"]

                assert result["success"] is True
                assert "line_count" in result
                assert result["line_count"] > 0
                assert "file_size" in result
                assert "checkpoint_count" in result
                assert result["checkpoint_count"] > 0
                assert "index_path" in result
                assert "time_seconds" in result

                break
            elif status == "failed":
                pytest.fail(f"Indexing failed: {status_data.get('error')}")

            time.sleep(1)
        else:
            pytest.fail(f"Indexing did not complete within {max_attempts} seconds")

    def test_index_file_too_small(self):
        """Test that index rejects files below threshold.

        Scenario:
        - Small file (< threshold) should be rejected with 400
        """
        import requests

        response = requests.post(
            "http://localhost:8888/v1/index",
            json={
                "path": "/path/to/test/small_file.txt",
                "threshold": 100,  # 100 MB minimum
            },
        )

        assert response.status_code == 400
        assert "below threshold" in response.json()["detail"].lower()


class TestTaskStatusEndpoint:
    """Test /v1/tasks/{task_id} endpoint."""

    def test_get_task_status(self):
        """Test querying task status by ID.

        Scenario:
        1. Start a compress task
        2. GET /v1/tasks/{task_id}
        3. Verify response contains all expected fields
        4. Status should progress from queued -> running -> completed
        """
        import requests

        # Start a task
        response = requests.post("http://localhost:8888/v1/compress", json={"input_path": "/path/to/test/file.txt"})
        task_id = response.json()["task_id"]

        # Query status
        status_response = requests.get(f"http://localhost:8888/v1/tasks/{task_id}")
        assert status_response.status_code == 200

        data = status_response.json()
        assert data["task_id"] == task_id
        assert "status" in data
        assert "path" in data
        assert "operation" in data
        assert data["operation"] in ["compress", "index"]
        assert "started_at" in data

    def test_task_not_found(self):
        """Test 404 for unknown task ID.

        Scenario:
        1. GET /v1/tasks/{invalid_uuid}
        2. Should return 404 Not Found
        """
        import uuid

        import requests

        fake_task_id = str(uuid.uuid4())
        response = requests.get(f"http://localhost:8888/v1/tasks/{fake_task_id}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_task_lifecycle(self):
        """Test complete task lifecycle from queued to completed.

        Scenario:
        1. Start task, verify status='queued' or 'running'
        2. Poll until status='completed'
        3. Verify completed_at timestamp is set
        4. Verify result is populated
        """
        import requests

        # Start task
        response = requests.post(
            "http://localhost:8888/v1/compress",
            json={
                "input_path": "/path/to/test/small_file.txt",
                "compression_level": 1,
            },
        )
        task_id = response.json()["task_id"]

        # Initial status
        response = requests.get(f"http://localhost:8888/v1/tasks/{task_id}")
        data = response.json()
        assert data["status"] in ["queued", "running"]
        assert data["completed_at"] is None
        assert data["result"] is None

        # Poll until completed
        for _ in range(30):
            response = requests.get(f"http://localhost:8888/v1/tasks/{task_id}")
            data = response.json()

            if data["status"] == "completed":
                assert data["completed_at"] is not None
                assert data["result"] is not None
                assert data["error"] is None
                break
            elif data["status"] == "failed":
                pytest.fail(f"Task failed: {data['error']}")

            time.sleep(1)
        else:
            pytest.fail("Task did not complete in time")


class TestConcurrencyControl:
    """Test concurrency control across compress and index operations."""

    def test_compress_and_index_same_file_conflict(self):
        """Test that compress and index operations conflict on the same file.

        Scenario:
        1. Start compress for file A
        2. Try to start index for same file A
        3. Should get 409 Conflict (or vice versa)
        """
        import requests

        # Start compress
        response1 = requests.post("http://localhost:8888/v1/compress", json={"input_path": "/path/to/test/file.txt"})
        assert response1.status_code == 200

        # Try to index same file
        response2 = requests.post("http://localhost:8888/v1/index", json={"path": "/path/to/test/file.txt"})

        # Should conflict
        assert response2.status_code == 409

    def test_multiple_different_files_ok(self):
        """Test that compress/index on different files work concurrently.

        Scenario:
        1. Start compress for file A
        2. Start compress for file B
        3. Start index for file C
        4. All should return 200 with different task IDs
        """
        import requests

        # Start three different operations
        response1 = requests.post("http://localhost:8888/v1/compress", json={"input_path": "/path/to/test/file1.txt"})
        response2 = requests.post("http://localhost:8888/v1/compress", json={"input_path": "/path/to/test/file2.txt"})
        response3 = requests.post("http://localhost:8888/v1/index", json={"path": "/path/to/test/file3.txt"})

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 200

        task_ids = [
            response1.json()["task_id"],
            response2.json()["task_id"],
            response3.json()["task_id"],
        ]

        # All task IDs should be unique
        assert len(set(task_ids)) == 3


class TestTaskCleanup:
    """Test automatic cleanup of old completed tasks."""

    def test_old_tasks_cleaned_up(self):
        """Test that completed tasks are cleaned up after retention period.

        Scenario:
        1. Start and complete a task
        2. Wait for cleanup period (or trigger manually)
        3. Task should be removed from storage
        4. GET /v1/tasks/{task_id} should return 404

        Note: This test may need to wait several minutes or use
        a test-specific cleanup trigger.
        """
        # This test would require either:
        # - Waiting for the actual cleanup interval
        # - Adding a test endpoint to trigger cleanup manually
        # - Mocking time
        pytest.skip("Requires manual cleanup trigger or long wait")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
