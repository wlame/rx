"""CLI command for getting file samples around byte offsets or line numbers."""

import json
import sys

import click

from rx.compressed_index import get_decompressed_content_at_line, get_or_build_compressed_index
from rx.compression import CompressionFormat, detect_compression, is_compressed
from rx.file_utils import get_context, get_context_by_lines, is_text_file
from rx.index import calculate_exact_line_for_offset, calculate_exact_offset_for_line, get_index_path, load_index
from rx.models import SamplesResponse


@click.command("samples")
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--byte-offset",
    "-b",
    multiple=True,
    type=int,
    help="Byte offset(s) to get context for. Can be specified multiple times.",
)
@click.option(
    "--line-offset",
    "-l",
    multiple=True,
    type=int,
    help="Line number(s) to get context for (1-based). Can be specified multiple times.",
)
@click.option(
    "--context",
    "-c",
    type=int,
    default=None,
    help="Number of context lines before and after (default: 3)",
)
@click.option(
    "--before",
    "-B",
    type=int,
    default=None,
    help="Number of context lines before offset",
)
@click.option(
    "--after",
    "-A",
    type=int,
    default=None,
    help="Number of context lines after offset",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.option(
    "--no-color",
    is_flag=True,
    help="Disable colored output",
)
@click.option(
    "--regex",
    "-r",
    type=str,
    default=None,
    help="Regex pattern to highlight in output",
)
def samples_command(
    path: str,
    byte_offset: tuple[int, ...],
    line_offset: tuple[int, ...],
    context: int | None,
    before: int | None,
    after: int | None,
    json_output: bool,
    no_color: bool,
    regex: str | None,
):
    """Get file content around specified byte offsets or line numbers.

    This command reads lines of context around one or more byte offsets
    or line numbers in a text file. Useful for examining specific locations
    in large files.

    Use -b/--byte-offset for byte offsets, or -l/--line-offset for line numbers.
    These options are mutually exclusive.

    Examples:

        rx samples /var/log/app.log -b 1234

        rx samples /var/log/app.log -b 1234 -b 5678 -c 5

        rx samples /var/log/app.log -l 100 -l 200

        rx samples /var/log/app.log -l 100 --before=2 --after=10

        rx samples /var/log/app.log -b 1234 --json
    """
    # Validate mutual exclusivity
    if byte_offset and line_offset:
        click.echo("Error: Cannot use both --byte-offset and --line-offset. Choose one.", err=True)
        sys.exit(1)

    if not byte_offset and not line_offset:
        click.echo("Error: Must provide either --byte-offset (-b) or --line-offset (-l)", err=True)
        sys.exit(1)

    # Check if file is compressed
    file_is_compressed = is_compressed(path)
    compression_format = detect_compression(path) if file_is_compressed else CompressionFormat.NONE

    # Compressed files only support line offset mode
    if file_is_compressed and byte_offset:
        click.echo(
            "Error: Byte offsets are not supported for compressed files. Use --line-offset (-l) instead.",
            err=True,
        )
        sys.exit(1)

    # Validate file is text (skip for compressed files as we can't easily check)
    if not file_is_compressed and not is_text_file(path):
        click.echo(f"Error: {path} is not a text file", err=True)
        sys.exit(1)

    # Determine context lines
    before_context = before if before is not None else context if context is not None else 3
    after_context = after if after is not None else context if context is not None else 3

    if before_context < 0 or after_context < 0:
        click.echo("Error: Context values must be non-negative", err=True)
        sys.exit(1)

    try:
        # Handle compressed files separately
        if file_is_compressed:
            line_list = list(line_offset)

            # Check if this is a seekable zstd file
            from rx.seekable_zstd import is_seekable_zstd

            if is_seekable_zstd(path):
                # Use seekable zstd index for accurate line numbers
                click.echo(f"Processing seekable zstd file...", err=True)
                from rx.seekable_index import get_or_build_index
                from rx.seekable_zstd import decompress_frame, read_seek_table

                index = get_or_build_index(path)
                frames = read_seek_table(path)

                # Get samples for each line using seekable zstd
                context_data = {}
                line_to_offset = {}
                for line_num in line_list:
                    # Find which frame contains this line
                    frame_idx = None
                    frame_info = None
                    for frame in index.frames:
                        if frame.first_line <= line_num <= frame.last_line:
                            frame_idx = frame.index
                            frame_info = frame
                            first_line = frame.first_line
                            break

                    if frame_idx is None:
                        context_data[line_num] = []
                        line_to_offset[str(line_num)] = -1
                        continue

                    # Calculate byte offset for this line
                    # Start with the frame's starting offset, then add bytes for each line before the target
                    frame_offset = frames[frame_idx].decompressed_offset

                    # Decompress the frame to calculate exact offset
                    frame_data = decompress_frame(path, frame_idx, frames)
                    frame_lines = frame_data.decode('utf-8', errors='replace').split('\n')

                    # Calculate line index within frame (0-based)
                    line_in_frame = line_num - first_line

                    # Calculate byte offset by summing lengths of lines before target
                    byte_offset = frame_offset
                    for i in range(line_in_frame):
                        byte_offset += len(frame_lines[i].encode('utf-8')) + 1  # +1 for newline

                    line_to_offset[str(line_num)] = byte_offset

                    # Get context lines
                    start_idx = max(0, line_in_frame - before_context)
                    end_idx = min(len(frame_lines), line_in_frame + after_context + 1)

                    context_data[line_num] = frame_lines[start_idx:end_idx]
            else:
                # Use generic compressed index for other formats
                click.echo(f"Processing compressed file ({compression_format.value})...", err=True)
                index_data = get_or_build_compressed_index(path)

                # Get samples for each line
                context_data = {}
                for line_num in line_list:
                    lines = get_decompressed_content_at_line(
                        path,
                        line_num,
                        context_before=before_context,
                        context_after=after_context,
                        index_data=index_data,
                    )
                    context_data[line_num] = lines

            # Use calculated offsets for seekable zstd, -1 for other formats
            if is_seekable_zstd(path):
                lines_dict = line_to_offset
            else:
                lines_dict = {str(ln): -1 for ln in line_list}

            response = SamplesResponse(
                path=path,
                offsets={},
                lines=lines_dict,
                before_context=before_context,
                after_context=after_context,
                samples={str(k): v for k, v in context_data.items()},
                is_compressed=True,
                compression_format=compression_format.value,
            )

            if json_output:
                click.echo(json.dumps(response.model_dump(), indent=2))
            else:
                colorize = not no_color and sys.stdout.isatty()
                click.echo(response.to_cli(colorize=colorize, regex=regex))
            return

        if byte_offset:
            # Byte offset mode
            offset_list = list(byte_offset)
            context_data = get_context(path, offset_list, before_context, after_context)

            # Calculate line numbers for each byte offset
            offset_to_line = {}
            index_data = load_index(get_index_path(path))
            for offset in offset_list:
                line_num = calculate_exact_line_for_offset(path, offset, index_data)
                offset_to_line[str(offset)] = line_num

            response = SamplesResponse(
                path=path,
                offsets=offset_to_line,
                lines={},
                before_context=before_context,
                after_context=after_context,
                samples={str(k): v for k, v in context_data.items()},
            )
        else:
            # Line offset mode
            line_list = list(line_offset)
            context_data = get_context_by_lines(path, line_list, before_context, after_context)

            # Calculate byte offsets for each line number
            line_to_offset = {}
            index_data = load_index(get_index_path(path))
            for line_num in line_list:
                byte_offset = calculate_exact_offset_for_line(path, line_num, index_data)
                line_to_offset[str(line_num)] = byte_offset

            response = SamplesResponse(
                path=path,
                offsets={},
                lines=line_to_offset,
                before_context=before_context,
                after_context=after_context,
                samples={str(k): v for k, v in context_data.items()},
            )

        if json_output:
            click.echo(json.dumps(response.model_dump(), indent=2))
        else:
            colorize = not no_color and sys.stdout.isatty()
            click.echo(response.to_cli(colorize=colorize, regex=regex))

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
