import argparse
import csv
import logging
import yaml
from pathlib import Path


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
    out_file = Path(args.out_file)

    if not in_dir.exists():
        logger.error(f"Input directory '{in_dir}' does not exist.")
        return

    logger.info(f"Scanning {in_dir} for cat.yaml files...")

    records = []
    # Find all cat.yaml files
    for cat_file in in_dir.rglob("cat.yaml"):
        try:
            with open(cat_file, "r") as f:
                data = yaml.safe_load(f) or {}
                data["path"] = str(cat_file.parent)
                records.append(data)
        except Exception as e:
            logger.warning(f"Failed to read {cat_file}: {e}")

    if not records:
        logger.warning("No records found.")
        return

    # Determine fieldnames from all keys in all records
    fieldnames = set()
    for record in records:
        fieldnames.update(record.keys())

    # Sort fieldnames for consistency
    priority_fields = ["name", "uuid", "hash", "language", "sets", "source", "path"]
    sorted_fieldnames = [f for f in priority_fields if f in fieldnames]
    sorted_fieldnames.extend(sorted(list(fieldnames - set(priority_fields))))

    logger.info(f"Writing {len(records)} records to {out_file}...")

    # Ensure output directory exists
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sorted_fieldnames)
        writer.writeheader()
        for record in records:
            # Handle list fields (like sets)
            row = record.copy()
            if "sets" in row and isinstance(row["sets"], list):
                row["sets"] = ";".join(str(x) for x in row["sets"])
            writer.writerow(row)

    logger.info("Done.")


def add_parser(subparsers):
    parser = subparsers.add_parser(
        "reindex_cats",
        help="Collate cat.yaml files into a CSV index",
        description="""
        Scans the input directory (recursively) for cat.yaml files, reads their content,
        and writes a consolidated CSV index file.
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
        default="cat",
        help="Input directory to scan (default: cat)",
    )
    parser.add_argument(
        "-o",
        "--out-file",
        default="cat/index.csv",
        help="Output CSV file path (default: cat/index.csv)",
    )
    parser.set_defaults(func=run)
