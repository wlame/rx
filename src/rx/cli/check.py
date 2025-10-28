"""Check command for regex complexity analysis"""

import sys
import click

from rx.regex import calculate_regex_complexity
from rx.models import ComplexityResponse


@click.command()
@click.argument('pattern', type=str)
@click.option('--json', 'output_json', is_flag=True, help="Output as JSON")
@click.option('--no-color', is_flag=True, help="Disable colored output")
def check_command(pattern, output_json, no_color):
    """
    Analyze regex pattern complexity and detect ReDoS vulnerabilities.

    Calculates a complexity score based on various regex features that
    can impact performance, particularly patterns that may cause
    catastrophic backtracking (ReDoS vulnerabilities).

    \b
    Examples:
      rx check "error.*"
      rx check "(a+)+" --json
      rx check "^[a-z]+$" --no-color

    \b
    Score ranges:
      0-10:    Very Simple (substring search)
      11-30:   Simple (basic patterns)
      31-60:   Moderate (reasonable performance)
      61-100:  Complex (monitor performance)
      101-200: Very Complex (significant impact)
      201+:    Dangerous (ReDoS risk!)
    """
    try:
        # Calculate complexity
        result = calculate_regex_complexity(pattern)
        result['regex'] = pattern

        # Create response model
        response = ComplexityResponse(**result)

        if output_json:
            # JSON output
            click.echo(response.model_dump_json(indent=2))
        else:
            # Human-readable output
            colorize = not no_color and sys.stdout.isatty()
            output = response.to_cli(colorize=colorize)
            click.echo(output)

        # Exit with non-zero code if dangerous
        if result['level'] == 'dangerous':
            sys.exit(2)  # Warning exit code

    except Exception as e:
        click.echo(f"Error analyzing pattern: {e}", err=True)
        sys.exit(1)
