import "fake-indexeddb/auto";

import { base64urlDecode, encodeEnvelope } from "./codec";
import {
  cacheTrustBundle,
  getOrCreateDeviceIdentity,
  pendingReceipts,
  resetOfflineState,
  verifyAndQueueReceipt,
} from "./offlineStore";
import type { TrustBundle } from "./types";

const canonicalPayload = '{"v":1,"capsule_id":"CAP-TR027-001","transfer_id":"TR-027","issuer":"AGT-NETWORK-01","donor":"F01","recipient":"F02","product":"P05","batch":"BAT-F01-P05-01","qty":11,"approval":"APR-DHO-001","iat":"2026-08-15T14:05:00Z","exp":"2026-08-16T02:05:00Z","nonce":"n_7G4WQ3M8HX2V9K1P"}';
const note = encodeEnvelope("TULINA1", {
  key_id: "KEY-CAPSULE-v1",
  canonical_payload: canonicalPayload,
  signature_base64url: "npXN-I9XS6d5j3llfTglBgBTxStqmLmAc2msR73LuVStloGwsdjgjHW3LrfVN6exdCPqYjPU8jTm84R1kwPIqw",
});
const trustBundle: TrustBundle = {
  schema_version: "1.0",
  bundle_id: "TRUST-FIXTURE-v1",
  issued_at: "2026-08-15T08:00:00Z",
  expires_at: "2026-09-15T08:00:00Z",
  keys: [{
    key_id: "KEY-CAPSULE-v1",
    algorithm: "ECDSA_P256_SHA256",
    public_jwk: {
      kty: "EC",
      x: "vK141iBpR48aPGUVVEFzr65vzUHJ3I9JvoD1WeR2mzs",
      y: "cBwIQZOn-txlzrgWgVOeK78CXy2T9cpxYUCq4Xw4P6w",
      crv: "P-256",
    },
    fingerprint: "sha256:f8ca5765e46bda07db1dcc70669dbcebb047ea82d6e23d5b18058c714975d83e",
  }],
  source_label: "Synthetic cryptographic fixture",
};

describe("IndexedDB offline receipt queue", () => {
  beforeEach(async () => resetOfflineState());
  afterEach(async () => resetOfflineState());

  test("keeps the device private key non-exportable", async () => {
    const identity = await getOrCreateDeviceIdentity();
    expect(identity.privateKey.extractable).toBe(false);
    expect(identity.publicJwk).toMatchObject({ kty: "EC", crv: "P-256" });
    const reopened = await getOrCreateDeviceIdentity();
    expect(reopened.keyId).toBe("KEY-DEV-F02-01");
  });

  test("queues one signed receipt offline and blocks a local replay", async () => {
    await cacheTrustBundle(trustBundle);
    const first = await verifyAndQueueReceipt(note, new Date("2026-08-15T14:12:00Z"));
    expect(first.verification.decision).toBe("ACCEPT_OFFLINE");
    expect(first.receipt?.receiptId).toBe("RCP-TR027-001");
    expect(await pendingReceipts()).toHaveLength(1);

    const envelopeBytes = base64urlDecode(first.receipt!.receiptToken.split(".")[1]);
    const envelope = JSON.parse(new TextDecoder().decode(envelopeBytes));
    const identity = await getOrCreateDeviceIdentity();
    const validReceiptSignature = await crypto.subtle.verify(
      { name: "ECDSA", hash: "SHA-256" },
      identity.publicKey,
      base64urlDecode(envelope.device_signature_base64url),
      new TextEncoder().encode(envelope.canonical_receipt_payload),
    );
    expect(validReceiptSignature).toBe(true);

    const replay = await verifyAndQueueReceipt(note, new Date("2026-08-15T14:14:00Z"));
    expect(replay.verification.reason_code).toBe("NONCE_ALREADY_USED_LOCAL");
    expect(replay.receipt).toBeNull();
    expect(await pendingReceipts()).toHaveLength(1);
  });
});
