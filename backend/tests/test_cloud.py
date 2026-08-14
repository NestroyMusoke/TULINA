from __future__ import annotations

import base64
import unittest
from types import SimpleNamespace

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from fastapi.testclient import TestClient

from backend.tulina.agents.settings import AgentSettings
from backend.tulina.api import create_app
from backend.tulina.cloud.document_store import MemoryDocumentStore
from backend.tulina.cloud.firestore import FirestoreProtocolStore, FirestoreRepository
from backend.tulina.cloud.kms import CloudKmsP256Signer, _crc32c
from backend.tulina.engine import DomainEngine
from backend.tulina.fixtures import load_fixture
from backend.tulina.models import TransferStatus
from backend.tulina.protocol.crypto import verify_raw_signature
from backend.tulina.protocol.models import ReconciliationDecision, ReconciliationResult
from backend.tulina.state_machine import TransitionContext


class FakeKmsClient:
    def __init__(self, name: str):
        self.name = name
        self.private_key = ec.generate_private_key(ec.SECP256R1())

    def get_public_key(self, request):
        self.assert_name(request)
        pem = self.private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return SimpleNamespace(name=self.name, pem=pem)

    def asymmetric_sign(self, request):
        self.assert_name(request)
        digest = request["digest"]["sha256"]
        signature = self.private_key.sign(
            digest, ec.ECDSA(utils.Prehashed(hashes.SHA256()))
        )
        return SimpleNamespace(name=self.name, signature=signature)

    def assert_name(self, request):
        if request["name"] != self.name:
            raise AssertionError("unexpected key resource")


class FakePublishFuture:
    def result(self, timeout=None):
        return "message-1"


class FakePublisher:
    def __init__(self):
        self.published = []

    def topic_path(self, project_id: str, topic: str) -> str:
        return f"projects/{project_id}/topics/{topic}"

    def publish(self, topic_path: str, payload: bytes, **attributes):
        self.published.append((topic_path, payload, attributes))
        return FakePublishFuture()


class FirestoreRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DomainEngine(load_fixture("data/fixtures/tulina_source_pack_v2.json"))
        self.documents = MemoryDocumentStore()
        self.repository = FirestoreRepository(self.documents)
        self.repository.seed(self.engine.all_positions(), self.engine.recommendations())

    def test_firestore_transaction_applies_transfer_exactly_once_and_chains_audit(self) -> None:
        for status, role in (
            (TransferStatus.AWAITING_APPROVAL, "steward_agent"),
            (TransferStatus.APPROVED, "dho_approver"),
            (TransferStatus.NOTE_ISSUED, "dispatch_agent"),
            (TransferStatus.IN_TRANSIT, "dispatch_agent"),
        ):
            self.repository.change_status(
                "TR-027",
                status,
                TransitionContext(actor_id=role, actor_role=role, reason=f"to {status.value}"),
            )
        key = "TR-027|CAP-TR027-001|DEV-F02-01"
        context = TransitionContext(
            actor_id="reconciliation_agent",
            actor_role="reconciliation_agent",
            reason="verified delivery",
        )
        self.assertTrue(self.repository.apply_transfer_once("TR-027", key, context))
        self.assertFalse(self.repository.apply_transfer_once("TR-027", key, context))
        self.assertEqual(self.repository.get_position("F01", "P05").on_hand, 49)
        self.assertEqual(self.repository.get_position("F02", "P05").on_hand, 12)
        self.assertEqual(self.repository.mutation_count("TR-027"), 1)
        self.assertTrue(self.repository.verify_audit_chain())

    def test_firestore_protocol_results_and_resolution_are_durable(self) -> None:
        store = FirestoreProtocolStore(self.documents)
        result = ReconciliationResult(
            receipt_id="RCP-CONFLICT-001",
            capsule_id="CAP-TR027-001",
            transfer_id="TR-027",
            decision=ReconciliationDecision.QUARANTINE_CONFLICT,
            reason_code="STATE_CONFLICT",
            message="Needs human review",
            transfer_mutations_applied=0,
            pending_receipts=0,
        )
        store.save_result(result)
        self.assertEqual(store.unresolved_quarantined_count(), 1)
        resolved = store.resolve_quarantine(
            "RCP-CONFLICT-001", note="Reviewed with no mutation", resolved_by="DHO-001"
        )
        self.assertEqual(resolved.resolution, "ACKNOWLEDGE_NO_MUTATION")
        self.assertEqual(store.unresolved_quarantined_count(), 0)


