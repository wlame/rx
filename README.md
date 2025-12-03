# RX (Regex Tracer)

A high-performance tool for searching and analyzing large files, powered by ripgrep.

## Designed for large files.
RX is optimized for processing multi-GB files efficiently through parallel chunking and streaming.
If you need to process many files repeatedly, use the API server (`rx serve`) instead of running CLI commands in a loop. The server mode avoids Python startup overhead on each invocation.

## Key Features

- **Byte-Offset Based**: Returns precise byte offsets for efficient large file processing (line-based indexing available)
- **Parallel Processing**: Automatic chunking and parallel execution for large files
- **Samples output**: Can show arbitrary parts of text files with context when you found interested offsets
- **REST API Server**: All CLI features available via async HTTP API
- **File Analysis**: Extract metadata, statistics, and metrics from files
- **Regex Complexity Analysis**: Detect ReDoS vulnerabilities before production use
- **Security Sandbox**: Restrict file access to specific directories in server mode

## Prerequisites

**ripgrep must be installed:**

- **macOS**: `brew install ripgrep`
- **Ubuntu/Debian**: `apt install ripgrep`
- **Windows**: `choco install ripgrep`

## Quick Start

### Install & Run

```bash
# With uv (development)
uv sync
uv run rx /var/log/app.log "error.*"

# Or build standalone binary
./build.sh
./dist/rx /var/log/app.log "error.*"
```

### Basic Examples

```bash
# Search a file (returns byte offsets)
rx /var/log/app.log "error.*"

# Search a directory
rx /var/log/ "error.*"

# Show context lines
rx /var/log/app.log "error" --samples --context=3

# Analyze file metadata
rx analyse /var/log/app.log

# Check regex complexity
rx check "(a+)+"

# Start API server
rx serve --port=8000
```

## Why Byte Offsets?

RX returns **byte offsets** instead of line numbers for efficiency. Seeking to byte position is O(1), while counting lines is O(n). For large files, this matters significantly.

**Need line numbers?** Use the indexing feature:

```bash
# Create index for a large file
rx index /var/log/huge.log

# Now you can use line-based operations
rx samples /var/log/huge.log -l 1000,2000,3000 --context=5
```

The index enables fast line-to-offset conversion for files >50MB.

## Server Mode (Recommended for Repeated Operations)

The CLI spawns a Python interpreter on each invocation. For processing multiple files or repeated operations, use the API server:

```bash
# Start server
rx serve --port=8000

# Use HTTP API (same endpoints as CLI)
curl "http://localhost:8000/v1/trace?path=/var/log/app.log&regexp=error"
curl "http://localhost:8000/v1/analyse?path=/var/log/"
```

**Benefits:**
- No Python startup overhead per request
- Async processing with configurable workers
- Webhook support for event notifications
- Security sandbox with `--search-root`

### Security Sandbox

Restrict file access in server mode:

```bash
# Only allow access to /var/log
rx serve --search-root=/var/log

# Attempts to access other paths return 403 Forbidden
curl "http://localhost:8000/v1/trace?path=/etc/passwd&regexp=root"
# => 403 Forbidden
```

Prevents directory traversal (`../`) and symlink escape attacks.

## CLI Commands

### `rx` (search)
Search files for regex patterns.

```bash
rx /var/log/app.log "error.*"              # Basic search
rx /var/log/ "error.*"                     # Search directory
rx /var/log/app.log "error" --samples      # Show context lines
rx /var/log/app.log "error" -i             # Case-insensitive (ripgrep flags work)
rx /var/log/app.log "error" --json         # JSON output
```

### `rx analyse`
Extract file metadata and statistics.

```bash
rx analyse /var/log/app.log               # Single file
rx analyse /var/log/                      # Directory
rx analyse /var/log/ --max-workers=20     # Parallel processing
```

### `rx check`
Analyze regex complexity and detect ReDoS vulnerabilities.

```bash
rx check "(a+)+"                          # Returns risk level and fixes
```

### `rx index`
Create line-offset index for large files.

```bash
rx index /var/log/huge.log                # Create index
rx index /var/log/huge.log --info         # Show index info
```

### `rx samples`
Extract context lines around byte offsets or line numbers.

```bash
rx samples /var/log/app.log -b 12345,67890 --context=3   # Byte offsets
rx samples /var/log/app.log -l 100,200 --context=5       # Line numbers (requires index)
```

### `rx serve`
Start REST API server.

```bash
rx serve                                  # Start on localhost:8000
rx serve --host=0.0.0.0 --port=8080       # Custom host/port
rx serve --search-root=/var/log           # Restrict to directory
```

## API Endpoints

Once the server is running, visit http://localhost:8000/docs for interactive API documentation.

**Main Endpoints:**
- `GET /v1/trace` - Search files for patterns
- `GET /v1/analyse` - File metadata and statistics
- `GET /v1/complexity` - Regex complexity analysis
- `GET /v1/samples` - Extract context lines
- `GET /health` - Server health and configuration

**Example:**

```bash
# Search
curl "http://localhost:8000/v1/trace?path=/var/log/app.log&regexp=error&max_results=10"

# Analyse
curl "http://localhost:8000/v1/analyse?path=/var/log/"

# With webhooks
curl "http://localhost:8000/v1/trace?path=/var/log/app.log&regexp=error&hook_on_complete=https://example.com/webhook"
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RX_WORKERS` | Worker processes for server | `1` |
| `RX_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `RX_MAX_SUBPROCESSES` | Max parallel workers for file processing | `20` |
| `RX_MIN_CHUNK_SIZE_MB` | Min chunk size for splitting files | `20` |

### Server Configuration

```bash
# Production example (8-core, 16GB RAM)
RX_WORKERS=17 \
RX_LIMIT_CONCURRENCY=500 \
RX_LIMIT_MAX_REQUESTS=10000 \
rx serve --host=0.0.0.0 --port=8000 --search-root=/data

# Container/Kubernetes (1 worker per pod, scale with replicas)
RX_WORKERS=1 rx serve --host=0.0.0.0 --port=8000
```

## Roadmap

- **Gzip support**: Process `.gz` files without manual decompression (planned)
- **Additional formats**: Support for more compressed formats
- **Streaming API**: WebSocket endpoint for real-time results

## Development

```bash
# Run tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=rx --cov-report=html

# Build binary
uv sync --group build
./build.sh
```

## License

MIT
