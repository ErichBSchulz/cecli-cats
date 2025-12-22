import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Cecli Atomic Tests")
    args = parser.parse_args()
    print("Hello from cecli-cat!")


if __name__ == "__main__":
    sys.exit(main())
