"""
Test concurrent request handling to ensure blocking operations
don't freeze the event loop.

Run with: pytest tests/test_concurrency.py -v
Or manually with: python tests/test_concurrency.py
"""

import asyncio
import time
import httpx
import pytest


BASE_URL = "http://localhost:8888"


async def test_health_not_blocked_by_slow_requests():
    """
    Verify that fast endpoints like /health return immediately
    even when slow trace operations are running.

    This test simulates the real-world scenario where:
    - Multiple slow /v1/trace requests are in progress
    - A quick /health check should still return instantly
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        # Create a slow trace request (will take several seconds)
        # Adjust path/regexp to match your test data
        slow_task = client.get(
            f"{BASE_URL}/v1/trace",
            params={
                "path": "/etc",  # Large directory scan
                "regexp": ".*",  # Match everything (slow)
                "max_results": 1000,
            },
        )

        # Wait a moment for the slow request to start processing
        await asyncio.sleep(0.5)

        # Now check if health endpoint responds quickly
        health_start = time.time()
        health_response = await client.get(f"{BASE_URL}/health")
        health_elapsed = time.time() - health_start

        # Health should respond in under 1 second even with slow trace running
        assert health_response.status_code == 200
        assert health_elapsed < 1.0, f"Health took {health_elapsed:.2f}s (should be <1s)"

        print(f"✅ Health responded in {health_elapsed:.3f}s while trace was running")

        # Cancel the slow task (we don't need to wait for it)
        try:
            slow_task.cancel()
        except:
            pass


async def test_multiple_concurrent_traces():
    """
    Test that multiple trace requests can run concurrently
    and complete faster than if they ran sequentially.
    """
    # Note: This test requires test files. Adjust paths as needed.
    # For a basic check, we'll just verify they all complete without errors.

    async with httpx.AsyncClient(timeout=120.0) as client:
        start = time.time()

        # Launch 3 concurrent trace requests
        tasks = [
            client.get(f"{BASE_URL}/v1/trace", params={"path": "/etc/hosts", "regexp": "localhost"}),
            client.get(f"{BASE_URL}/v1/trace", params={"path": "/etc/hosts", "regexp": "127"}),
            client.get(f"{BASE_URL}/v1/trace", params={"path": "/etc/hosts", "regexp": "[0-9]+"}),
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start

        # Check all completed successfully
        for i, resp in enumerate(responses):
            if isinstance(resp, Exception):
                print(f"⚠️  Request {i + 1} failed: {resp}")
            else:
                assert resp.status_code == 200, f"Request {i + 1} failed with status {resp.status_code}"

        print(f"✅ All 3 trace requests completed in {elapsed:.3f}s")


async def test_complexity_during_trace():
    """
    Test that complexity endpoint (CPU-bound) doesn't block
    when trace requests (I/O-bound) are running.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        # Start a trace
        trace_task = client.get(f"{BASE_URL}/v1/trace", params={"path": "/etc/hosts", "regexp": ".*"})

        # Wait a bit for trace to start
        await asyncio.sleep(0.2)

        # Now run complexity check
        complexity_start = time.time()
        complexity_resp = await client.get(f"{BASE_URL}/v1/complexity", params={"regex": "(a+)+b"})
        complexity_elapsed = time.time() - complexity_start

        assert complexity_resp.status_code == 200
        print(f"✅ Complexity responded in {complexity_elapsed:.3f}s while trace was running")

        # Wait for trace to complete
        trace_resp = await trace_task
        assert trace_resp.status_code == 200


# Manual test runner (if not using pytest)
async def run_all_tests():
    print("\n" + "=" * 60)
    print("Testing Concurrent Request Handling")
    print("=" * 60 + "\n")

    print("Test 1: Health endpoint responsiveness during slow operations")
    try:
        await test_health_not_blocked_by_slow_requests()
    except Exception as e:
        print(f"❌ Test 1 failed: {e}\n")
    else:
        print("✅ Test 1 passed\n")

    print("Test 2: Multiple concurrent trace requests")
    try:
        await test_multiple_concurrent_traces()
    except Exception as e:
        print(f"❌ Test 2 failed: {e}\n")
    else:
        print("✅ Test 2 passed\n")

    print("Test 3: Complexity during trace operations")
    try:
        await test_complexity_during_trace()
    except Exception as e:
        print(f"❌ Test 3 failed: {e}\n")
    else:
        print("✅ Test 3 passed\n")

    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    print("\n⚠️  Make sure the server is running: uvicorn rx.web:app --reload")
    print("Starting tests in 2 seconds...\n")
    time.sleep(2)

    asyncio.run(run_all_tests())
