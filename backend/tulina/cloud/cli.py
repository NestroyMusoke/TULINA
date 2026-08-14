from __future__ import annotations

import argparse
import json

from ..engine import DomainEngine
from ..fixtures import load_fixture
from .document_store import GoogleFirestoreDocumentStore
from .firestore import FirestoreRepository


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Seed or inspect a Tulina Firestore environment using ADC"
    )
    value.add_argument("command", choices=("seed", "status"))
    value.add_argument("--project", required=True)
    value.add_argument("--database", default="(default)")
    value.add_argument("--namespace", default="tulina-demo")
    value.add_argument(
        "--fixture", default="data/fixtures/tulina_source_pack_v2.json"
    )
    value.add_argument("--reset", action="store_true")
    value.add_argument("--confirm-namespace")
    return value


def main() -> None:
    args = parser().parse_args()
    if args.reset and args.command != "seed":
        raise SystemExit("--reset is valid only with the seed command")
    if args.reset and args.confirm_namespace != args.namespace:
        raise SystemExit(
            "A cloud reset requires --confirm-namespace with the exact namespace value"
        )
    documents = GoogleFirestoreDocumentStore(
        project_id=args.project,
        database=args.database,
        namespace=args.namespace,
    )
    repository = FirestoreRepository(documents)
    if args.command == "seed":
        engine = DomainEngine(load_fixture(args.fixture))
        repository.seed(
            engine.all_positions(), engine.recommendations(), reset=args.reset
        )
    transfer = repository.get_transfer("TR-027")
    print(
        json.dumps(
            {
                "backend": repository.backend_name,
                "project": args.project,
                "database": args.database,
                "namespace": args.namespace,
                "transfer_id": transfer.transfer_id,
                "status": transfer.status.value,
                "audit": repository.audit_status(),
                "synthetic_data": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
