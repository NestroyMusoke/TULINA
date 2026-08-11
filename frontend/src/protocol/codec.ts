import { z } from "zod";

import type { NotePayload, OfflineVerification, TrustBundle } from "./types";

const notePayloadSchema = z.object({
  v: z.literal(1),
  capsule_id: z.string().startsWith("CAP-"),
  transfer_id: z.string().regex(/^TR-\d{3}$/),
  issuer: z.string().min(1),
  donor: z.string().regex(/^F\d{2}$/),
  recipient: z.string().regex(/^F\d{2}$/),
  product: z.string().regex(/^P\d{2}$/),
  batch: z.string().startsWith("BAT-"),
  qty: z.number().int().positive(),
  approval: z.string().startsWith("APR-"),
  iat: z.string().datetime(),
  exp: z.string().datetime(),
  nonce: z.string().min(12).max(128),
}).strict();

const envelopeSchema = z.object({
  key_id: z.string().min(1),
  canonical_payload: z.string().min(2),
  signature_base64url: z.string().min(80).max(96),
}).strict();

const skipped = "NOT_EVALUATED" as const;

export function base64urlEncode(value: ArrayBuffer | Uint8Array): string {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
}

export function base64urlDecode(value: string): Uint8Array {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "="));
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

export function encodeEnvelope(prefix: string, value: Record<string, unknown>): string {
  return `${prefix}.${base64urlEncode(new TextEncoder().encode(JSON.stringify(value)))}`;
}

export function decodeNote(token: string): {
  keyId: string;
  canonicalPayload: string;
  signature: string;
  payload: NotePayload;
} {
  if (!token.startsWith("TULINA1.")) throw new Error("Unsupported note format");
  const encoded = token.slice("TULINA1.".length);
  const envelope = envelopeSchema.parse(JSON.parse(new TextDecoder().decode(base64urlDecode(encoded))));
  const payload = notePayloadSchema.parse(JSON.parse(envelope.canonical_payload));
  return {
    keyId: envelope.key_id,
    canonicalPayload: envelope.canonical_payload,
    signature: envelope.signature_base64url,
    payload,
  };
}

function rejected(
  reasonCode: string,
  message: string,
  checks: OfflineVerification["checks"],
  payload?: NotePayload,
): OfflineVerification {
  return { decision: "REJECT_OFFLINE", reason_code: reasonCode, message, checks, payload };
}

export async function verifyNoteOffline(options: {
  token: string;
  trustBundle: TrustBundle;
  facilityId: string;
  scannedAt?: Date;
  nonceConsumed?: boolean;
}): Promise<OfflineVerification> {
  let decoded: ReturnType<typeof decodeNote>;
  try {
    decoded = decodeNote(options.token);
  } catch {
    return rejected("PAYLOAD_UNREADABLE", "Rejected — unreadable Tulina Note", {
      parse: "FAIL", key: skipped, signature: skipped, recipient: skipped, expiry: skipped, nonce: skipped,
    });
  }
  const key = options.trustBundle.keys.find((candidate) => candidate.key_id === decoded.keyId);
  const scannedAt = options.scannedAt ?? new Date();
  if (!key || scannedAt > new Date(options.trustBundle.expires_at)) {
    return rejected("ISSUER_KEY_NOT_TRUSTED", "Rejected — issuer not trusted", {
      parse: "PASS", key: "FAIL", signature: skipped, recipient: skipped, expiry: skipped, nonce: skipped,
    }, decoded.payload);
  }
  let signatureValid = false;
  try {
    const publicKey = await crypto.subtle.importKey(
      "jwk",
      key.public_jwk,
      { name: "ECDSA", namedCurve: "P-256" },
      false,
      ["verify"],
    );
    signatureValid = await crypto.subtle.verify(
      { name: "ECDSA", hash: "SHA-256" },
      publicKey,
      base64urlDecode(decoded.signature),
      new TextEncoder().encode(decoded.canonicalPayload),
    );
  } catch {
    signatureValid = false;
  }
  if (!signatureValid) {
    return rejected("SIGNATURE_INVALID", "Rejected — signature invalid", {
      parse: "PASS", key: "PASS", signature: "FAIL", recipient: skipped, expiry: skipped, nonce: skipped,
    }, decoded.payload);
  }
  const recipientValid = decoded.payload.recipient === options.facilityId;
  const expiryValid = scannedAt >= new Date(decoded.payload.iat) && scannedAt <= new Date(decoded.payload.exp);
  const nonceValid = !options.nonceConsumed;
  const checks: OfflineVerification["checks"] = {
    parse: "PASS",
    key: "PASS",
    signature: "PASS",
    recipient: recipientValid ? "PASS" : "FAIL",
    expiry: expiryValid ? "PASS" : "FAIL",
    nonce: nonceValid ? "PASS" : "FAIL",
  };
  if (!recipientValid) return rejected("RECIPIENT_MISMATCH", "Rejected — wrong receiving facility", checks, decoded.payload);
  if (!expiryValid) return rejected("NOTE_EXPIRED", "Rejected — authorization expired", checks, decoded.payload);
  if (!nonceValid) return rejected("NONCE_ALREADY_USED_LOCAL", "Rejected — Tulina Note already used", checks, decoded.payload);
  return {
    decision: "ACCEPT_OFFLINE",
    reason_code: "OK_QUEUED",
    message: "Safe to receive",
    checks,
    payload: decoded.payload,
  };
}

export function canonicalReceipt(value: {
  receipt_id: string;
  capsule_id: string;
  device_id: string;
  received_at: string;
  local_sequence: number;
}): string {
  return JSON.stringify({
    receipt_id: value.receipt_id,
    capsule_id: value.capsule_id,
    device_id: value.device_id,
    decision: "RECEIVED",
    received_at: value.received_at,
    local_sequence: value.local_sequence,
  });
}
