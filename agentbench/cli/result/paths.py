"""Explicit result-directory selection and legacy CLI location compatibility."""
from pathlib import Path


def configure_result_paths(parser, *, legacy_option):
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--results-dir', type=Path, metavar='DIR', help=(
        'ABB result directory; managed Suites save DIR/suites/<suite-id>/events.json. '
        'Created if missing; independent of SDK output.'))
    group.add_argument(legacy_option, type=Path, metavar='PATH', help=(
        'Deprecated result location. For managed Suites, a file path selects its parent '
        'directory; the requested filename is not created. Use --results-dir instead.'))


def legacy_results_parent(output_path):
    base = Path(output_path).resolve()
    # Retain the historical naming-base rule for existing callers.
    return base if not base.suffix and base.is_dir() else base.parent


def validate_results_dir(output_path, results_dir):
    if results_dir is None:
        return None
    if output_path is not None:
        raise ValueError('Pass results_dir or the legacy output_path, not both')
    directory = Path(results_dir).resolve()
    if directory.exists() and not directory.is_dir():
        raise ValueError('The ABB results directory must be a directory, not a file')
    return directory


def legacy_result_notice(option, output_path, output_fn):
    directory = legacy_results_parent(output_path)
    output_fn(f'Deprecated: {option} selects {directory} for managed Suite results; '
              'it does not create the requested file. '
              f'Use --results-dir "{directory}" instead. '
              'The actual events.json path is printed as Result saved.')
