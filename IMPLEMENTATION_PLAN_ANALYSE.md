# Implementation Plan: Enhanced Analyse with Compressed File Support

## Overview

This plan describes the remaining work to complete the enhanced `analyse` feature with:
- Compressed file analysis (decompress to /tmp, analyze, cleanup)
- Analysis result caching via `analyse_cache`
- Index information for both regular and seekable zstd files
- Enhanced model fields for compression and index metadata

## Current State (Completed)

### ✅ Done:
1. **analyse_cache module** (`src/rx/analyse_cache.py`)
   - Cache management functions: save, load, delete, clear
   - Cache validation based on file size + mtime
   - Storage: `~/.cache/rx/analyse_cache/`
   - Tests: `tests/test_analyse_cache.py` (19 tests, all passing)

2. **Enhanced FileAnalysisResult model** (`src/rx/models.py`)
   - Added fields: `is_compressed`, `compression_format`, `is_seekable_zstd`
   - Added fields: `compressed_size`, `decompressed_size`, `compression_ratio`
   - Added fields: `has_index`, `index_path`, `index_valid`, `index_checkpoint_count`
   - Updated `to_cli()` to display compression and index info

3. **Background task infrastructure** (`src/rx/task_manager.py`, `src/rx/web.py`)
   - POST /v1/compress endpoint
   - POST /v1/index endpoint
   - GET /v1/tasks/{task_id} endpoint
   - Tests: `tests/test_compress_index_endpoints.py` (skipped, requires server)

## Remaining Work

### 1. Update FileAnalysisState (src/rx/analyse.py)

Add compression and index fields to the internal dataclass:

```python
@dataclass
class FileAnalysisState:
    # ... existing fields ...
    
    # Compression information
    is_compressed: bool = False
    compression_format: str | None = None
    is_seekable_zstd: bool = False
    compressed_size: int | None = None
    decompressed_size: int | None = None
    compression_ratio: float | None = None
    
    # Index information
    has_index: bool = False
    index_path: str | None = None
    index_valid: bool = False
    index_checkpoint_count: int | None = None
```

### 2. Update FileAnalyzer.analyze_file() - Add Cache Integration

**Location**: `src/rx/analyse.py`, method `FileAnalyzer.analyze_file()`

**Changes**:

```python
def analyze_file(self, filepath: str, file_id: str) -> FileAnalysisState:
    """Analyze a single file with all registered hooks."""
    
    # STEP 1: Try analyse_cache first (NEW)
    from rx.analyse_cache import load_cache, save_cache
    
    cached = load_cache(filepath)
    if cached:
        logger.info(f"Loaded from analyse_cache: {filepath}")
        # Convert dict back to FileAnalysisState
        result = self._dict_to_state(cached, file_id, filepath)
        # Still run hooks
        try:
            self.file_hook(filepath, result)
        except Exception as e:
            logger.warning(f"File hook failed: {e}")
        try:
            self.post_hook(result)
        except Exception as e:
            logger.warning(f"Post hook failed: {e}")
        return result
    
    # STEP 2: Try old index cache (keep existing logic)
    cached_result = self._try_load_from_cache(filepath, file_id)
    if cached_result is not None:
        # ... existing hook logic ...
        return cached_result
    
    # STEP 3: Fresh analysis
    try:
        stat_info = os.stat(filepath)
        size_bytes = stat_info.st_size
        
        # Initialize result
        result = FileAnalysisState(
            file_id=file_id,
            filepath=filepath,
            size_bytes=size_bytes,
            size_human=human_readable_size(size_bytes),
            is_text=is_text_file(filepath),
        )
        
        # Add metadata
        result.created_at = datetime.fromtimestamp(stat_info.st_ctime).isoformat()
        result.modified_at = datetime.fromtimestamp(stat_info.st_mtime).isoformat()
        result.permissions = oct(stat_info.st_mode)[-3:]
        try:
            import pwd
            result.owner = pwd.getpwuid(stat_info.st_uid).pw_name
        except (ImportError, KeyError):
            result.owner = str(stat_info.st_uid)
        
        # STEP 4: Detect compression (NEW)
        from rx.compression import detect_compression, is_compressed
        from rx.seekable_zstd import is_seekable_zstd
        
        if is_compressed(filepath):
            result.is_compressed = True
            comp_format = detect_compression(filepath)
            result.compression_format = comp_format.value if comp_format else None
            result.compressed_size = size_bytes
            
            if is_seekable_zstd(filepath):
                result.is_seekable_zstd = True
                # Get seekable zstd info
                from rx.seekable_zstd import get_seekable_zstd_info
                try:
                    info = get_seekable_zstd_info(filepath)
                    result.decompressed_size = info.decompressed_size
                    result.compression_ratio = info.compression_ratio
                except Exception as e:
                    logger.warning(f"Failed to get seekable zstd info: {e}")
        
        # STEP 5: Run hooks
        try:
            self.file_hook(filepath, result)
        except Exception as e:
            logger.warning(f"File hook failed: {e}")
        
        # STEP 6: Analyze content
        if result.is_text:
            self._analyze_text_file(filepath, result)
        elif result.is_compressed:
            # NEW: Handle compressed files
            self._analyze_compressed_file(filepath, result)
        
        # STEP 7: Add index information (NEW)
        self._add_index_info(filepath, result)
        
        # STEP 8: Run post hooks
        try:
            self.post_hook(result)
        except Exception as e:
            logger.warning(f"Post hook failed: {e}")
        
        # STEP 9: Save to analyse_cache (NEW)
        try:
            result_dict = self._state_to_dict(result)
            save_cache(filepath, result_dict)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to analyze {filepath}: {e}")
        # Return minimal result
        return FileAnalysisState(
            file_id=file_id,
            filepath=filepath,
            size_bytes=0,
            size_human="0 B",
            is_text=False,
        )
```

