import argparse
import csv
import json
import logging
import re
import shlex
import shutil
import yaml
import pandas as pd
from tabulate import tabulate
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

DEFAULT_CONSOLIDATED_FILE = "results.csv"


def setup_logging(args):
    level = logging.WARNING
    if args.quiet:
        level = logging.ERROR
    elif args.verbose == 1:
        level = logging.INFO
    elif args.verbose >= 2:
        level = logging.DEBUG

    logging.basicConfig(level=level, format="%(message)s")
    return logging.getLogger(__name__)


def add_common_args(parser):
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet output")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v, -vv)",
    )


def add_decimals_arg(parser):
    parser.add_argument(
        "--decimals",
        type=int,
        help="Number of decimal places (default: 3 for quiet, 5 for normal, raw for verbose)",
    )


def format_dataframe(df, args):
    decimals = getattr(args, "decimals", None)
    if decimals is None:
        if args.quiet:
            decimals = 3
        elif args.verbose == 0:
            decimals = 5

    if decimals is not None:
        df = df.round(decimals)

        # Handle object columns that might contain floats (e.g. min/max in describe output)
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].apply(
                lambda x: round(x, decimals) if isinstance(x, float) else x
            )

    return df.fillna("")


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
    logger = setup_logging(args)

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


def run_consolidate(args):
    logger = setup_logging(args)

    results_dir = Path(args.results_dir)
    cats_dir = Path(args.cats_dir)
    out_file = Path(args.out_file)
    index_file = cats_dir / "index.csv"

    # Load index keyed by UUID
    cat_index = {}
    if index_file.exists():
        logger.info(f"Loading index from {index_file}...")
        try:
            with open(index_file, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    uid = row.get("uuid")
                    if uid:
                        # Parse sets (semicolon separated in index)
                        sets_str = row.get("sets", "")
                        row["set_list"] = [
                            s.strip() for s in sets_str.split(";") if s.strip()
                        ]
                        cat_index[uid] = row
        except Exception as e:
            logger.warning(f"Failed to read index {index_file}: {e}")
    else:
        logger.warning(
            f"Index file {index_file} not found. Metadata validation will be limited."
        )

    if not results_dir.exists():
        logger.error(f"Results directory '{results_dir}' does not exist.")
        return

    logger.info(f"Scanning {results_dir} for results.json files...")
    result_files = list(results_dir.rglob("results.json"))
    logger.info(f"Found {len(result_files)} files. Processing...")

    all_sets = set()
    rows = []
    processed_count = 0

    for res_file in result_files:
        try:
            with open(res_file, "r") as f:
                data = json.load(f)

            results_list = data.get("results", [])
            # In results.json, usually structured as {"summary": ..., "results": [...]}

            # The run name is the parent directory name
            run_name = res_file.parent.name

            for res in results_list:
                processed_count += 1

                # Create base row
                row = {}
                row["run"] = run_name

                # Copy scalar fields, exclude dropped/handled ones
                exclude = {
                    "tests_outcomes",
                    "chat_hashes",
                    "cat_uuid",
                    "cat_hash",
                    "source",
                }
                for k, v in res.items():
                    if k not in exclude and not isinstance(v, (list, dict)):
                        row[k] = v

                # Handle outcomes
                outcomes = res.get("tests_outcomes", [])
                if isinstance(outcomes, list):
                    row["tests_outcomes"] = "".join(
                        ["P" if x else "F" for x in outcomes]
                    )
                else:
                    row["tests_outcomes"] = str(outcomes)

                # Metadata and sets
                uuid = res.get("cat_uuid")
                res_hash = res.get("cat_hash")

                row["uuid"] = uuid
                row["hash"] = res_hash

                notes = []
                cat_sets = []

                if uuid:
                    if uuid in cat_index:
                        idx_entry = cat_index[uuid]

                        # Validate hash
                        idx_hash = idx_entry.get("hash")
                        if idx_hash and res_hash and idx_hash != res_hash:
                            notes.append(f"Hash mismatch (index: {idx_hash[:8]}...)")

                        # Enrich language if missing
                        if "language" not in row or row["language"] == "unknown":
                            row["language"] = idx_entry.get("language", "unknown")

                        # Sets
                        cat_sets = idx_entry.get("set_list", [])
                    else:
                        notes.append("UUID not found in index")
                else:
                    notes.append("No UUID in result")

                row["sets"] = ",".join(cat_sets)
                for s in cat_sets:
                    all_sets.add(s)
                    row[f"set_{s}"] = 1

                if notes:
                    row["notes"] = "; ".join(notes)
                else:
                    row["notes"] = ""

                rows.append(row)

        except Exception as e:
            logger.warning(f"Error processing {res_file}: {e}")

    # Finalize columns
    fieldnames = set()
    for r in rows:
        fieldnames.update(r.keys())

    # Ensure all set columns exist in all rows
    sorted_sets = sorted(list(all_sets))
    set_cols = [f"set_{s}" for s in sorted_sets]

    for s_col in set_cols:
        fieldnames.add(s_col)
        for r in rows:
            if s_col not in r:
                r[s_col] = 0

    # Determine column order
    priority = [
        "run",
        "model",
        "language",
        "testcase",
        "uuid",
        "hash",
        "tests_outcomes",
        "cost",
        "duration",
        "sets",
        "notes",
    ]
    ordered = [f for f in priority if f in fieldnames]
    others = sorted(
        [f for f in fieldnames if f not in ordered and not f.startswith("set_")]
    )

    final_header = ordered + others + set_cols

    logger.info(f"Writing {len(rows)} rows to {out_file}...")

    try:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=final_header)
            writer.writeheader()
            writer.writerows(rows)

        if not args.quiet:
            print(f"Consolidated {len(rows)} results into {out_file}")
            print(f"Total Sets found: {len(sorted_sets)} ({', '.join(sorted_sets)})")

    except Exception as e:
        logger.error(f"Failed to write output file: {e}")


