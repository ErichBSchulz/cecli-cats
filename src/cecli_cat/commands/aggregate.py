import argparse
import csv
import json
import logging
import re
import yaml
from collections import defaultdict
from pathlib import Path


def load_index(index_file: Path):
    index = {}
    if not index_file.exists():
        return index
    try:
        with open(index_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # key by (language, name)
                key = (row.get("language"), row.get("name"))
                index[key] = row
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to load index {index_file}: {e}")
    return index


def find_run_dir(path: Path):
    # Pattern: YYYY-MM-DD-HH-MM-SS--*
    # Example: 2025-12-23-04-35-48--unnamed
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}--.*$")
    curr = path.parent
    # Traverse up until we reach root or find a match
    while curr != curr.parent:
        if pattern.match(curr.name):
            return curr
        curr = curr.parent
    return None


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

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    index_file = Path(args.index_file)

    logger.info(f"Loading index from {index_file}...")
    index = load_index(index_file)

    logger.info(f"Scanning {in_dir} for test runs...")

    # Store as results[run_name][model_name] = [test_data, ...]
    aggregated = defaultdict(lambda: defaultdict(list))

    # We look for .aider.results.json
    try:
        files = list(in_dir.rglob(".aider.results.json"))
    except Exception as e:
        logger.error(f"Error scanning directory {in_dir}: {e}")
        return

    logger.info(f"Found {len(files)} result files. Processing...")

    processed_count = 0
    skipped_count = 0

    for res_file in files:
        run_dir = find_run_dir(res_file)
        if not run_dir:
            logger.debug(
                f"Skipping {res_file}: Not inside a recognizable run directory."
            )
            skipped_count += 1
            continue

        run_name = run_dir.name

        try:
            with open(res_file, "r") as f:
                res_json = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {res_file}: {e}")
            skipped_count += 1
            continue

        model_name = res_json.get("model", "unknown")

        # Determine identity
        test_dir = res_file.parent
        cat_file = test_dir / "cat.yaml"

        uuid = None
        test_hash = None

        if cat_file.exists():
            # New style: read from cat.yaml
            try:
                with open(cat_file, "r") as f:
                    cat_data = yaml.safe_load(f) or {}
                    uuid = cat_data.get("uuid")
                    test_hash = cat_data.get("hash")
            except Exception as e:
                logger.warning(f"Failed to read cat.yaml in {test_dir}: {e}")
        else:
            # Classic style: infer from path relative to run_dir
            try:
                rel_path = test_dir.relative_to(run_dir)
                parts = rel_path.parts
                # Expecting structure like: LANGUAGE/exercises/practice/NAME
                # We need at least language and name.
                # parts[0] is typically language. parts[-1] is name.
                # We check for 'exercises' and 'practice' to be safer if depth allows
                if len(parts) >= 2:
                    lang = parts[0]
                    name = parts[-1]
                    key = (lang, name)
                    if key in index:
                        uuid = index[key].get("uuid")
                        test_hash = index[key].get("hash")
                    else:
                        logger.debug(f"Classic test not found in index: {lang}/{name}")
            except ValueError:
                # Not relative to run_dir? Should not happen given logic above
                pass

        # Enrich result
        if uuid:
            res_json["cat_uuid"] = uuid
        if test_hash:
            res_json["cat_hash"] = test_hash

        # Add path relative to run dir for debugging/reference
        try:
            res_json["run_relative_path"] = str(test_dir.relative_to(run_dir))
        except ValueError:
            res_json["run_relative_path"] = str(test_dir)

        aggregated[run_name][model_name].append(res_json)
        processed_count += 1

    logger.info(
        f"Processed {processed_count} results (skipped {skipped_count}). Saving aggregation..."
    )

    # Write output
    for run_name, models in aggregated.items():
        for model_name, results in models.items():
            # Construct path: out_dir/model_name/run_name/results.json
            # Note: Model names can contain characters not suitable for paths (e.g., :)
            # However, user requested /runs/MODELNAME/RUNNAME. We will trust the inputs mostly,
            # but maybe a small safety replacement for slash could be wise if model has it.
            # Assuming typical unix fs, ':' is allowed.

            target_dir = out_dir / model_name / run_name
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                target_file = target_dir / "results.json"
                with open(target_file, "w") as f:
                    json.dump(results, f, indent=2)
                logger.debug(f"Saved {target_file}")
            except OSError as e:
                logger.error(
                    f"Failed to write results for {run_name}/{model_name}: {e}"
                )

    logger.info("Aggregation complete.")


def add_parser(subparsers):
    parser = subparsers.add_parser(
        "aggregate",
        help="Aggregate test results from run directories",
        description="""
        Scans a directory for test runs (matching YYYY-MM-DD-HH-MM-SS--*), finds
        all .aider.results.json files, enriches them with cat UUID/Hash (via cat.yaml or index.csv),
        and saves aggregated JSON files organized by Model and Run.
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
    parser.add_argument(
        "-i",
        "--in-dir",
        default="..",
        help="Input directory to scan (default: ..)",
    )
    parser.add_argument(
        "-o",
        "--out-dir",
        default="results",
        help="Output directory for aggregated results (default: results)",
    )
    parser.add_argument(
        "--index-file",
        default="cat/index.csv",
        help="Path to index.csv for classic test lookup (default: cat/index.csv)",
    )
    parser.set_defaults(func=run)