### 3. Add Helper Methods

**3.1 _dict_to_state() - Convert cache dict to FileAnalysisState**

```python
def _dict_to_state(self, data: dict, file_id: str, filepath: str) -> FileAnalysisState:
    """Convert cached dict to FileAnalysisState."""
    return FileAnalysisState(
        file_id=file_id,
        filepath=filepath,
        size_bytes=data.get('size_bytes', 0),
        size_human=data.get('size_human', '0 B'),
        is_text=data.get('is_text', False),
        created_at=data.get('created_at'),
        modified_at=data.get('modified_at'),
        permissions=data.get('permissions'),
        owner=data.get('owner'),
        line_count=data.get('line_count'),
        empty_line_count=data.get('empty_line_count'),
        line_length_max=data.get('line_length_max'),
        line_length_avg=data.get('line_length_avg'),
        line_length_median=data.get('line_length_median'),
        line_length_p95=data.get('line_length_p95'),
        line_length_p99=data.get('line_length_p99'),
        line_length_stddev=data.get('line_length_stddev'),
        line_length_max_line_number=data.get('line_length_max_line_number'),
        line_length_max_byte_offset=data.get('line_length_max_byte_offset'),
        line_ending=data.get('line_ending'),
        custom_metrics=data.get('custom_metrics', {}),
        # Compression fields
        is_compressed=data.get('is_compressed', False),
        compression_format=data.get('compression_format'),
        is_seekable_zstd=data.get('is_seekable_zstd', False),
        compressed_size=data.get('compressed_size'),
        decompressed_size=data.get('decompressed_size'),
        compression_ratio=data.get('compression_ratio'),
        # Index fields
        has_index=data.get('has_index', False),
        index_path=data.get('index_path'),
        index_valid=data.get('index_valid', False),
        index_checkpoint_count=data.get('index_checkpoint_count'),
    )
```

**3.2 _state_to_dict() - Convert FileAnalysisState to dict**

```python
def _state_to_dict(self, result: FileAnalysisState) -> dict:
    """Convert FileAnalysisState to dict for caching."""
    return {
        'file': result.file_id,
        'size_bytes': result.size_bytes,
        'size_human': result.size_human,
        'is_text': result.is_text,
        'created_at': result.created_at,
        'modified_at': result.modified_at,
        'permissions': result.permissions,
        'owner': result.owner,
        'line_count': result.line_count,
        'empty_line_count': result.empty_line_count,
        'line_length_max': result.line_length_max,
        'line_length_avg': result.line_length_avg,
        'line_length_median': result.line_length_median,
        'line_length_p95': result.line_length_p95,
        'line_length_p99': result.line_length_p99,
        'line_length_stddev': result.line_length_stddev,
        'line_length_max_line_number': result.line_length_max_line_number,
        'line_length_max_byte_offset': result.line_length_max_byte_offset,
        'line_ending': result.line_ending,
        'custom_metrics': result.custom_metrics,
        # Compression fields
        'is_compressed': result.is_compressed,
        'compression_format': result.compression_format,
        'is_seekable_zstd': result.is_seekable_zstd,
        'compressed_size': result.compressed_size,
        'decompressed_size': result.decompressed_size,
        'compression_ratio': result.compression_ratio,
        # Index fields
        'has_index': result.has_index,
        'index_path': result.index_path,
        'index_valid': result.index_valid,
        'index_checkpoint_count': result.index_checkpoint_count,
    }
```

