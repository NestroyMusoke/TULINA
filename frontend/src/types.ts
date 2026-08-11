export type TransferStatus =
  | "FOUND"
  | "AWAITING_APPROVAL"
  | "APPROVED"
  | "NOTE_ISSUED"
  | "IN_TRANSIT"
  | "DELIVERED"
  | "NEEDS_REVIEW"
  | "CANCELLED";

export type DemoRole = "facility_worker" | "dho_approver" | "auditor";
export type AgentRunStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
export type AgentStepStatus = "RUNNING" | "COMPLETED" | "WAITING" | "FAILED";
export type StockCardIntakeStatus = "AWAITING_REVIEW" | "NEEDS_REVIEW" | "ACCEPTED" | "REJECTED";

export interface PolicyDecision {
  allowed: boolean;
  human_approval_required: boolean;
  checks: Record<string, boolean>;
  reasons: string[];
}

export interface RecommendationEvidence {
  donor_on_hand: number;
  donor_monthly_use: number;
  donor_cover_before_days: number;
  donor_cover_after_days: number;
  recipient_on_hand: number;
  recipient_monthly_use: number;
  recipient_cover_before_days: number;
  recipient_cover_after_days: number;
  route_km: number;
  route_minutes: number;
  expiry_date: string;
  projected_expiry_risk_avoided: number;
  score_components: Record<string, number>;
}

export interface Recommendation {
  schema_version: string;
  transfer_id: string;
  donor_facility_id: string;
  donor_name: string;
  donor_short_name: string;
  recipient_facility_id: string;
  recipient_name: string;
  recipient_short_name: string;
  product_id: string;
  product_name: string;
  batch_id: string;
  batch_number: string;
  quantity: number;
  transfer_unit: string;
  route_id: string;
  vehicle_id: string;
  approval_id: string;
  score: number;
  status: TransferStatus;
  source_label: string;
  evidence: RecommendationEvidence;
  policy: PolicyDecision;
  metrics: {
    transfer_id: string;
    recipient_cover_restored_days: number;
    donor_cover_retained_days: number;
    projected_expiry_risk_avoided: number;
    distance_km: number;
  };
}

export interface ActivityEvent {
  event_id: string;
  sequence: number;
  occurred_at: string;
  trace_id: string;
  actor_id: string;
  event_type: string;
  summary: string;
  event_hash: string;
  details: Record<string, unknown>;
}

export interface NetworkPosition {
  facility_id: string;
  facility_name: string;
  facility_short_name: string;
  product_id: string;
  product_name: string;
  on_hand: number;
  monthly_use: number;
  days_of_cover: number;
  target_quantity: number;
  safety_quantity: number;
  need_quantity: number;
  safe_release_quantity: number;
  state: "needs_stock" | "safe_surplus" | "covered";
}

export interface AgentStep {
  step_id: string;
  run_id: string;
  sequence: number;
  agent_name: string;
  tool_name: string;
  status: AgentStepStatus;
  summary: string;
  evidence: Record<string, unknown>;
  started_at: string;
  completed_at: string | null;
}

export interface AgentRun {
  run_id: string;
  workflow: "district_watch_cycle";
  status: AgentRunStatus;
  trace_id: string;
  requested_by: string;
  provider: "fixture" | "gemini";
  model_name: string | null;
  queue_backend: "local" | "pubsub";
  request: {
    schema_version: "1.0";
    recipient_facility_id: string;
    product_id: string;
    trigger: "demo" | "schedule" | "inventory_event";
  };
  result_transfer_id: string | null;
  event_authors: string[];
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface AgentRunDetail {
  run: AgentRun;
  steps: AgentStep[];
}

export interface EvidenceRegion {
  field: string;
  quote: string;
  confidence: number;
  bbox: [number, number, number, number];
}

export interface StockMovement {
  movement_date: string;
  reference: string;
  batch_number: string;
  expiry_date: string;
  received_packs: number;
  issued_packs: number;
  balance_packs: number;
  temperature_c: number;
  remarks: string;
}

export interface StockCardExtraction {
  schema_version: "1.0";
  facility_name: string;
  product_name: string;
  stock_unit: string;
  card_number: string;
  scenario_date: string;
  store_name: string;
  storage_min_c: number;
  storage_max_c: number;
  on_hand_packs: number;
  batch_number: string;
  expiry_date: string;
  latest_temperature_c: number;
  redistribution_review: boolean;
  movements: StockMovement[];
  evidence: EvidenceRegion[];
  overall_confidence: number;
}

export interface StockCardIntake {
  schema_version: "1.0";
  intake_id: string;
  trace_id: string;
  status: StockCardIntakeStatus;
  provider: "fixture" | "gemini";
  model_name: string | null;
  gemini_called: boolean;
  source_filename: string;
  mime_type: "image/png" | "image/jpeg";
  image_sha256: string;
  image_size_bytes: number;
  extraction: StockCardExtraction;
  observation: {
    facility_id: string;
    product_id: string;
    batch_id: string;
    extraction: StockCardExtraction;
  } | null;
  required_corrections: string[];
  corrections: Array<{
    field: string;
    previous_value: string;
    corrected_value: string;
    corrected_by: string;
    corrected_at: string;
  }>;
  source_label: string;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  accepted_by: string | null;
  accepted_at: string | null;
}

export type StockCardCorrection = Partial<
  Pick<
    StockCardExtraction,
    | "facility_name"
    | "product_name"
    | "stock_unit"
    | "card_number"
    | "scenario_date"
    | "store_name"
    | "storage_min_c"
    | "storage_max_c"
    | "on_hand_packs"
    | "batch_number"
    | "expiry_date"
    | "latest_temperature_c"
    | "redistribution_review"
  >
>;

export interface Overview {
  recommendation: Recommendation;
  activity: ActivityEvent[];
  network: NetworkPosition[];
  agent_run: AgentRunDetail | null;
  stock_card_intake: StockCardIntake | null;
  synthetic_data: boolean;
  scenario_date: string;
}
