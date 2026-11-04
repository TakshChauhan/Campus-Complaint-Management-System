"""Exercise the PostgreSQL migration chain and rolling upgrade/rollback flow."""

from __future__ import annotations

import argparse
import os

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def migration_targets(config: Config) -> list[str]:
    script = ScriptDirectory.from_config(config)
    all_revisions = list(script.walk_revisions())
    bases = [revision for revision in all_revisions if revision.down_revision is None]
    if len(bases) != 1:
        raise RuntimeError(f"Expected one base migration, found {len(bases)}")
    base = bases[0]
    revisions = list(reversed(list(script.iterate_revisions("head", base.revision))))
    targets = [base.revision, *(revision.revision for revision in revisions)]
    if not targets or not targets[0].startswith("0001"):
        raise RuntimeError(f"Expected migration chain to start at 0001, got {targets[:1]}")
    return targets


def run_flow(database_url: str) -> None:
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    config = Config(os.path.join(backend_dir, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    targets = migration_targets(config)
    initial = targets[0]
    head = targets[-1]
    print(f"Migration chain: {' -> '.join(targets)}")

    print(f"Upgrade {initial} -> {head}")
    command.upgrade(config, "head")
    print(f"Downgrade {head} -> {initial}")
    command.downgrade(config, initial)

    current_index = 0
    while current_index < len(targets) - 1:
        next_index = min(current_index + 3, len(targets) - 1)
        next_target = targets[next_index]
        print(f"Upgrade {targets[current_index]} -> {next_target}")
        command.upgrade(config, next_target)

        if next_index == len(targets) - 1:
            break

        rollback_index = next_index - 1
        rollback_target = targets[rollback_index]
        print(f"Downgrade {next_target} -> {rollback_target}")
        command.downgrade(config, rollback_target)
        current_index = rollback_index

    print(f"Migration flow completed at {head}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()
    if not args.db_url:
        parser.error("--db-url or DATABASE_URL is required")
    run_flow(args.db_url)