def run_describe(args):
    logger = setup_logging(args)

    input_file = Path(args.input_file)
    if not input_file.exists():
        logger.error(f"Error: File {input_file} not found.")
        logger.error("Please run 'cecli-cat results consolidate' first to generate it.")
        return

    try:
        df = pd.read_csv(input_file)
        desc = df.describe(include="all").transpose()
        if "top" in desc.columns:
            desc = desc.drop(columns=["top"])

        desc = format_dataframe(desc, args)
        print(tabulate(desc, headers="keys", tablefmt="simple", showindex=True))
    except Exception as e:
        logger.error(f"Error processing {input_file}: {e}")


def run_crosstab(args):
    logger = setup_logging(args)

    input_file = Path(args.input_file)
    if not input_file.exists():
        logger.error(f"Error: File {input_file} not found.")
        logger.error("Please run 'cecli-cat results consolidate' first to generate it.")
        return

    try:
        df = pd.read_csv(input_file)

        # Derive passed if possible
        if "tests_outcomes" in df.columns:
            # "P" indicates at least one pass in the boolean string logic
            df["passed"] = (
                df["tests_outcomes"].astype(str).apply(lambda x: 1 if "P" in x else 0)
            )

        # Determine grouping columns (dimensions)
        dimensions = []
        if args.group_by:
            dimensions = [c.strip() for c in args.group_by.split(",") if c.strip()]
        else:
            # Defaults
            candidates = []
            if args.quiet:
                candidates = ["model"]
            else:
                candidates = ["model", "language", "edit_format"]

            if args.verbose >= 1:
                candidates.append("tests_outcomes")
                # Add set_* columns
                candidates.extend([c for c in df.columns if c.startswith("set_")])

            if args.verbose >= 2:
                # Add all numeric fields
                candidates.extend(df.select_dtypes(include="number").columns.tolist())

            # Filter duplicates and existence
            seen = set()
            for c in candidates:
                if c in df.columns and c not in seen:
                    dimensions.append(c)
                    seen.add(c)

        if not dimensions:
            logger.error("No valid grouping columns found.")
            return

        # Determine outcome columns
        outcome_cols = []
        if args.outcome:
            outcome_cols = [c.strip() for c in args.outcome.split(",") if c.strip()]
        else:
            # Defaults
            candidates = []
            if "passed" in df.columns:
                candidates.append("passed")

            if not args.quiet:
                # Normal
                candidates.extend(
                    [
                        "prompt_tokens",
                        "cost",
                        "duration",
                        "completion_tokens",
                        "thinking_tokens",
                    ]
                )

            if args.verbose >= 1:
                # V
                candidates.extend(
                    [
                        "indentation_errors",
                        "lazy_comments",
                        "map_tokens",
                        "num_error_outputs",
                        "num_exhausted_context_windows",
                        "num_malformed_responses",
                        "num_user_asks",
                        "reasoning_effort",
                        "syntax_errors",
                        "test_timeouts",
                    ]
                )

            if args.verbose >= 2:
                # VV
                candidates.extend(df.select_dtypes(include="number").columns.tolist())

            # Filter duplicates and existence
            seen = set()
            for c in candidates:
                if c in df.columns and c not in seen:
                    outcome_cols.append(c)
                    seen.add(c)

        # Aggregation
        for dim in dimensions:
            print(f"\nDimension: {dim}")
            if not outcome_cols:
                # Just count rows
                res = df.groupby([dim]).size().reset_index(name="count")
            else:
                # Metric aggregation
                agg_dict = {}
                for c in outcome_cols:
                    agg_dict[c] = ["sum", "mean", "count"]

                res = df.groupby([dim]).agg(agg_dict)

                # Flatten MultiIndex columns
                res.columns = ["_".join(col).strip() for col in res.columns.values]

                # Add a generic group size count
                res["group_count"] = df.groupby([dim]).size().values

                res.reset_index(inplace=True)

            res = format_dataframe(res, args)

            print(tabulate(res, headers="keys", tablefmt="grid", showindex=False))

    except Exception as e:
        logger.error(f"Error: {e}")


