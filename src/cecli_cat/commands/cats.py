from cecli_cat.commands import (
    cat_summary,
    polyglot,
    rehash_cats,
    reindex_cats,
)


def add_parser(subparsers):
    parser = subparsers.add_parser(
        "cats",
        help="Manage CATs",
        description="Commands for managing CATs (Cecli Atomic Tests).",
    )
    cats_subparsers = parser.add_subparsers(dest="cats_command", required=True)

    polyglot.add_parser(cats_subparsers)
    rehash_cats.add_parser(cats_subparsers)
    reindex_cats.add_parser(cats_subparsers)
    cat_summary.add_parser(cats_subparsers)
