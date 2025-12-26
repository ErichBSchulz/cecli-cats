import argparse
import csv
import json
import logging
import re
import shlex
import yaml
from collections import defaultdict
from pathlib import Path

REQUIRED_KEYS = [
    "testdir",
    "testcase",
    "model",
    "edit_format",
    "tests_outcomes",
    "cost",
]


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


def run_aggregate(args):
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

    # Store as results[run_name][model_name] = {"results": [], "rejected_count": 0}
    aggregated = defaultdict(
        lambda: defaultdict(lambda: {"results": [], "rejected_count": 0})
    )

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
        bucket = aggregated[run_name][model_name]

        # Validation
        if not all(k in res_json for k in REQUIRED_KEYS):
            logger.debug(f"Rejecting {res_file}: Missing required keys.")
            bucket["rejected_count"] += 1
            continue

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

        bucket["results"].append(res_json)
        processed_count += 1

    logger.info(
        f"Processed {processed_count} results (skipped {skipped_count}). Saving aggregation..."
    )

    # Prepare table data
    table_rows = []

    # Write output and collect stats
    for run_name, models in aggregated.items():
        for model_name, data in models.items():
            results = data["results"]
            rejected_count = data["rejected_count"]
            count = len(results)
            # Pass if any test outcome is true
            pass_count = sum(1 for r in results if any(r.get("tests_outcomes", [])))

            output_data = {
                "summary": {
                    "count": count,
                    "pass": pass_count,
                    "rejected": rejected_count,
                },
                "results": results,
            }

            table_rows.append((run_name, model_name, count, pass_count, rejected_count))

            # Construct path: out_dir/model_name/run_name/results.json
            target_dir = out_dir / model_name / run_name
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                target_file = target_dir / "results.json"
                with open(target_file, "w") as f:
                    json.dump(output_data, f, indent=2)
                logger.debug(f"Saved {target_file}")
            except OSError as e:
                logger.error(
                    f"Failed to write results for {run_name}/{model_name}: {e}"
                )

    if not args.quiet and table_rows:
        print(f"\n{'Run':<40} {'Model':<40} {'Count':>8} {'Pass':>8} {'Reject':>8}")
        print("-" * 108)
        for row in sorted(table_rows):
            r_name, m_name, c, p, rej = row
            # Truncate names if too long
            r_disp = (r_name[:37] + "...") if len(r_name) > 37 else r_name
            m_disp = (m_name[:37] + "...") if len(m_name) > 37 else m_name
            print(f"{r_disp:<40} {m_disp:<40} {c:>8} {p:>8} {rej:>8}")
        print()

    logger.info("Aggregation complete.")


def run_clean(args):
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

    # 1. Scan Source Runs
    if in_dir.exists():
        # Group files by run directory
        run_files = defaultdict(list)
        try:
            for res_file in in_dir.rglob(".aider.results.json"):
                run_dir = find_run_dir(res_file)
                if run_dir:
                    run_files[run_dir].append(res_file)
        except Exception as e:
            logger.error(f"Error scanning input directory {in_dir}: {e}")

        for run_dir, files in run_files.items():
            rejected_count = 0
            total_count = 0
            for f in files:
                total_count += 1
                try:
                    with open(f, "r") as fh:
                        data = json.load(fh)
                        if not all(k in data for k in REQUIRED_KEYS):
                            rejected_count += 1
                except Exception:
                    rejected_count += 1  # count read errors as rejected/bad

            if total_count > 0 and rejected_count == total_count:
                print(f"rm -rf {shlex.quote(str(run_dir))}")

    # 2. Scan Aggregated Runs
    if out_dir.exists():
        for res_file in out_dir.rglob("results.json"):
            try:
                with open(res_file, "r") as f:
                    data = json.load(f)
                    summary = data.get("summary", {})
                    count = summary.get("count", 0)
                    rejected = summary.get("rejected", 0)
                    if count > 0 and rejected == count:
                        print(f"rm -rf {shlex.quote(str(res_file.parent))}")
            except Exception as e:
                logger.debug(f"Failed to read/parse {res_file}: {e}")


def add_parser(subparsers):
    results_parser = subparsers.add_parser(
        "results",
        help="Manage test results",
        description="Commands for aggregating and managing test results.",
    )
    results_subparsers = results_parser.add_subparsers(
        dest="results_command", required=True
    )

    # Aggregate subcommand
    agg_parser = results_subparsers.add_parser(
        "aggregate",
        help="Aggregate test results from run directories",
        description="""
        Scans a directory for test runs (matching YYYY-MM-DD-HH-MM-SS--*), finds
        all .aider.results.json files, enriches them with cat UUID/Hash (via cat.yaml or index.csv),
        and saves aggregated JSON files organized by Model and Run.
        """,
    )
    agg_parser.add_argument("-q", "--quiet", action="store_true", help="Quiet output")
    agg_parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v, -vv)",
    )
    agg_parser.add_argument(
        "-i",
        "--in-dir",
        default="..",
        help="Input directory to scan (default: ..)",
    )
    agg_parser.add_argument(
        "-o",
        "--out-dir",
        default="results",
        help="Output directory for aggregated results (default: results)",
    )
    agg_parser.add_argument(
        "--index-file",
        default="cat/index.csv",
        help="Path to index.csv for classic test lookup (default: cat/index.csv)",
    )
    agg_parser.set_defaults(func=run_aggregate)

    # Clean subcommand
    clean_parser = results_subparsers.add_parser(
        "clean",
        help="List directories with 100%% rejected results",
        description="""
        Lists directories containing runs (source data and aggregated) that have 100% rejected results.
        Useful for identifying failed runs that can be deleted.
        """,
    )
    clean_parser.add_argument("-q", "--quiet", action="store_true", help="Quiet output")
    clean_parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v, -vv)",
    )
    clean_parser.add_argument(
        "-i",
        "--in-dir",
        default="..",
        help="Input directory to scan (default: ..)",
    )
    clean_parser.add_argument(
        "-o",
        "--out-dir",
        default="results",
        help="Output directory for aggregated results (default: results)",
    )
    clean_parser.set_defaults(func=run_clean)