def run_clean(args):
    logger = setup_logging(args)

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)

    paths_to_remove = []

    if not in_dir.exists():
        logger.error(f"Input directory '{in_dir}' does not exist.")
        return

    # 1. Scan Source Runs
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
            paths_to_remove.append(run_dir)

    # 2. Scan Aggregated Runs
    search_dirs = [out_dir]
    # If in_dir is different from out_dir, we scan it too (it might contain results)
    if in_dir.resolve() != out_dir.resolve():
        search_dirs.append(in_dir)

    seen_aggregated = set()
    for d in search_dirs:
        if not d.exists():
            continue
        for res_file in d.rglob("results.json"):
            # Deduplicate by absolute path
            try:
                resolved = res_file.resolve()
                if resolved in seen_aggregated:
                    continue
                seen_aggregated.add(resolved)

                with open(res_file, "r") as f:
                    data = json.load(f)
                    summary = data.get("summary", {})
                    count = summary.get("count", 0)
                    rejected = summary.get("rejected", 0)
                    if rejected > 0 and count == 0:
                        paths_to_remove.append(res_file.parent)
            except Exception as e:
                logger.debug(f"Failed to read/parse {res_file}: {e}")

    if not paths_to_remove:
        logger.info("No broken runs found.")
        return

    # Generate commands for display
    cmds = [f"rm -rf {shlex.quote(str(p))}" for p in paths_to_remove]

    if not args.yolo and not args.interactive:
        print("# run these commands to remove the broken runs")
        for cmd in cmds:
            print(cmd)
        return

    # If yolo or interactive
    if args.interactive and not args.yolo:
        print("The following directories will be removed:")
        for cmd in cmds:
            print(cmd)
        try:
            response = input("Run these commands? [y/N] ").strip().lower()
        except EOFError:
            response = "n"
        if response != "y":
            print("Aborted.")
            return

    # Execution (yolo or interactive=yes)
    for p in paths_to_remove:
        if p.exists():
            logger.info(f"Removing {p}...")
            shutil.rmtree(p, ignore_errors=True)


