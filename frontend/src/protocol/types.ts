export interface PublicKeyRecord {
  key_id: string;
  algorithm: "ECDSA_P256_SHA256";
  public_jwk: JsonWebKey;
  fingerprint: string;
}

export interface TrustBundle {
  schema_version: "1.0";
  bundle_id: string;
  issued_at: string;
  expires_at: string;
  keys: PublicKeyRecord[];
  source_label: string;
}

export interface NotePayload {
  v: 1;
  capsule_id: string;
  transfer_id: string;
  issuer: string;
  donor: string;
  recipient: string;
  product: string;
  batch: string;
  qty: number;
  approval: string;
  iat: string;
  exp: string;
  nonce: string;
}

export interface SignedTulinaNote {
  schema_version: "1.0";
  key_id: string;
  canonical_payload: string;
  signature_base64url: string;
  qr_payload: string;
  payload: NotePayload;
  signature_format: "IEEE_P1363_64_BYTE";
  source_label: string;
}

export interface OfflineVerification {
  decision: "ACCEPT_OFFLINE" | "REJECT_OFFLINE";
  reason_code: string;
  message: string;
  checks: {
    parse: "PASS" | "FAIL" | "NOT_EVALUATED";
    key: "PASS" | "FAIL" | "NOT_EVALUATED";
    signature: "PASS" | "FAIL" | "NOT_EVALUATED";
    recipient: "PASS" | "FAIL" | "NOT_EVALUATED";
    expiry: "PASS" | "FAIL" | "NOT_EVALUATED";
    nonce: "PASS" | "FAIL" | "NOT_EVALUATED";
  };
  payload?: NotePayload;
}

export interface DeviceIdentity {
  deviceId: "DEV-F02-01";
  facilityId: "F02";
  keyId: "KEY-DEV-F02-01";
  publicKey: CryptoKey;
  privateKey: CryptoKey;
  publicJwk: JsonWebKey;
}

export interface QueuedReceipt {
  receiptId: string;
  capsuleId: string;
  receiptToken: string;
  state: "PENDING" | "ACKNOWLEDGED" | "QUARANTINED" | "REJECTED";
  queuedAt: string;
  result?: ReconciliationResult;
}

export interface ReconciliationResult {
  schema_version: "1.0";
  receipt_id: string | null;
  capsule_id: string | null;
  transfer_id: string | null;
  decision: "APPLIED_EXACTLY_ONCE" | "IDEMPOTENT_ACK" | "QUARANTINE_CONFLICT" | "REJECTED";
  reason_code: string;
  message: string;
  transfer_mutations_applied: number;
  pending_receipts: number;
  inventory_before: { donor: number; recipient: number } | null;
  inventory_after: { donor: number; recipient: number } | null;
}

export interface OfflineState {
  verification: OfflineVerification | null;
  pendingCount: number;
  latestReceipt: QueuedReceipt | null;
  latestResult: ReconciliationResult | null;
}
