import argparse
import sys
from cecli_cat.commands import (
    cats,
    results,
)


def main():
    parser = argparse.ArgumentParser(
        description="Cecli Atomic Tests",
        epilog="For detailed help on a specific command, run: cecli-cat <command> -h",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    cats.add_parser(subparsers)
    results.add_parser(subparsers)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    sys.exit(main())
