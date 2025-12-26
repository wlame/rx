"""Analyse command for file analysis"""

import sys

import click

from rx.analyse import analyse_path
from rx.models import AnalyseResponse, AnomalyRangeResult, FileAnalysisResult


@click.command()
@click.argument('path', type=click.Path(exists=True), nargs=-1, required=True)
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.option('--no-color', is_flag=True, help='Disable colored output')
@click.option('--max-workers', type=int, default=10, help='Maximum parallel workers (default: 10)')
@click.option(
    '--detect-anomalies',
    is_flag=True,
    help='Detect anomalies in log files (tracebacks, errors, format deviations)',
)
def analyse_command(path, output_json, no_color, max_workers, detect_anomalies):
    """
    Analyze files to extract metadata and statistics.

    Analyzes text and binary files, providing:
    - File size (bytes and human-readable)
    - File metadata (creation time, modification time, permissions, owner)
    - For text files: line count, empty lines, line length statistics

    \b
    Examples:
      rx analyse /var/log/app.log
      rx analyse /var/log/ --json
      rx analyse file1.txt file2.txt --no-color
      rx analyse /path/to/dir --max-workers 20
      rx analyse /var/log/app.log --detect-anomalies

    \b
    Analysis includes:
      - File size (bytes and human-readable format)
      - Creation and modification timestamps
      - File permissions and owner
      - Line count and empty line count (text files)
      - Line length statistics: max, average, median, standard deviation

    \b
    With --detect-anomalies:
      - Detects Python/Java/JS/Go/Rust stack traces
      - Flags lines with ERROR, FATAL, Exception keywords
      - Identifies unusually long lines (>3 stddev from mean)
      - Detects unusual indentation blocks
    """
    try:
        # Convert tuple to list
        paths = list(path)

        # Analyze files
        result = analyse_path(paths, max_workers=max_workers, detect_anomalies=detect_anomalies)

        # Create response model - convert anomalies to Pydantic models
        file_results = []
        for r in result['results']:
            # Convert anomaly dicts to AnomalyRangeResult models if present
            if r.get('anomalies'):
                r['anomalies'] = [AnomalyRangeResult(**a) for a in r['anomalies']]
            file_results.append(FileAnalysisResult(**r))

        response = AnalyseResponse(
            path=result['path'],
            time=result['time'],
            files=result['files'],
            results=file_results,
            scanned_files=result['scanned_files'],
            skipped_files=result['skipped_files'],
        )

        if output_json:
            # JSON output
            click.echo(response.model_dump_json(indent=2))
        else:
            # Human-readable output
            colorize = not no_color and sys.stdout.isatty()
            output = response.to_cli(colorize=colorize)
            click.echo(output)

        # Exit with warning if some files were skipped
        if result['skipped_files']:
            sys.exit(2)  # Warning exit code

    except Exception as e:
        click.echo(f'Error analyzing files: {e}', err=True)
        sys.exit(1)
