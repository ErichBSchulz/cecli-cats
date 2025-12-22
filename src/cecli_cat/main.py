import argparse
import sys
from cecli_cat.commands import polyglot

def main():
    parser = argparse.ArgumentParser(description="Cecli Atomic Tests")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    polyglot.add_parser(subparsers)

    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    sys.exit(main())
