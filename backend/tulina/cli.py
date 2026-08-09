from __future__ import annotations

import argparse
import json

from .engine import DomainEngine
from .fixtures import load_fixture
from .metrics import metrics_for
from .repository import SQLiteRepository


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Tulina deterministic domain utilities")
    cli.add_argument("command", choices=("recommend", "seed"))
    cli.add_argument("--fixture", default="data/fixtures/tulina_source_pack_v2.json")
    cli.add_argument("--database", default="data/runtime/tulina.sqlite3")
    cli.add_argument("--reset", action="store_true")
    return cli


def main() -> None:
    args = parser().parse_args()
    engine = DomainEngine(load_fixture(args.fixture))
    recommendations = engine.recommendations()
    if args.command == "recommend":
        print(
            json.dumps(
                [
                    {
                        "recommendation": item.model_dump(mode="json"),
                        "metrics": metrics_for(item).model_dump(mode="json"),
                    }
                    for item in recommendations
                ],
                indent=2,
            )
        )
        return
    repository = SQLiteRepository(args.database)
    repository.seed(engine.all_positions(), recommendations, reset=args.reset)
    print(
        json.dumps(
            {
                "database": args.database,
                "positions": len(engine.all_positions()),
                "recommendations": len(repository.list_transfers()),
                "audit_chain_valid": repository.verify_audit_chain(),
            },
            indent=2,
        )
    )
    repository.close()


if __name__ == "__main__":
    main()
