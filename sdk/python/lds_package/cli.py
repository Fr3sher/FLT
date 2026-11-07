"""The developer CLI deliberately performs no build, install or network access."""
from __future__ import annotations

import argparse
import json
import sys

from .core import PackageError, pack, validate


def main(argv=None):
    parser = argparse.ArgumentParser(description='Validate or reproducibly package an LDS v2 plugin')
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('validate', 'pack'):
        child = commands.add_parser(command)
        child.add_argument('source')
        child.add_argument('--lds-source', help='Trusted development checkout containing LDS manifest rules and SDK')
        child.add_argument('--official-lds', action='store_true', help='Explicit LDS authoring conversion; grants no installation trust')
        child.add_argument('--js-tools', help='Trusted directory with installed Acorn (sdk/python by default)')
        if command == 'pack':
            child.add_argument('--output', required=True)
            child.add_argument('--overwrite', action='store_true')
    args = parser.parse_args(argv)
    options = {'lds_source': args.lds_source, 'official_lds': args.official_lds, 'js_tools': args.js_tools}
    try:
        report = (pack(args.source, args.output, overwrite=args.overwrite, **options) if args.command == 'pack'
                  else validate(args.source, **options).report())
    except (PackageError, OSError, UnicodeError, SyntaxError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 2
    # JSON escapes preserve Unicode labels even when a Windows pipe uses cp1252.
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
    return 0
