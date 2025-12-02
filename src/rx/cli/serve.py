"""Serve command for web API server"""

import os
import sys

import click

from rx.utils import get_int_env, get_str_env, setup_shutdown_filter


@click.command()
@click.option('--host', default='127.0.0.1', help='Host to bind to (default: 127.0.0.1)')
@click.option('--port', default=8000, help='Port to bind to (default: 8000)', type=int)
@click.option(
    '--search-root',
    default=None,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help='Root directory for all searches (default: current directory). All user paths must be within this directory.',
)
def serve_command(host, port, search_root):
    """
    Start the RX web API server.

    Launches a FastAPI-based REST API server with Prometheus metrics
    and full regex search capabilities.

    \b
    Examples:
      rx serve
      rx serve --port 8080
      rx serve --host 0.0.0.0 --port 8000

    \b
    Environment Variables:
      RX_LOG_LEVEL          Log level (DEBUG, INFO, WARNING, ERROR) [default: INFO]
      RX_WORKERS            Number of worker processes [default: 1]
      RX_LIMIT_CONCURRENCY  Max concurrent connections (None = unlimited) [default: None]
      RX_LIMIT_MAX_REQUESTS Max requests per worker before restart [default: None]
      RX_TIMEOUT_KEEP_ALIVE Keep-alive timeout in seconds [default: 5]
      RX_BACKLOG            Max queued connections [default: 2048]

    \b
    Worker Recommendations:
      - Single server: (2 × CPU cores) + 1
      - Kubernetes/containers: 1 worker per container, scale horizontally
      - Memory-intensive: Fewer workers to avoid OOM
      - I/O-bound: More workers (2-4 × CPU cores)

    \b
    API Documentation:
      Once started, visit:
      - http://localhost:PORT/docs     (Swagger UI)
      - http://localhost:PORT/redoc    (ReDoc)
      - http://localhost:PORT/metrics  (Prometheus metrics)

    \b
    Main Endpoints:
      GET /v1/trace       Search files for patterns
      GET /v1/samples     Get context around matches
      GET /v1/complexity  Analyze regex complexity
      GET /health         Health check
    """
    # Import uvicorn only when needed (not for CLI usage)
    try:
        import uvicorn
    except ImportError:
        click.echo("Error: uvicorn is not installed. Install with: pip install uvicorn", err=True)
        raise SystemExit(1)

    # Set up search root before importing web module
    from rx.path_security import set_search_root

    # Use provided search_root or default to current working directory
    resolved_root = set_search_root(search_root)

    # Set as environment variable so worker processes inherit it
    os.environ['RX_SEARCH_ROOT'] = str(resolved_root)

    # Import the FastAPI app (this triggers prometheus swap)
    from rx.web import app

    # Get configuration from environment variables
    log_level = get_str_env('RX_LOG_LEVEL', 'info').lower()
    workers = get_int_env('RX_WORKERS') or 1
    limit_concurrency = get_int_env('RX_LIMIT_CONCURRENCY') or None
    limit_max_requests = get_int_env('RX_LIMIT_MAX_REQUESTS') or None
    timeout_keep_alive = get_int_env('RX_TIMEOUT_KEEP_ALIVE') or 5
    backlog = get_int_env('RX_BACKLOG') or 2048

    # Check if running from a frozen binary (PyInstaller)
    is_frozen = getattr(sys, 'frozen', False)

    # Warn if using multiple workers with a frozen binary
    if is_frozen and workers > 1:
        click.echo("WARNING: Multiple workers detected in frozen binary mode", err=True)
        click.echo("  This may cause issues. Recommended: RX_WORKERS=1", err=True)
        click.echo("  For scaling, run multiple instances instead (e.g., Docker/Kubernetes)", err=True)
        click.echo("", err=True)

    click.echo(f"Starting RX API server on http://{host}:{port}")
    click.echo(f"Search root: {resolved_root}")
    click.echo(f"  All file searches are restricted to this directory.")
    click.echo(f"API docs available at http://{host}:{port}/docs")
    click.echo(f"Metrics available at http://{host}:{port}/metrics")
    click.echo(f"Workers: {workers}, Log level: {log_level.upper()}")
    if limit_concurrency:
        click.echo(f"Max concurrent connections: {limit_concurrency}")
    if limit_max_requests:
        click.echo(f"Max requests per worker: {limit_max_requests}")
    click.echo("")

    # Configure logging to suppress uvicorn shutdown tracebacks
    setup_shutdown_filter()

    try:
        uvicorn.run(
            "rx.web:app",
            host=host,
            port=port,
            workers=workers,
            log_level=log_level,
            limit_concurrency=limit_concurrency,
            limit_max_requests=limit_max_requests,
            timeout_keep_alive=timeout_keep_alive,
            backlog=backlog,
        )
    except KeyboardInterrupt:
        click.echo("\nShutting down server...")
        sys.exit(0)
