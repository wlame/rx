"""Path security validation for sandboxed file access.

This module provides security validation to ensure all file access stays within
configured search root directories, preventing directory traversal attacks and
symlink escapes.

Security Features:
- Resolves symlinks to prevent escape via symbolic links
- Normalizes paths to prevent ../ traversal attacks
- Validates both files and directories
- Thread-safe for use in async/threaded contexts
- Supports multiple search roots for flexible configuration
"""

import os
from pathlib import Path
from typing import Optional

# Global search roots - set during server startup
_search_roots: list[Path] = []


def set_search_root(path: Optional[str | Path]) -> Path:
    """
    Set a single global search root directory (replaces any existing roots).

    This is a convenience function for single-root configurations.
    For multiple roots, use set_search_roots() instead.

    Args:
        path: The root directory path. If None, uses current working directory.

    Returns:
        The resolved absolute path of the search root.

    Raises:
        ValueError: If the path doesn't exist or is not a directory.
    """
    if path is None:
        resolved = Path.cwd().resolve()
    else:
        resolved = Path(path).resolve()

    if not resolved.exists():
        raise ValueError(f"Search root does not exist: {resolved}")

    if not resolved.is_dir():
        raise ValueError(f"Search root is not a directory: {resolved}")

    global _search_roots
    _search_roots = [resolved]
    return resolved


def set_search_roots(paths: list[str | Path]) -> list[Path]:
    """
    Set multiple global search root directories.

    Args:
        paths: List of root directory paths. If empty, uses current working directory.

    Returns:
        List of resolved absolute paths of the search roots.

    Raises:
        ValueError: If any path doesn't exist or is not a directory.
    """
    global _search_roots

    if not paths:
        resolved = Path.cwd().resolve()
        _search_roots = [resolved]
        return [resolved]

    resolved_roots = []
    for path in paths:
        resolved = Path(path).resolve()

        if not resolved.exists():
            raise ValueError(f"Search root does not exist: {resolved}")

        if not resolved.is_dir():
            raise ValueError(f"Search root is not a directory: {resolved}")

        # Avoid duplicates
        if resolved not in resolved_roots:
            resolved_roots.append(resolved)

    _search_roots = resolved_roots
    return resolved_roots


def get_search_root() -> Optional[Path]:
    """
    Get the first search root directory.

    Returns:
        The first search root Path, or None if not set.
    """
    return _search_roots[0] if _search_roots else None


def get_search_roots() -> list[Path]:
    """
    Get all configured search root directories.

    Returns:
        List of search root Paths (empty list if not configured).
    """
    return _search_roots.copy()


def validate_path_within_root(path: str | Path, search_root: Optional[Path] = None) -> Path:
    """
    Validate that a path is within one of the search root directories.

    This function:
    1. Resolves the path to an absolute path (following symlinks)
    2. Checks if the resolved path is within any of the search roots
    3. Returns the resolved path if valid

    Args:
        path: The path to validate (can be relative or absolute).
        search_root: Optional single root override. Uses global roots if not provided.

    Returns:
        The resolved absolute Path if valid.

    Raises:
        ValueError: If no search root is configured.
        PermissionError: If the path is outside all search roots.
    """
    # Determine which roots to check
    if search_root is not None:
        roots = [search_root.resolve()]
    elif _search_roots:
        roots = _search_roots
    else:
        raise ValueError("Search root not configured")

    # Convert to Path
    target = Path(path)

    # Try to validate against each root
    resolved_path = None
    last_error = None

    for root in roots:
        root = root.resolve()

        # If path is relative, resolve relative to this root
        if not target.is_absolute():
            check_path = root / target
        else:
            check_path = target

        # Resolve the path - this follows symlinks and normalizes ../ etc.
        resolved = check_path.resolve()

        # Check if resolved path is within this search root
        try:
            resolved.relative_to(root)
            # Path is valid for this root
            resolved_path = resolved
            break
        except ValueError:
            # Path is not relative to this root, try next
            last_error = PermissionError(
                f"Access denied: path '{path}' resolves to '{resolved}' which is outside search roots"
            )
            continue

    if resolved_path is None:
        # Path wasn't valid for any root
        roots_str = ", ".join(f"'{r}'" for r in roots)
        raise PermissionError(f"Access denied: path '{path}' is outside all search roots: {roots_str}")

    return resolved_path


def validate_path_within_roots(path: str | Path, search_roots: Optional[list[Path]] = None) -> Path:
    """
    Validate that a path is within one of the specified search root directories.

    Args:
        path: The path to validate (can be relative or absolute).
        search_roots: Optional list of root overrides. Uses global roots if not provided.

    Returns:
        The resolved absolute Path if valid.

    Raises:
        ValueError: If no search roots are configured.
        PermissionError: If the path is outside all search roots.
    """
    # Determine which roots to check
    if search_roots is not None:
        roots = [r.resolve() for r in search_roots]
    elif _search_roots:
        roots = _search_roots
    else:
        raise ValueError("Search roots not configured")

    if not roots:
        raise ValueError("Search roots not configured")

    # Convert to Path
    target = Path(path)

    # Try to validate against each root
    resolved_path = None

    for root in roots:
        # If path is relative, resolve relative to this root
        if not target.is_absolute():
            check_path = root / target
        else:
            check_path = target

        # Resolve the path - this follows symlinks and normalizes ../ etc.
        resolved = check_path.resolve()

        # Check if resolved path is within this search root
        try:
            resolved.relative_to(root)
            # Path is valid for this root
            resolved_path = resolved
            break
        except ValueError:
            # Path is not relative to this root, try next
            continue

    if resolved_path is None:
        # Path wasn't valid for any root
        roots_str = ", ".join(f"'{r}'" for r in roots)
        raise PermissionError(f"Access denied: path '{path}' is outside all search roots: {roots_str}")

    return resolved_path


def validate_paths_within_root(paths: list[str | Path], search_root: Optional[Path] = None) -> list[Path]:
    """
    Validate multiple paths are within the search root(s).

    Args:
        paths: List of paths to validate.
        search_root: Optional single root override.

    Returns:
        List of resolved absolute Paths.

    Raises:
        ValueError: If no search root is configured.
        PermissionError: If any path is outside the search root(s).
    """
    return [validate_path_within_root(p, search_root) for p in paths]


def validate_paths_within_roots(paths: list[str | Path], search_roots: Optional[list[Path]] = None) -> list[Path]:
    """
    Validate multiple paths are within any of the search roots.

    Args:
        paths: List of paths to validate.
        search_roots: Optional list of root overrides.

    Returns:
        List of resolved absolute Paths.

    Raises:
        ValueError: If no search roots are configured.
        PermissionError: If any path is outside all search roots.
    """
    return [validate_path_within_roots(p, search_roots) for p in paths]


def is_path_within_root(path: str | Path, search_root: Optional[Path] = None) -> bool:
    """
    Check if a path is within the search root(s) without raising exceptions.

    Args:
        path: The path to check.
        search_root: Optional single root override.

    Returns:
        True if the path is within any search root, False otherwise.
    """
    try:
        validate_path_within_root(path, search_root)
        return True
    except (ValueError, PermissionError, FileNotFoundError, OSError):
        return False


def is_path_within_roots(path: str | Path, search_roots: Optional[list[Path]] = None) -> bool:
    """
    Check if a path is within any of the search roots without raising exceptions.

    Args:
        path: The path to check.
        search_roots: Optional list of root overrides.

    Returns:
        True if the path is within any search root, False otherwise.
    """
    try:
        validate_path_within_roots(path, search_roots)
        return True
    except (ValueError, PermissionError, FileNotFoundError, OSError):
        return False
