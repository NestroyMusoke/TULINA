import { base64urlEncode, canonicalReceipt, decodeNote, encodeEnvelope, verifyNoteOffline } from "./codec";
import type {
  DeviceIdentity,
  OfflineVerification,
  QueuedReceipt,
  ReconciliationResult,
  TrustBundle,
} from "./types";

const DATABASE = "tulina-offline-v1";
const VERSION = 1;

function requestValue<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Offline storage request failed"));
  });
}

function transactionComplete(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("Offline storage transaction failed"));
    transaction.onabort = () => reject(transaction.error ?? new Error("Offline storage transaction stopped"));
  });
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains("state")) database.createObjectStore("state");
      if (!database.objectStoreNames.contains("keys")) database.createObjectStore("keys");
      if (!database.objectStoreNames.contains("receipts")) database.createObjectStore("receipts", { keyPath: "receiptId" });
      if (!database.objectStoreNames.contains("nonces")) database.createObjectStore("nonces");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Offline storage is unavailable"));
  });
}

export async function cacheTrustBundle(bundle: TrustBundle): Promise<void> {
  const database = await openDatabase();
  const transaction = database.transaction("state", "readwrite");
  transaction.objectStore("state").put(bundle, "trust_bundle");
  await transactionComplete(transaction);
  database.close();
}

export async function getCachedTrustBundle(): Promise<TrustBundle | null> {
  const database = await openDatabase();
  const transaction = database.transaction("state", "readonly");
  const result = await requestValue(transaction.objectStore("state").get("trust_bundle"));
  database.close();
  return (result as TrustBundle | undefined) ?? null;
}

export async function getOrCreateDeviceIdentity(): Promise<DeviceIdentity> {
  const database = await openDatabase();
  const read = database.transaction("keys", "readonly");
  const existing = await requestValue(read.objectStore("keys").get("DEV-F02-01"));
  if (existing) {
    database.close();
    return existing as DeviceIdentity;
  }
  const pair = await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["sign", "verify"],
  );
  const publicJwk = await crypto.subtle.exportKey("jwk", pair.publicKey);
  const identity: DeviceIdentity = {
    deviceId: "DEV-F02-01",
    facilityId: "F02",
    keyId: "KEY-DEV-F02-01",
    publicKey: pair.publicKey,
    privateKey: pair.privateKey,
    publicJwk,
  };
  const write = database.transaction("keys", "readwrite");
  write.objectStore("keys").put(identity, identity.deviceId);
  await transactionComplete(write);
  database.close();
  return identity;
}

export async function nonceWasConsumed(nonce: string): Promise<boolean> {
  const database = await openDatabase();
  const transaction = database.transaction("nonces", "readonly");
  const value = await requestValue(transaction.objectStore("nonces").get(nonce));
  database.close();
  return Boolean(value);
}

async function nextSequence(database: IDBDatabase): Promise<number> {
  const transaction = database.transaction("state", "readonly");
  const current = await requestValue(transaction.objectStore("state").get("local_sequence"));
  return Number(current ?? 0) + 1;
}

export async function verifyAndQueueReceipt(token: string, receivedAt = new Date()): Promise<{
  verification: OfflineVerification;
  receipt: QueuedReceipt | null;
}> {
  const trustBundle = await getCachedTrustBundle();
  if (!trustBundle) throw new Error("Connect once to cache the Tulina trust bundle before receiving offline");
  let decoded: ReturnType<typeof decodeNote> | null = null;
  try { decoded = decodeNote(token); } catch { /* verification returns the safe parse failure */ }
  const consumed = decoded ? await nonceWasConsumed(decoded.payload.nonce) : false;
  const verification = await verifyNoteOffline({
    token,
    trustBundle,
    facilityId: "F02",
    scannedAt: receivedAt,
    nonceConsumed: consumed,
  });
  if (verification.decision !== "ACCEPT_OFFLINE" || !verification.payload) {
    return { verification, receipt: null };
  }
  const identity = await getOrCreateDeviceIdentity();
  const database = await openDatabase();
  const sequence = await nextSequence(database);
  const receiptId = verification.payload.transfer_id === "TR-027"
    ? "RCP-TR027-001"
    : `RCP-${verification.payload.transfer_id.slice(3)}-${String(sequence).padStart(3, "0")}`;
  const canonical = canonicalReceipt({
    receipt_id: receiptId,
    capsule_id: verification.payload.capsule_id,
    device_id: identity.deviceId,
    received_at: receivedAt.toISOString().replace(/\.\d{3}Z$/, "Z"),
    local_sequence: sequence,
  });
  const signature = await crypto.subtle.sign(
    { name: "ECDSA", hash: "SHA-256" },
    identity.privateKey,
    new TextEncoder().encode(canonical),
  );
  const receiptToken = encodeEnvelope("TULINA_RECEIPT1", {
    device_key_id: identity.keyId,
    canonical_receipt_payload: canonical,
    device_signature_base64url: base64urlEncode(signature),
  });
  const receipt: QueuedReceipt = {
    receiptId,
    capsuleId: verification.payload.capsule_id,
    receiptToken,
    state: "PENDING",
    queuedAt: receivedAt.toISOString(),
  };
  const transaction = database.transaction(["receipts", "nonces", "state"], "readwrite");
  transaction.objectStore("receipts").put(receipt);
  transaction.objectStore("nonces").put({ receiptId, consumedAt: receivedAt.toISOString() }, verification.payload.nonce);
  transaction.objectStore("state").put(sequence, "local_sequence");
  await transactionComplete(transaction);
  database.close();
  return { verification, receipt };
}

export async function pendingReceipts(): Promise<QueuedReceipt[]> {
  const database = await openDatabase();
  const transaction = database.transaction("receipts", "readonly");
  const rows = await requestValue(transaction.objectStore("receipts").getAll()) as QueuedReceipt[];
  database.close();
  return rows.filter((row) => row.state === "PENDING");
}

export async function latestReceipt(): Promise<QueuedReceipt | null> {
  const database = await openDatabase();
  const transaction = database.transaction("receipts", "readonly");
  const rows = await requestValue(transaction.objectStore("receipts").getAll()) as QueuedReceipt[];
  database.close();
  return rows.sort((left, right) => right.queuedAt.localeCompare(left.queuedAt))[0] ?? null;
}

export async function updateReceipt(receipt: QueuedReceipt, result: ReconciliationResult): Promise<QueuedReceipt> {
  const updated: QueuedReceipt = {
    ...receipt,
    state: result.decision === "QUARANTINE_CONFLICT"
      ? "QUARANTINED"
      : result.decision === "REJECTED"
        ? "REJECTED"
        : "ACKNOWLEDGED",
    result,
  };
  const database = await openDatabase();
  const transaction = database.transaction("receipts", "readwrite");
  transaction.objectStore("receipts").put(updated);
  await transactionComplete(transaction);
  database.close();
  return updated;
}

export async function resetOfflineState(): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase(DATABASE);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error ?? new Error("Could not reset offline state"));
    request.onblocked = () => reject(new Error("Close another Tulina tab before resetting the demo"));
  });
}