**3.3 _add_index_info() - Add index metadata**

```python
def _add_index_info(self, filepath: str, result: FileAnalysisState):
    """Add index information to analysis result."""
    from rx.index import get_index_path, is_index_valid, load_index
    from rx.seekable_zstd import is_seekable_zstd
    from rx.seekable_index import get_index_path as get_seekable_index_path
    from rx.seekable_index import is_index_valid as is_seekable_index_valid
    from rx.seekable_index import get_or_build_index
    
    try:
        if is_seekable_zstd(filepath):
            # Check for seekable zstd index
            index_path = get_seekable_index_path(filepath)
            if os.path.exists(index_path):
                result.has_index = True
                result.index_path = index_path
                result.index_valid = is_seekable_index_valid(filepath)
                
                if result.index_valid:
                    try:
                        index = get_or_build_index(filepath)
                        result.index_checkpoint_count = len(index.frames)
                    except Exception as e:
                        logger.warning(f"Failed to load seekable index: {e}")
        else:
            # Check for regular file index
            index_path = get_index_path(filepath)
            if os.path.exists(index_path):
                result.has_index = True
                result.index_path = index_path
                result.index_valid = is_index_valid(filepath)
                
                if result.index_valid:
                    try:
                        index_data = load_index(index_path)
                        result.index_checkpoint_count = len(index_data.get('checkpoints', []))
                    except Exception as e:
                        logger.warning(f"Failed to load index: {e}")
    except Exception as e:
        logger.warning(f"Failed to add index info: {e}")
```

**3.4 _analyze_compressed_file() - Handle compressed files**

```python
def _analyze_compressed_file(self, filepath: str, result: FileAnalysisState):
    """Analyze compressed file by decompressing to /tmp and analyzing."""
    import tempfile
    import shutil
    from rx.compression import decompress_to_file
    
    temp_file = None
    try:
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tf:
            temp_file = tf.name
        
        logger.info(f"Decompressing {filepath} to {temp_file}")
        
        # Decompress to temp file
        try:
            decompress_to_file(filepath, temp_file)
        except OSError as e:
            if "No space left" in str(e) or "Disk quota exceeded" in str(e):
                logger.warning(f"No space left on device, skipping decompression of {filepath}")
                return
            raise
        
        # Get decompressed size
        stat = os.stat(temp_file)
        result.decompressed_size = stat.st_size
        
        # Calculate compression ratio
        if result.compressed_size and result.decompressed_size:
            result.compression_ratio = result.decompressed_size / result.compressed_size
        
        # Check if decompressed file is text
        if is_text_file(temp_file):
            result.is_text = True
            # Analyze the decompressed content
            self._analyze_text_file(temp_file, result)
        else:
            logger.info(f"Decompressed file is not text: {filepath}")
            
    except Exception as e:
        logger.error(f"Failed to analyze compressed file {filepath}: {e}")
    finally:
        # IMPORTANT: Clean up temp file
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                logger.debug(f"Cleaned up temp file: {temp_file}")
            except OSError as e:
                logger.warning(f"Failed to remove temp file {temp_file}: {e}")
```

### 4. Update analyse_path_results() - Map to FileAnalysisResult

**Location**: `src/rx/analyse.py`, function `analyse_path_results()`

**Changes**: Add new fields when converting FileAnalysisState → FileAnalysisResult