class KmsAndPubSubTests(unittest.TestCase):
    key_name = (
        "projects/test-project/locations/us-central1/keyRings/tulina/"
        "cryptoKeys/tulina-note/cryptoKeyVersions/1"
    )

    def test_cloud_kms_signer_converts_der_to_browser_compatible_p256(self) -> None:
        signer = CloudKmsP256Signer(self.key_name, client=FakeKmsClient(self.key_name))
        message = '{"transfer_id":"TR-027"}'
        signature = signer.sign(message)
        self.assertTrue(verify_raw_signature(signer.jwk, message, signature))
        self.assertEqual(_crc32c(b"123456789"), 0xE3069283)

    def test_authenticated_pubsub_push_processes_the_durable_firestore_run(self) -> None:
        publisher = FakePublisher()
        documents = MemoryDocumentStore()
        settings = AgentSettings(
            _env_file=None,
            TULINA_MODE="fixture",
            TULINA_REPOSITORY="firestore",
            TULINA_QUEUE="pubsub",
            GOOGLE_CLOUD_PROJECT="test-project",
            TULINA_GCP_PROJECT="test-project",
            TULINA_PUBSUB_AUDIENCE="https://tulina-api.example.run.app",
            TULINA_PUBSUB_SERVICE_ACCOUNT="tulina-push@test-project.iam.gserviceaccount.com",
            TULINA_KMS_KEY_VERSION=self.key_name,
            TULINA_AGENT_STEP_DELAY_MS=0,
        )

        def verifier(token, request, audience):
            self.assertEqual(token, "valid-token")
            self.assertEqual(audience, "https://tulina-api.example.run.app")
            return {
                "email": "tulina-push@test-project.iam.gserviceaccount.com",
                "email_verified": True,
            }

        app = create_app(
            agent_settings=settings,
            document_store=documents,
            kms_client=FakeKmsClient(self.key_name),
            publisher=publisher,
            oidc_verifier=verifier,
        )
        client = TestClient(app)
        started = client.post(
            "/api/v1/agent-runs/watch",
            headers={"X-Tulina-Role": "facility_worker"},
            json={"trigger": "demo"},
        )
        self.assertEqual(started.status_code, 202)
        _, payload, attributes = publisher.published[0]
        envelope = {
            "message": {
                "data": base64.b64encode(payload).decode("ascii"),
                "messageId": "message-1",
                "attributes": attributes,
            },
            "subscription": "projects/test-project/subscriptions/tulina-agent-worker",
        }
        response = client.post(
            "/api/v1/internal/pubsub/agent-runs",
            headers={"Authorization": "Bearer valid-token"},
            json=envelope,
        )
        self.assertEqual(response.status_code, 204)
        detail = client.get(
            f"/api/v1/agent-runs/{started.json()['run']['run_id']}",
            headers={"X-Tulina-Role": "auditor"},
        ).json()
        self.assertEqual(detail["run"]["status"], "COMPLETED")
        self.assertEqual(len(detail["steps"]), 6)

        duplicate = client.post(
            "/api/v1/internal/pubsub/agent-runs",
            headers={"Authorization": "Bearer valid-token"},
            json=envelope,
        )
        self.assertEqual(duplicate.status_code, 204)

        unauthenticated = client.post(
            "/api/v1/internal/pubsub/agent-runs", json=envelope
        )
        self.assertEqual(unauthenticated.status_code, 401)


if __name__ == "__main__":
    unittest.main()
