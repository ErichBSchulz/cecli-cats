import argparse
import logging
import yaml
from pathlib import Path

from cecli_cat.utils import calculate_directory_hash


def run(args):
    # Setup logging
    level = logging.WARNING
    if args.quiet:
        level = logging.ERROR
    elif args.verbose == 1:
        level = logging.INFO
    elif args.verbose >= 2:
        level = logging.DEBUG

    logging.basicConfig(level=level, format="%(message)s")
    logger = logging.getLogger(__name__)

    root = Path.cwd()
    cat_root = root / "cat"

    if not cat_root.exists():
        logger.error("No 'cat' directory found.")
        return

    logger.info("Checking hashes for all tests in cat/...")

    checked_count = 0
    updated_count = 0

    for cat_file in cat_root.rglob("cat.yaml"):
        test_dir = cat_file.parent
        checked_count += 1

        current_hash = calculate_directory_hash(test_dir)

        with open(cat_file, "r") as f:
            data = yaml.safe_load(f) or {}

        old_hash = data.get("hash")

        if current_hash != old_hash:
            logger.info(
                f"Updating hash for {test_dir.name}: {old_hash} -> {current_hash}"
            )
            data["hash"] = current_hash

            with open(cat_file, "w") as f:
                yaml.dump(data, f, sort_keys=False)
            updated_count += 1
        else:
            logger.debug(f"Hash match for {test_dir.name}")

    logger.info(f"Checked {checked_count} tests. Updated {updated_count} hashes.")


def add_parser(subparsers):
    parser = subparsers.add_parser(
        "rehash",
        help="Recalculate hashes for all tests",
        description="""
        Visits every directory in 'cat/', recalculates the hash (excluding cat.yaml and LICENSE),
        and updates the cat.yaml file if the hash has changed.
        """,
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet output")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v, -vv)",
    )
    parser.set_defaults(func=run)
