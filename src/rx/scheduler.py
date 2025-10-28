"""Multi-file parsing scheduler for efficient parallel processing"""

import os
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class FileTask:
    """Represents a file and its allocated worker count"""

    filepath: str
    file_size: int
    num_workers: int  # Number of parallel workers allocated to this file


def calculate_file_workers(
    filepaths: List[str], max_subprocesses: int = 20, min_chunk_size_mb: int = 20 * 1024 * 1024
) -> List[FileTask]:
    """
    Calculate optimal worker allocation for multiple files.

    Strategy:
    1. Calculate potential chunks for each file (file_size / min_chunk_size)
    2. Small files (< min_chunk_size) get 1 worker
    3. Large files get workers proportional to their size
    4. Total workers never exceed max_subprocesses

    Args:
        filepaths: List of file paths to process
        max_subprocesses: Maximum total parallel workers
        min_chunk_size_mb: Minimum chunk size in bytes

    Returns:
        List of FileTask with worker allocation

    Examples:
        # 3 small files (5MB each) + 1 large file (200MB), max_workers=20
        # Small files: 3 workers (1 each)
        # Large file: 17 workers (200MB / 20MB = 10 potential, but we have 17 available)

        # 100 small files (5MB each), max_workers=20
        # Each file gets 1 worker, but only 20 files processed at a time
        # This requires batching (handled by caller)
    """
    if not filepaths:
        return []

    # Get file sizes
    file_info = []
    for filepath in filepaths:
        if os.path.exists(filepath) and os.path.isfile(filepath):
            size = os.path.getsize(filepath)
            file_info.append({'path': filepath, 'size': size})

    if not file_info:
        return []

    # Calculate potential chunks for each file
    for info in file_info:
        # How many chunks this file COULD use (unconstrained)
        potential_chunks = max(1, info['size'] // min_chunk_size_mb)
        info['potential_chunks'] = potential_chunks

    # Total potential chunks across all files
    total_potential = sum(info['potential_chunks'] for info in file_info)

    # Allocate workers proportionally
    tasks = []
    total_allocated = 0

    for i, info in enumerate(file_info):
        if i == len(file_info) - 1:
            # Last file gets remaining workers
            workers = max_subprocesses - total_allocated
        else:
            # Proportional allocation: (file_potential / total_potential) * max_workers
            if total_potential > 0:
                proportion = info['potential_chunks'] / total_potential
                workers = max(1, int(proportion * max_subprocesses))
            else:
                workers = 1

            # Cap by file's actual potential
            workers = min(workers, info['potential_chunks'])

        # Ensure at least 1 worker per file
        workers = max(1, workers)

        # Cap by remaining workers
        workers = min(workers, max_subprocesses - total_allocated)

        if workers > 0:
            tasks.append(FileTask(filepath=info['path'], file_size=info['size'], num_workers=workers))
            total_allocated += workers

        # Stop if we've allocated all workers
        if total_allocated >= max_subprocesses:
            # Remaining files get added with 0 workers (will need batching)
            for remaining in file_info[i + 1 :]:
                tasks.append(FileTask(filepath=remaining['path'], file_size=remaining['size'], num_workers=0))
            break

    return tasks


def create_batches(tasks: List[FileTask], max_workers: int) -> List[List[FileTask]]:
    """
    Create batches of files that can be processed in parallel.
    Files with 0 workers are distributed across batches.

    Args:
        tasks: List of FileTask from calculate_file_workers
        max_workers: Maximum parallel workers

    Returns:
        List of batches, where each batch can run in parallel
    """
    # First batch: all files with allocated workers
    first_batch = [t for t in tasks if t.num_workers > 0]

    # Remaining files: those with 0 workers
    remaining = [t for t in tasks if t.num_workers == 0]

    batches = [first_batch] if first_batch else []

    # Create additional batches for remaining files
    # Each file in remaining batches gets proportional workers
    while remaining:
        batch = []
        batch_files = remaining[:max_workers]  # Take up to max_workers files
        remaining = remaining[max_workers:]

        # Recalculate workers for this batch
        batch_tasks = calculate_file_workers(
            [t.filepath for t in batch_files],
            max_workers,
            20 * 1024 * 1024,  # This should be parameterized
        )
        batch.extend(batch_tasks)
        batches.append(batch)

    return batches


# Example usage and tests
if __name__ == "__main__":
    # Example 1: Mixed file sizes
    print("Example 1: 3 small files + 1 large file")
    print("=" * 60)

    # Simulate file sizes
    test_files = {
        "small1.log": 5 * 1024 * 1024,  # 5MB
        "small2.log": 8 * 1024 * 1024,  # 8MB
        "small3.log": 3 * 1024 * 1024,  # 3MB
        "large.log": 200 * 1024 * 1024,  # 200MB
    }

    # Create temp info (simulating files)
    tasks = calculate_file_workers(list(test_files.keys()), max_subprocesses=20, min_chunk_size_mb=20 * 1024 * 1024)

    for task in tasks:
        size_mb = test_files[task.filepath] / (1024 * 1024)
        print(f"{task.filepath:20} {size_mb:6.1f}MB -> {task.num_workers:2} workers")

    print(f"\nTotal workers allocated: {sum(t.num_workers for t in tasks)}")

    print("\n" + "=" * 60)
    print("Example 2: Many small files (30 x 5MB)")
    print("=" * 60)

    many_small = {f"file{i:02d}.log": 5 * 1024 * 1024 for i in range(30)}

    tasks = calculate_file_workers(list(many_small.keys()), max_subprocesses=20, min_chunk_size_mb=20 * 1024 * 1024)

    files_with_workers = [t for t in tasks if t.num_workers > 0]
    files_without_workers = [t for t in tasks if t.num_workers == 0]

    print(f"Files with workers: {len(files_with_workers)}")
    print(f"Files queued (0 workers): {len(files_without_workers)}")
    print(f"Total workers used: {sum(t.num_workers for t in tasks)}")

    # Show batching
    batches = create_batches(tasks, max_workers=20)
    print(f"\nBatches needed: {len(batches)}")
    for i, batch in enumerate(batches):
        print(f"  Batch {i + 1}: {len(batch)} files, {sum(t.num_workers for t in batch)} workers")
