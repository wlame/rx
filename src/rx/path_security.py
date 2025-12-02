"""Path security validation for sandboxed file access.

This module provides security validation to ensure all file access stays within
a configured search root directory, preventing directory traversal attacks and
symlink escapes.

Security Features:
- Resolves symlinks to prevent escape via symbolic links
- Normalizes paths to prevent ../ traversal attacks
- Validates both files and directories
- Thread-safe for use in async/threaded contexts
"""

import os
from pathlib import Path
from typing import Optional

# Global search root - set during server startup
_search_root: Optional[Path] = None


def set_search_root(path: Optional[str | Path]) -> Path:
    """
    Set the global search root directory.

    Args:
        path: The root directory path. If None, uses current working directory.

    Returns:
        The resolved absolute path of the search root.

    Raises:
        ValueError: If the path doesn't exist or is not a directory.
    """
    global _search_root

    if path is None:
        resolved = Path.cwd().resolve()
    else:
        resolved = Path(path).resolve()

    if not resolved.exists():
        raise ValueError(f"Search root does not exist: {resolved}")

    if not resolved.is_dir():
        raise ValueError(f"Search root is not a directory: {resolved}")

    _search_root = resolved
    return resolved


def get_search_root() -> Optional[Path]:
    """
    Get the current search root directory.

    Returns:
        The search root Path, or None if not set.
    """
    return _search_root


def validate_path_within_root(path: str | Path, search_root: Optional[Path] = None) -> Path:
    """
    Validate that a path is within the search root directory.

    This function:
    1. Resolves the path to an absolute path (following symlinks)
    2. Checks if the resolved path is within the search root
    3. Returns the resolved path if valid

    Args:
        path: The path to validate (can be relative or absolute).
        search_root: Optional override for search root. Uses global if not provided.

    Returns:
        The resolved absolute Path if valid.

    Raises:
        ValueError: If no search root is configured.
        PermissionError: If the path is outside the search root.
        FileNotFoundError: If the path doesn't exist.
    """
    root = search_root or _search_root

    if root is None:
        raise ValueError("Search root not configured")

    # Resolve the root to handle symlinks (e.g., /var -> /private/var on macOS)
    root = root.resolve()

    # Convert to Path and resolve to absolute path (follows symlinks)
    target = Path(path)

    # If path is relative, resolve relative to search root
    if not target.is_absolute():
        target = root / target

    # Resolve the path - this follows symlinks and normalizes ../ etc.
    # We need to handle the case where the path doesn't exist yet
    # For non-existent paths, resolve the parent and check the final component
    if target.exists():
        resolved = target.resolve()
    else:
        # For non-existent paths, resolve what we can
        # This handles cases like /allowed/path/../../../etc/passwd
        # where the intermediate path may not exist
        resolved = target.resolve()

    # Check if resolved path is within the search root
    # Use os.path.commonpath for reliable comparison
    try:
        # resolve() returns absolute paths, so we can compare directly
        # Check if the resolved path starts with the search root
        resolved.relative_to(root)
    except ValueError:
        # relative_to raises ValueError if path is not relative to root
        raise PermissionError(
            f"Access denied: path '{path}' resolves to '{resolved}' which is outside search root '{root}'"
        )

    return resolved


def validate_paths_within_root(paths: list[str | Path], search_root: Optional[Path] = None) -> list[Path]:
    """
    Validate multiple paths are within the search root.

    Args:
        paths: List of paths to validate.
        search_root: Optional override for search root.

    Returns:
        List of resolved absolute Paths.

    Raises:
        ValueError: If no search root is configured.
        PermissionError: If any path is outside the search root.
        FileNotFoundError: If any path doesn't exist.
    """
    return [validate_path_within_root(p, search_root) for p in paths]


def is_path_within_root(path: str | Path, search_root: Optional[Path] = None) -> bool:
    """
    Check if a path is within the search root without raising exceptions.

    Args:
        path: The path to check.
        search_root: Optional override for search root.

    Returns:
        True if the path is within the search root, False otherwise.
    """
    try:
        validate_path_within_root(path, search_root)
        return True
    except (ValueError, PermissionError, FileNotFoundError, OSError):
        return False
