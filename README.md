# RX (Regex Tracer)

A high-performance file search and analysis tool powered by ripgrep.

## Features

- **Fast Pattern Matching**: Search files using powerful regex patterns with parallel streaming processing
- **Directory Support**: Search all text files in a directory automatically (skips binary files)
- **File Analysis**: Extract metadata, statistics, and metrics from files with pluggable hook system
- **Context Extraction**: Get surrounding lines for matched patterns with colored output
- **Complexity Analysis**: Analyze regex patterns for performance characteristics and ReDoS risks
- **Byte Offset Results**: Get precise byte offsets for all matches with filepath:offset format
- **CLI & API**: Use as command-line tool or REST API server
- **Streaming Architecture**: Worker pool processes chunks in parallel with no batching delays
- **Version Management**: Semantic versioning with `--version` flag

## Prerequisites

**ripgrep must be installed on your system:**

- **macOS**: `brew install ripgrep`
- **Ubuntu/Debian**: `apt install ripgrep`
- **Windows**: `choco install ripgrep` or download from [releases](https://github.com/BurntSushi/ripgrep/releases)

## Installation & Usage

### Option 1: Run with uv (Development)

```bash
# Install dependencies
uv sync

# Run CLI search mode
uv run rx /path/to/file.log "error.*" --samples

# Analyze files
uv run rx analyse /path/to/file.log

# Run complexity check
uv run rx check "(a+)+"

# Run API server
uv run rx serve --port 8000

# Check version
uv run rx --version
```

### Option 2: Build Standalone Binary

```bash
# Build the binary
./build.sh

# Use the binary
./dist/rx /path/to/file.log "error.*"     # Search
./dist/rx analyse /path/to/file.log       # File analysis
./dist/rx check "(a+)+"                    # Complexity analysis
./dist/rx serve --port 8000                # API server
./dist/rx --version                        # Check version
```

### Option 3: Install as Python Package
TBD

## CLI Usage

RX has four modes:

### 1. Search Mode (Default)

```bash
# Basic search
rx /var/log/app.log "error.*"
rx /var/log/ "error.*"                     # Search directory
```

### 2. Analyse Mode (File Analysis)

```bash
# Analyze files for metadata and statistics
rx analyse /var/log/app.log
rx analyse /var/log/                       # Analyze directory
rx analyse /var/log/app.log --json         # JSON output
rx analyse /var/log/ --no-color            # Disable colors
rx analyse /var/log/ --max-workers=20      # Parallel processing
```

### 3. Check Mode (Regex Complexity Analysis)

```bash
# Analyze regex complexity
rx check "(a+)+"
rx check "error.*" --json
rx check "^[a-z]+$" --no-color
```

### 4. Server Mode (Web API)

```bash
# Start API server
rx serve                           # localhost:8000
rx serve --host 0.0.0.0 --port 8080

# Configure via environment variables
RX_WORKERS=4 rx serve --port 8000
RX_LOG_LEVEL=DEBUG RX_WORKERS=8 rx serve
```

#### Server Configuration (Environment Variables)

| Variable | Description | Default | Recommendation |
|----------|-------------|---------|----------------|
| `RX_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` | `INFO` for production, `DEBUG` for troubleshooting |
| `RX_WORKERS` | Number of worker processes | `1` | `(2 × CPU cores) + 1` for single server<br>`1` for Kubernetes/containers |
| `RX_LIMIT_CONCURRENCY` | Max concurrent connections | `None` | Set based on memory: `100-500` for 2GB RAM<br>`None` (unlimited) if sufficient memory |
| `RX_LIMIT_MAX_REQUESTS` | Max requests per worker before restart | `None` | `10000-50000` to prevent memory leaks<br>`None` if memory is stable |
| `RX_TIMEOUT_KEEP_ALIVE` | Keep-alive timeout (seconds) | `5` | `5` for most cases<br>`15-30` for slow clients |
| `RX_BACKLOG` | Max queued connections | `2048` | `2048` (default is fine)<br>Increase for high-traffic |

**Worker Recommendations:**

- **Development (Python source)**: `(2 × CPU cores) + 1` workers
  - 4-core machine: 9 workers
  - 8-core machine: 17 workers
  - 16-core machine: 33 workers

- **Binary deployments**: **Always use `RX_WORKERS=1`**, run multiple instances for scaling
  - Use Docker/systemd/supervisor to run multiple processes
  - Example: Run 4 instances on ports 8000-8003, use nginx/haproxy for load balancing

- **Kubernetes/Container deployment**: **1 worker per container**, scale horizontally with pods

- **Memory-intensive workloads**: Fewer workers to avoid OOM

- **I/O-bound workloads**: More workers, 2-4 × CPU cores (Python source only)

**Example Production Configuration:**

```bash
# High-traffic single server (8-core, 16GB RAM)
RX_WORKERS=17 \
RX_LIMIT_CONCURRENCY=500 \
RX_LIMIT_MAX_REQUESTS=10000 \
RX_TIMEOUT_KEEP_ALIVE=5 \
rx serve --host 0.0.0.0 --port 8000

# Kubernetes deployment (1 worker per pod, scale with replicas)
RX_WORKERS=1 \
RX_LOG_LEVEL=INFO \
rx serve --host 0.0.0.0 --port 8000
```

### Search Mode

```bash
# Basic search - single file (shows byte offsets)
rx /var/log/app.log "error.*"

# Search entire directory (all text files)
rx /var/log/ "error.*"

# Show context lines with colored matches (single file only)
rx /var/log/app.log "error" --samples

# Customize context
rx /var/log/app.log "error" --samples --context=5
rx /var/log/app.log "error" --samples --before=2 --after=10

# Limit results
rx /var/log/app.log "error" --max-results=100
rx /var/log/ "error" --max-results=100  # Works with directories too

# JSON output (for piping to jq)
rx /var/log/ "error" --json | jq '.matches'
rx /var/log/ "error" --json | jq '.scanned_files'

# Disable colors
rx /var/log/app.log "error" --samples --no-color

# Use named parameters
rx --path=/var/log/ --regex="error.*"

# Ripgrep passthrough - any unrecognized flags are passed to ripgrep
rx /var/log/app.log "error" -i              # Case-insensitive search
rx /var/log/app.log "error" --case-sensitive # Case-sensitive search
rx /var/log/app.log "error" -w              # Match whole words only
rx /var/log/app.log "pattern" -A 3          # Show 3 lines after match (ripgrep's -A)
rx /var/log/app.log "pattern" -B 2          # Show 2 lines before match (ripgrep's -B)
rx /var/log/app.log "pattern" -C 2          # Show 2 lines context (ripgrep's -C)
```

### Analyse Mode Examples

```bash
# Basic file analysis
rx analyse /var/log/app.log

# Example output:
# Analysis Results for: /var/log/app.log
# Time: 0.012s
#
# File: f1 (/var/log/app.log)
#   Size: 1.50 MB (1572864 bytes)
#   Type: text
#   Created: 2025-10-18T00:00:00
#   Modified: 2025-10-18T01:00:00
#   Permissions: 644
#   Owner: user
#   Lines: 5000 (150 empty)
#   Line length: max=200, avg=80.5, median=75.0, stddev=25.3

# Analyze entire directory
rx analyse /var/log/

# JSON output for programmatic use
rx analyse /var/log/app.log --json | jq '.results[0].line_count'

# Analyze multiple paths
rx analyse /var/log/app.log /var/log/error.log

# Parallel processing with custom workers
rx analyse /var/log/ --max-workers=20

# Without colors (for piping)
rx analyse /var/log/app.log --no-color
```

### Ripgrep Compatibility

RX passes any unrecognized options directly to ripgrep, making it compatible with most ripgrep flags:

- **Case sensitivity**: `-i` (ignore case), `--case-sensitive`, `-s` (smart case)
- **Word boundaries**: `-w` (match whole words)
- **Context lines**: `-A N` (after), `-B N` (before), `-C N` (context) - Note: use `--samples` for rx's own context feature
- **File encoding**: `--encoding=ENCODING`
- **And many more**: See `rg --help` for all available options

**Note**: Some ripgrep options that conflict with rx's internal usage may not work as expected. RX always uses `--byte-offset`, `--no-heading`, `--only-matching`, and `--color=never` internally.

```

## API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Search & Analysis

- **GET /v1/trace** - Search for regex patterns in files or directories
  - Parameters: `path` (file or directory), `regex`, `max_results` (optional)
  - Returns: Matches with filepath:offset, scanned_files, skipped_files

- **GET /v1/analyse** - Analyze files for metadata and statistics
  - Parameters: `path` (file or directory), `max_workers` (optional, default: 10)
  - Returns: File analysis results with size, metadata, line statistics, scanned_files, skipped_files

- **GET /v1/complexity** - Analyze regex complexity
  - Parameters: `regex`
  - Returns: Complexity score, level, risk assessment, and warnings

- **GET /v1/samples** - Get context lines around byte offsets
  - Parameters: `path`, `offsets`, `context`/`before_context`/`after_context`
  - Returns: Lines of text around each offset

### General

- **GET /health** - Health check
- **GET /** - Welcome message

## Examples

### Search for patterns

```bash
# Single file
curl "http://localhost:8000/v1/trace?path=/var/log/app.log&regex=error.*failed&max_results=10"

# Directory (all text files)
curl "http://localhost:8000/v1/trace?path=/var/log/&regex=error.*"
```

### Analyze files

```bash
# Single file
curl "http://localhost:8000/v1/analyse?path=/var/log/app.log"

# Directory (all text files)
curl "http://localhost:8000/v1/analyse?path=/var/log/&max_workers=20"

# Example response
{
  "path": "/var/log/app.log",
  "time": 0.123,
  "files": {
    "f1": "/var/log/app.log"
  },
  "results": [
    {
      "file": "f1",
      "size_bytes": 1048576,
      "size_human": "1.00 MB",
      "is_text": true,
      "created_at": "2025-10-18T00:00:00",
      "modified_at": "2025-10-18T01:00:00",
      "permissions": "644",
      "owner": "user",
      "line_count": 5000,
      "empty_line_count": 150,
      "max_line_length": 200,
      "avg_line_length": 80.5,
      "median_line_length": 75.0,
      "line_length_stddev": 25.3
    }
  ],
  "scanned_files": ["/var/log/app.log"],
  "skipped_files": []
}
```

### Analyze regex complexity

```bash
curl "http://localhost:8000/v1/complexity?regex=(a%2B)%2B"
```

### Get context around matches

```bash
curl "http://localhost:8000/v1/samples?path=/var/log/app.log&offsets=123,456&context=3"
```

## Performance

### Pattern Search
- **Streaming Worker Pool**: Uses `ThreadPoolExecutor` with configurable worker count (default: 20)
- **Intelligent Chunking**: Splits large files (>20MB) into parallel chunks with line-aligned boundaries
- **No Batching Delays**: All tasks submitted to pool immediately, results stream as available
- **Early Termination**: `max_results` parameter cancels remaining tasks when limit reached
- **Scalable**: Handles files of any size efficiently (tested with multi-GB files)
- **Environment Variables**:
  - `RX_MAX_SUBPROCESSES`: Max parallel workers (default: 20)
  - `RX_MIN_CHUNK_SIZE_MB`: Minimum chunk size in bytes (default: 20MB)

### File Analysis
- **Parallel Processing**: Analyzes multiple files concurrently using `ThreadPoolExecutor`
- **Configurable Workers**: `--max-workers` parameter (default: 10) for optimal throughput
- **Pluggable Architecture**: Hook-based system for custom metrics and analysis
- **Efficient Statistics**: Uses Python `statistics` module for accurate line length metrics
- **Binary Detection**: Automatically skips binary files from text analysis
- **Metadata Extraction**: Fast file metadata retrieval (size, timestamps, permissions, owner)

## Use Cases

1. **Log Analysis**: Search multi-GB log files or entire log directories for error patterns
2. **Code Search**: Find patterns across large codebases and directories
3. **File Analysis**: Extract metadata and statistics from files for auditing or reporting
4. **Security Auditing**: Detect sensitive data patterns in files or scan entire directories
5. **Regex Testing**: Analyze regex complexity before production use
6. **Multi-File Search**: Process hundreds of files in parallel using streaming architecture
7. **Code Metrics**: Analyze code files for line counts, length statistics, and complexity

## Development

### Run Tests

```bash
uv run pytest -v
```

### Run with Coverage

```bash
uv run pytest --cov=rx --cov-report=html
```

### Build Binary

```bash
# Install build dependencies
uv sync --group build

# Build
./build.sh
```

## Binary Distribution

The standalone binary includes all Python dependencies but requires:

- **ripgrep** installed on the target system
- Compatible architecture (binary is platform-specific)

Build on the target platform for best compatibility.

## License

MIT
