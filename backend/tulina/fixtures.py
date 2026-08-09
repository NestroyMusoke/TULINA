from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from .models import Consumption, Facility, InventoryBatch, Product, Route, Vehicle

T = TypeVar("T", bound=BaseModel)


def _validated(model: type[T], row: dict[str, Any]) -> T:
    """Validate only contract fields while retaining source data separately."""
    selected = {name: row[name] for name in model.model_fields if name in row}
    return model.model_validate(selected)


@dataclass(frozen=True)
class FixtureData:
    raw: dict[str, Any]
    facilities: tuple[Facility, ...]
    products: tuple[Product, ...]
    batches: tuple[InventoryBatch, ...]
    consumption: tuple[Consumption, ...]
    routes: tuple[Route, ...]
    vehicles: tuple[Vehicle, ...]

    @property
    def scenario_date(self):
        from datetime import date

        return date.fromisoformat(self.raw["metadata"]["scenario_date"])

    @property
    def controls(self) -> dict[str, Any]:
        return self.raw["controls"]


def load_fixture(path: str | Path = "data/fixtures/tulina_source_pack_v2.json") -> FixtureData:
    source_path = Path(path)
    raw = json.loads(source_path.read_text(encoding="utf-8-sig"))
    if raw["metadata"]["contains_patient_data"] is not False:
        raise ValueError("Tulina refuses fixture packs containing patient data")
    if raw["metadata"]["contains_private_keys"] is not False:
        raise ValueError("Tulina refuses fixture packs containing private keys")
    if len(raw.get("relay_test_vectors", [])) != 9:
        raise ValueError("Canonical fixture pack must contain nine protocol test vectors")
    return FixtureData(
        raw=raw,
        facilities=tuple(_validated(Facility, row) for row in raw["facilities"]),
        products=tuple(_validated(Product, row) for row in raw["products"]),
        batches=tuple(_validated(InventoryBatch, row) for row in raw["private_inventory_batches"]),
        consumption=tuple(_validated(Consumption, row) for row in raw["private_consumption_history"]),
        routes=tuple(Route.model_validate(row) for row in raw["route_matrix_estimate"]),
        vehicles=tuple(_validated(Vehicle, row) for row in raw["vehicles"]),
    )


def fixture_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