```python
from rx.models import FileAnalysisResult

# Inside the loop where FileAnalysisResult is created:
file_result = FileAnalysisResult(
    file=state.file_id,
    size_bytes=state.size_bytes,
    size_human=state.size_human,
    is_text=state.is_text,
    created_at=state.created_at,
    modified_at=state.modified_at,
    permissions=state.permissions,
    owner=state.owner,
    line_count=state.line_count,
    empty_line_count=state.empty_line_count,
    line_length_max=state.line_length_max,
    line_length_avg=state.line_length_avg,
    line_length_median=state.line_length_median,
    line_length_p95=state.line_length_p95,
    line_length_p99=state.line_length_p99,
    line_length_stddev=state.line_length_stddev,
    line_length_max_line_number=state.line_length_max_line_number,
    line_length_max_byte_offset=state.line_length_max_byte_offset,
    line_ending=state.line_ending,
    custom_metrics=state.custom_metrics,
    # NEW: Compression fields
    is_compressed=state.is_compressed,
    compression_format=state.compression_format,
    is_seekable_zstd=state.is_seekable_zstd,
    compressed_size=state.compressed_size,
    decompressed_size=state.decompressed_size,
    compression_ratio=state.compression_ratio,
    # NEW: Index fields
    has_index=state.has_index,
    index_path=state.index_path,
    index_valid=state.index_valid,
    index_checkpoint_count=state.index_checkpoint_count,
)
```

### 5. Add decompress_to_file() to compression.py

**Location**: `src/rx/compression.py`

**New function**:

```python
def decompress_to_file(input_path: str, output_path: str) -> None:
    """Decompress a file to the output path.
    
    Args:
        input_path: Path to compressed file
        output_path: Path where decompressed file should be written
        
    Raises:
        ValueError: If file is not compressed or format unsupported
        OSError: If decompression fails (e.g., no space left)
    """
    compression_format = detect_compression(input_path)
    
    if compression_format == CompressionFormat.NONE:
        raise ValueError(f"File is not compressed: {input_path}")
    
    decompressor_cmd = get_decompressor_command(compression_format, input_path)
    
    if not decompressor_cmd:
        raise ValueError(f"No decompressor available for {compression_format.value}")
    
    # Run decompression to file
    import subprocess
    
    with open(output_path, 'wb') as outfile:
        result = subprocess.run(
            decompressor_cmd,
            stdout=outfile,
            stderr=subprocess.PIPE,
            check=False,
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.decode('utf-8', errors='replace')
            raise OSError(f"Decompression failed: {error_msg}")
```

### 6. Write Tests

**File**: `tests/test_analyse_compressed.py`

**Test cases**:
1. `test_analyse_gzip_file` - Analyze .gz file
2. `test_analyse_zstd_file` - Analyze .zst file
3. `test_analyse_seekable_zstd_file` - Analyze seekable .zst with index info
4. `test_analyse_cache_hit` - Verify cache is used on second analysis
5. `test_analyse_cache_invalidated_on_change` - Verify cache invalidation
6. `test_analyse_shows_compression_info` - Verify compression fields populated
7. `test_analyse_shows_index_info` - Verify index fields populated
8. `test_analyse_no_space_left_handled` - Verify graceful handling of disk full
9. `test_temp_file_cleanup` - Verify temp files are deleted

**File**: `tests/test_analyse_integration.py`

**Test cases**:
1. `test_analyse_regular_file_with_index` - Regular file with index
2. `test_analyse_regular_file_without_index` - Regular file without index
3. `test_analyse_binary_file` - Binary file (no analysis)
4. `test_analyse_cache_workflow` - Full cache workflow

## Testing Strategy

1. **Unit tests**: Individual methods (cache, compression detection, index info)
2. **Integration tests**: Full analyse workflow with real files
3. **Edge cases**: No space left, invalid compressed files, corrupt index files
4. **Performance**: Verify caching improves performance (>10x speedup expected)

## Files to Modify

- `src/rx/analyse.py` - Main implementation
- `src/rx/compression.py` - Add `decompress_to_file()`
- `tests/test_analyse_compressed.py` - NEW
- `tests/test_analyse_integration.py` - NEW

## Success Criteria

- [ ] All new tests pass
- [ ] Existing analyse tests still pass
- [ ] Compressed files can be analyzed
- [ ] Cache improves performance (verified with benchmark)
- [ ] Temp files are always cleaned up
- [ ] No space left errors handled gracefully
- [ ] Index information displayed for all file types
- [ ] Compression information displayed correctly

## Risks & Mitigation

**Risk**: Temp file not cleaned up → **Mitigation**: Use try/finally, test cleanup
**Risk**: No space left crashes → **Mitigation**: Catch OSError, continue gracefully
**Risk**: Cache corruption → **Mitigation**: Validate cache, fallback to fresh analysis
**Risk**: Performance regression → **Mitigation**: Add benchmarks, use cache properly

## Estimated Effort

- Implementation: 2-3 hours
- Testing: 1-2 hours
- **Total**: 3-5 hours
