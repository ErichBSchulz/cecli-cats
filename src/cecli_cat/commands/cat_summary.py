import argparse
import csv
import logging
from collections import defaultdict
from pathlib import Path


def run(args):
    # Setup logging
    level = logging.WARNING
    if args.quiet:
        level = logging.ERROR

    logging.basicConfig(level=level, format="%(message)s")
    logger = logging.getLogger(__name__)

    in_file = Path(args.in_file)

    if not in_file.exists():
        logger.error(f"Input file '{in_file}' does not exist.")
        return

    tests_by_lang = defaultdict(list)
    total_tests = 0

    try:
        with open(in_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                lang = row.get("language", "unknown")
                tests_by_lang[lang].append(row)
                total_tests += 1
    except Exception as e:
        logger.error(f"Failed to read {in_file}: {e}")
        return

    # If verbose, list tests
    if args.verbose >= 1:
        for lang in sorted(tests_by_lang.keys()):
            tests = tests_by_lang[lang]
            print(f"\nLanguage: {lang} ({len(tests)} tests)")
            for test in sorted(tests, key=lambda x: x.get("name", "")):
                name = test.get("name", "unnamed")
                path = test.get("path", "")
                print(f"  - {name:<30} {path}")
        print()

    # Print summary table
    print(f"{'Language':<20} {'Count':>10}")
    print("-" * 31)

    for lang in sorted(tests_by_lang.keys()):
        count = len(tests_by_lang[lang])
        print(f"{lang:<20} {count:>10}")

    print("-" * 31)
    print(f"{'Total':<20} {total_tests:>10}")


def add_parser(subparsers):
    parser = subparsers.add_parser(
        "cat_summary",
        help="Summarize tests from the CSV index",
        description="""
        Reads the CSV index file and produces a summary of tests per language.
        """,
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet output")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (show test details)",
    )
    parser.add_argument(
        "-i",
        "--in-file",
        default="cat/index.csv",
        help="Input CSV file path (default: cat/index.csv)",
    )
    parser.set_defaults(func=run)
