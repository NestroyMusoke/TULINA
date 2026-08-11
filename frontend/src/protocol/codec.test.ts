import { decodeNote, encodeEnvelope, verifyNoteOffline } from "./codec";
import type { TrustBundle } from "./types";

const canonicalPayload = '{"v":1,"capsule_id":"CAP-TR027-001","transfer_id":"TR-027","issuer":"AGT-NETWORK-01","donor":"F01","recipient":"F02","product":"P05","batch":"BAT-F01-P05-01","qty":11,"approval":"APR-DHO-001","iat":"2026-08-15T14:05:00Z","exp":"2026-08-16T02:05:00Z","nonce":"n_7G4WQ3M8HX2V9K1P"}';
const signature = "npXN-I9XS6d5j3llfTglBgBTxStqmLmAc2msR73LuVStloGwsdjgjHW3LrfVN6exdCPqYjPU8jTm84R1kwPIqw";
const note = encodeEnvelope("TULINA1", {
  key_id: "KEY-CAPSULE-v1",
  canonical_payload: canonicalPayload,
  signature_base64url: signature,
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

describe("offline Tulina Note verification", () => {
  test("accepts the preserved P-256 fixture without a network request", async () => {
    const result = await verifyNoteOffline({
      token: note,
      trustBundle,
      facilityId: "F02",
      scannedAt: new Date("2026-08-15T14:12:00Z"),
    });
    expect(result.decision).toBe("ACCEPT_OFFLINE");
    expect(result.message).toBe("Safe to receive");
    expect(result.checks).toEqual({
      parse: "PASS", key: "PASS", signature: "PASS", recipient: "PASS", expiry: "PASS", nonce: "PASS",
    });
  });

  test("rejects changed quantity under the original signature", async () => {
    const tampered = encodeEnvelope("TULINA1", {
      key_id: "KEY-CAPSULE-v1",
      canonical_payload: canonicalPayload.replace('"qty":11', '"qty":17'),
      signature_base64url: signature,
    });
    const result = await verifyNoteOffline({
      token: tampered,
      trustBundle,
      facilityId: "F02",
      scannedAt: new Date("2026-08-15T14:13:00Z"),
    });
    expect(result.reason_code).toBe("SIGNATURE_INVALID");
    expect(result.checks.signature).toBe("FAIL");
  });

  test.each([
    ["local replay", { nonceConsumed: true }, "NONCE_ALREADY_USED_LOCAL"],
    ["wrong facility", { facilityId: "F03" }, "RECIPIENT_MISMATCH"],
    ["expired note", { scannedAt: new Date("2026-08-16T02:06:00Z") }, "NOTE_EXPIRED"],
  ])("rejects %s", async (_name, override, expected) => {
    const result = await verifyNoteOffline({
      token: note,
      trustBundle,
      facilityId: "F02",
      scannedAt: new Date("2026-08-15T14:14:00Z"),
      ...override,
    });
    expect(result.reason_code).toBe(expected);
  });

  test("rejects unknown issuer before signature evaluation", async () => {
    const decoded = decodeNote(note);
    const rogue = encodeEnvelope("TULINA1", {
      key_id: "KEY-ROGUE-v1",
      canonical_payload: decoded.canonicalPayload,
      signature_base64url: decoded.signature,
    });
    const result = await verifyNoteOffline({
      token: rogue,
      trustBundle,
      facilityId: "F02",
      scannedAt: new Date("2026-08-15T14:13:45Z"),
    });
    expect(result.reason_code).toBe("ISSUER_KEY_NOT_TRUSTED");
    expect(result.checks.signature).toBe("NOT_EVALUATED");
  });

  test("rejects malformed QR data at the parse gate", async () => {
    const result = await verifyNoteOffline({
      token: "TULINA1.not-valid-base64",
      trustBundle,
      facilityId: "F02",
    });
    expect(result.reason_code).toBe("PAYLOAD_UNREADABLE");
    expect(result.checks.parse).toBe("FAIL");
  });
});
