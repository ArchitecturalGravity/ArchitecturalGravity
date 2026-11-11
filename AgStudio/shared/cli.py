"""Run the same analysis as the editor: python -m AgStudio.shared.cli [--json] file.arc."""
import argparse
import json
from pathlib import Path
import sys

from .lint import analyze
from .diagnostics import SEVERITY_ORDER


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', help='UTF-8 .arc files; - reads stdin')
    parser.add_argument('--json', action='store_true', help='Versioned JSON with exact code-point ranges')
    parser.add_argument('--arcgrav-version', default='current')
    parser.add_argument('--fail-on', choices=('critical', 'error', 'warning', 'never'), default='error')
    args = parser.parse_args(argv)
    records = []
    failed = False
    io_error = False
    for filename in args.files:
        try:
            data = sys.stdin.buffer.read() if filename == '-' else Path(filename).read_bytes()
            source = data.decode('utf-8-sig')
            result = analyze(source, arcgrav_version=args.arcgrav_version)
            record = {'file': filename, **result.as_record()}
            failed |= args.fail_on != 'never' and any(
                SEVERITY_ORDER[f.severity] >= SEVERITY_ORDER[args.fail_on]
                for f in result.diagnostics.findings)
            if not args.json:
                for f in result.diagnostics.findings:
                    p = f.source_range.start
                    print(f'{filename}:{p.line}:{p.column}: {f.severity} {f.rule_id}: {f.message}')
                print(f'{filename}: {len(result.diagnostics.findings)} findings; overall conformance unknown')
        except (OSError, UnicodeError, ValueError) as exc:
            io_error = True
            record = {'file': filename, 'error': str(exc), 'conformance': 'unknown'}
            if not args.json:
                print(f'{filename}: {exc}', file=sys.stderr)
        records.append(record)
    if args.json:
        print(json.dumps({'schema_version': 1, 'results': records}, ensure_ascii=True, sort_keys=True))
    return 2 if io_error else 1 if failed and args.fail_on != 'never' else 0


if __name__ == '__main__':
    raise SystemExit(main())
