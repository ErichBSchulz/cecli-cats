import argparse
import logging
import shutil
import uuid
import yaml
from pathlib import Path
from typing import List

from cecli_cat.utils import calculate_directory_hash

# Map from language (dir name) to repo URL based on README
REPO_MAP = {
    "cpp": "https://github.com/exercism/cpp",
    "go": "https://github.com/exercism/go",
    "java": "https://github.com/exercism/java",
    "javascript": "https://github.com/exercism/javascript",
    "python": "https://github.com/exercism/python",
    "rust": "https://github.com/exercism/rust",
}


def find_polyglot_tests() -> List[Path]:
    """
    Find tests using equivalent logic to `tf4 | grep 'practice/'`.
    We search for directories matching the structure */exercises/practice/*.
    """
    tests = []
    root = Path.cwd()

    # We expect structure like: language/exercises/practice/exercise-name
    for language in REPO_MAP.keys():
        practice_dir = root / language / "exercises" / "practice"
        if practice_dir.exists():
            for item in practice_dir.iterdir():
                if item.is_dir():
                    tests.append(item)

    return sorted(tests)


def process_test(test_dir: Path):
    logger = logging.getLogger(__name__)

    # Identify language
    try:
        # Assuming run from root, language is the first part
        rel_path = test_dir.absolute().relative_to(Path.cwd())
        language = rel_path.parts[0]
    except ValueError:
        language = "unknown"

    source_url = REPO_MAP.get(language, "Exercism")

    # Generate UUID
    test_uuid = str(uuid.uuid4())

    # Hash
    dir_hash = calculate_directory_hash(test_dir)

    # Target path: cat/f4/7a/f47ac10b...
    prefix1 = test_uuid[:2]
    prefix2 = test_uuid[2:4]
    target_dir = Path("cat") / prefix1 / prefix2 / test_uuid

    logger.info(f"Migrating {test_dir} -> {target_dir}")
    logger.debug(f"UUID: {test_uuid}, Hash: {dir_hash}, Lang: {language}")

    if target_dir.exists():
        shutil.rmtree(target_dir)

    # Copy directory
    shutil.copytree(test_dir, target_dir)

    # Create cat.yaml
    cat_data = {
        "uuid": test_uuid,
        "hash": dir_hash,
        "language": language,
        "sets": ["polyglot"],
        "source": source_url,
    }

    with open(target_dir / "cat.yaml", "w") as f:
        yaml.dump(cat_data, f, sort_keys=False)


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

    logger.info("Finding polyglot tests...")
    tests = find_polyglot_tests()

    if not tests:
        logger.warning("No tests found.")
        return

    logger.info(f"Found {len(tests)} tests. Reorganising...")

    for test in tests:
        process_test(test)

    logger.info("Done.")


def add_parser(subparsers):
    parser = subparsers.add_parser(
        "polyglot_to_cat",
        help="Reorganise polyglot tests into cat structure",
        description="""
        Finds polyglot tests in the current directory (looking for */exercises/practice/*)
        and reorganises them into a canonical 'cat' structure.
        
        For each test:
        1. Assigns a new UUID.
        2. Calculates a content hash.
        3. Copies the test to cat/{uuid_prefix}/{uuid_prefix}/{uuid}.
        4. Creates a cat.yaml metadata file.
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