def add_parser(subparsers):
    results_parser = subparsers.add_parser(
        "results",
        help="Manage test results",
        description="""
Commands for aggregating and managing test results.

This suite of tools handles the lifecycle of test results:
1. aggregate: Harvest raw .aider.results.json files from run directories.
2. clean: Identify and remove failed or malformed runs.
3. consolidate: Flatten and denormalize data into a CSV for analysis.
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    results_subparsers = results_parser.add_subparsers(
        dest="results_command", required=True
    )

    # Aggregate subcommand
    agg_parser = results_subparsers.add_parser(
        "aggregate",
        help="Aggregate test results from run directories",
        description="""
Scans a directory for test runs and aggregates individual test results.

Features:
- Discovery: Finds run directories matching 'YYYY-MM-DD-HH-MM-SS--*'.
- Extraction: Locates '.aider.results.json' files within runs.
- Enrichment:
    - Identifies tests via 'cat.yaml' (UUID/Hash).
    - Fallback to path-based lookup using 'cat/index.csv' for classic tests.
    - Adds 'cat_uuid' and 'cat_hash' to results.
- Output:
    - JSON files organized by 'results/MODEL/RUN/results.json'.
    - Summaries with pass/fail counts.
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_common_args(agg_parser)
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
Identifies and cleans up failed test runs.

Features:
- Detection: Finds runs with 100% rejected results (malformed JSON or missing keys).
- Scope: Scans both source run directories and aggregated output directories.
- Safety:
    - Default: Prints shell commands to delete failed runs (dry-run).
    - --interactive: Asks for confirmation before deleting.
    - --yolo: Deletes immediately without confirmation.
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_common_args(clean_parser)
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
    clean_parser.add_argument(
        "--yolo",
        action="store_true",
        help="Run the clean commands without confirmation",
    )
    clean_parser.add_argument(
        "--interactive",
        action="store_true",
        help="Ask for confirmation before running clean commands",
    )
    clean_parser.set_defaults(func=run_clean)

    # Consolidate subcommand
    consolidate_parser = results_subparsers.add_parser(
        "consolidate",
        help="Consolidate aggregated results into a single CSV",
        description="""
Merges aggregated results into a single, analysis-ready CSV file.

Data Transformations:
- Flattening: Denormalizes nested JSON into flat CSV columns.
- Outcomes: Converts boolean lists (e.g. [True, False]) to strings (e.g. "PF").
- Sets: Explodes 'sets' list into individual binary columns (e.g. 'set_polyglot=1').
- Validation:
    - Verifies UUIDs against the CAT index.
    - Checks for hash mismatches between result and index.
    - Adds a 'notes' column for any data integrity warnings.
- Metadata: Joins with 'cat/index.csv' to ensure language and other fields are present.
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_common_args(consolidate_parser)
    consolidate_parser.add_argument(
        "-r",
        "--results-dir",
        default="results",
        help="Directory containing aggregated results (default: results)",
    )
    consolidate_parser.add_argument(
        "-c",
        "--cats-dir",
        default="cat",
        help="Directory containing cat metadata and index.csv (default: cat)",
    )
    consolidate_parser.add_argument(
        "-o",
        "--out-file",
        default=DEFAULT_CONSOLIDATED_FILE,
        help=f"Output CSV file (default: {DEFAULT_CONSOLIDATED_FILE})",
    )
    consolidate_parser.set_defaults(func=run_consolidate)

    # Crosstab subcommand
    crosstab_parser = results_subparsers.add_parser(
        "crosstab",
        help="Analyze results with crosstabs",
        description="Load CSV and perform groupby aggregation.",
    )
    crosstab_parser.add_argument(
        "-i",
        "--input-file",
        default=DEFAULT_CONSOLIDATED_FILE,
        help=f"Path to the CSV file (default: {DEFAULT_CONSOLIDATED_FILE})",
    )
    crosstab_parser.add_argument(
        "--group-by", help="Comma-separated list of columns to group by"
    )
    crosstab_parser.add_argument(
        "--outcome", help="Comma-separated list of columns to calculate metrics for"
    )
    add_decimals_arg(crosstab_parser)
    add_common_args(crosstab_parser)
    crosstab_parser.set_defaults(func=run_crosstab)

    # Describe subcommand
    describe_parser = results_subparsers.add_parser(
        "describe",
        help="Show dataframe description",
        description="Print a general overview using df.describe().",
    )
    describe_parser.add_argument(
        "-i",
        "--input-file",
        default=DEFAULT_CONSOLIDATED_FILE,
        help=f"Path to the CSV file (default: {DEFAULT_CONSOLIDATED_FILE})",
    )
    add_decimals_arg(describe_parser)
    add_common_args(describe_parser)
    describe_parser.set_defaults(func=run_describe)
