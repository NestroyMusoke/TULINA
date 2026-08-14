from __future__ import annotations

import copy
import re
import threading
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

T = TypeVar("T")
Filter = tuple[str, str, object]
Order = tuple[str, str]


class DocumentTransaction(Protocol):
    def get(self, collection: str, document_id: str) -> dict[str, object] | None: ...
    def set(
        self,
        collection: str,
        document_id: str,
        value: dict[str, object],
        *,
        merge: bool = False,
    ) -> None: ...
    def delete(self, collection: str, document_id: str) -> None: ...


class DocumentStore(DocumentTransaction, Protocol):
    backend_name: str
    namespace: str

    def list(
        self,
        collection: str,
        *,
        filters: tuple[Filter, ...] = (),
        order: tuple[Order, ...] = (),
        limit: int | None = None,
    ) -> tuple[dict[str, object], ...]: ...
    def run_transaction(self, operation: Callable[[DocumentTransaction], T]) -> T: ...
    def delete_all(self, collection: str) -> int: ...
    def ping(self) -> bool: ...


def _validate_namespace(value: str) -> str:
    normalized = value.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,30}", normalized):
        raise ValueError(
            "TULINA_FIRESTORE_NAMESPACE must be 3-31 lowercase letters, digits, or hyphens"
        )
    return normalized


class _GoogleTransaction:
    def __init__(self, owner: GoogleFirestoreDocumentStore, transaction: Any):
        self.owner = owner
        self.transaction = transaction

    def get(self, collection: str, document_id: str) -> dict[str, object] | None:
        snapshot = self.owner._document(collection, document_id).get(
            transaction=self.transaction
        )
        return snapshot.to_dict() if snapshot.exists else None

    def set(
        self,
        collection: str,
        document_id: str,
        value: dict[str, object],
        *,
        merge: bool = False,
    ) -> None:
        self.transaction.set(
            self.owner._document(collection, document_id), value, merge=merge
        )

    def delete(self, collection: str, document_id: str) -> None:
        self.transaction.delete(self.owner._document(collection, document_id))


class GoogleFirestoreDocumentStore:
    """Small Firestore boundary that keeps environment data under one root document."""

    backend_name = "firestore"

    def __init__(
        self,
        *,
        project_id: str,
        namespace: str = "tulina-demo",
        database: str = "(default)",
        client: Any = None,
    ):
        self.namespace = _validate_namespace(namespace)
        if client is None:
            from google.cloud import firestore

            client = firestore.Client(project=project_id, database=database)
        self.client = client
        self.root = client.collection("tulina_environments").document(self.namespace)

    def _collection(self, name: str):
        return self.root.collection(name)

    def _document(self, collection: str, document_id: str):
        return self._collection(collection).document(document_id)

    def get(self, collection: str, document_id: str) -> dict[str, object] | None:
        snapshot = self._document(collection, document_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def set(
        self,
        collection: str,
        document_id: str,
        value: dict[str, object],
        *,
        merge: bool = False,
    ) -> None:
        self._document(collection, document_id).set(value, merge=merge)

    def delete(self, collection: str, document_id: str) -> None:
        self._document(collection, document_id).delete()

    def list(
        self,
        collection: str,
        *,
        filters: tuple[Filter, ...] = (),
        order: tuple[Order, ...] = (),
        limit: int | None = None,
    ) -> tuple[dict[str, object], ...]:
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self._collection(collection)
        for field, operator, value in filters:
            query = query.where(filter=FieldFilter(field, operator, value))
        for field, direction in order:
            firestore_direction = (
                firestore.Query.DESCENDING
                if direction.lower() == "desc"
                else firestore.Query.ASCENDING
            )
            query = query.order_by(field, direction=firestore_direction)
        if limit is not None:
            query = query.limit(limit)
        return tuple(snapshot.to_dict() for snapshot in query.stream())

    def run_transaction(self, operation: Callable[[DocumentTransaction], T]) -> T:
        from google.cloud import firestore

        transaction = self.client.transaction(max_attempts=5)

        @firestore.transactional
        def invoke(inner_transaction):
            return operation(_GoogleTransaction(self, inner_transaction))

        return invoke(transaction)

    def delete_all(self, collection: str) -> int:
        deleted = 0
        while True:
            snapshots = tuple(self._collection(collection).limit(200).stream())
            if not snapshots:
                return deleted
            batch = self.client.batch()
            for snapshot in snapshots:
                batch.delete(snapshot.reference)
            batch.commit()
            deleted += len(snapshots)

    def ping(self) -> bool:
        self.root.get()
        return True


class _MemoryTransaction:
    def __init__(self, data: dict[str, dict[str, dict[str, object]]]):
        self.data = data

    def get(self, collection: str, document_id: str) -> dict[str, object] | None:
        value = self.data.get(collection, {}).get(document_id)
        return copy.deepcopy(value) if value is not None else None

    def set(
        self,
        collection: str,
        document_id: str,
        value: dict[str, object],
        *,
        merge: bool = False,
    ) -> None:
        target = self.data.setdefault(collection, {})
        if merge and document_id in target:
            target[document_id] = {**target[document_id], **copy.deepcopy(value)}
        else:
            target[document_id] = copy.deepcopy(value)

    def delete(self, collection: str, document_id: str) -> None:
        self.data.get(collection, {}).pop(document_id, None)


class MemoryDocumentStore(_MemoryTransaction):
    """Deterministic transaction double for cloud adapter tests; never used as GCP state."""

    backend_name = "memory-firestore"

    def __init__(self, namespace: str = "tulina-test"):
        self.namespace = _validate_namespace(namespace)
        self._data: dict[str, dict[str, dict[str, object]]] = {}
        self._lock = threading.RLock()
        super().__init__(self._data)

    def list(
        self,
        collection: str,
        *,
        filters: tuple[Filter, ...] = (),
        order: tuple[Order, ...] = (),
        limit: int | None = None,
    ) -> tuple[dict[str, object], ...]:
        with self._lock:
            values = [copy.deepcopy(value) for value in self._data.get(collection, {}).values()]
        for field, operator, expected in filters:
            if operator != "==":
                raise ValueError(f"MemoryDocumentStore does not implement filter {operator}")
            values = [value for value in values if value.get(field) == expected]
        for field, direction in reversed(order):
            values.sort(key=lambda value: value.get(field), reverse=direction.lower() == "desc")
        if limit is not None:
            values = values[:limit]
        return tuple(values)

    def run_transaction(self, operation: Callable[[DocumentTransaction], T]) -> T:
        with self._lock:
            staging = copy.deepcopy(self._data)
            result = operation(_MemoryTransaction(staging))
            self._data.clear()
            self._data.update(staging)
            self.data = self._data
            return result

    def delete_all(self, collection: str) -> int:
        with self._lock:
            count = len(self._data.get(collection, {}))
            self._data[collection] = {}
            return count

    def ping(self) -> bool:
        return True
