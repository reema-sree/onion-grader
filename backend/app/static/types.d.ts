/**
 * Kisan Setu - TypeScript Type Definitions
 * Matches /docs/api-schema.md specification.
 */

export type UserRole = "farmer" | "csc" | "staff" | "admin";

export type LotStatus = 
  | "draft" 
  | "analysing" 
  | "pending_review" 
  | "approved" 
  | "overridden" 
  | "reported" 
  | "archived";

export type OnionBucket = "grade_a" | "urs" | "defective";

export type VerificationDecision = "approved" | "overridden";

export interface User {
  id: number;
  email: string | null;
  phone: string | null;
  name: string;
  role: UserRole;
  centre_id: number | null;
  is_active: boolean;
  created_at: string;
}

export interface Centre {
  id: number;
  code: string;
  name: string;
  district: string;
  state: string;
  is_active: boolean;
  created_at: string;
}

export interface OnionDetection {
  id: number;
  lot_id: number;
  image_id: number | null;
  bbox: [number, number, number, number];
  mask_polygon?: number[][] | null;
  original_class: string;
  current_class: string;
  bucket: OnionBucket;
  confidence: number;
  diameter_cm: number | null;
  is_overridden: boolean;
  computation_source: "server" | "device";
}

export interface GradeResult {
  id?: number;
  lot_id: number;
  grade_a_pct: number;
  urs_pct: number;
  defective_pct: number;
  lot_grade: string;
  lot_grade_label: string;
  lot_grade_pct: number;
  total_count: number;
  grade_a_count?: number;
  urs_count?: number;
  defective_count?: number;
  raw_counts: Record<string, number>;
  defect_breakdown: Record<string, { count: number; pct: number }>;
  rule_version: string;
  computation_source: string;
  is_device_computed: boolean;
  computed_at?: string;
}

export interface Verification {
  id: number;
  lot_id: number;
  verifier_id: number;
  decision: VerificationDecision;
  ai_lot_grade: string;
  final_lot_grade: string;
  reason: string | null;
  created_at: string;
}

export interface LotResponse {
  id: number;
  batch_code: string;
  client_lot_id: string | null;
  farmer_id: number | null;
  farmer_name: string;
  centre_id: number;
  centre?: Centre | null;
  crop: string;
  batch_date: string;
  weight_kg: number | null;
  needs_attention: boolean;
  attention_reason: string | null;
  ai_result: Record<string, any> | null;
  final_result: Record<string, any> | null;
  status: LotStatus;
  created_at: string;
  images: any[];
  detections: OnionDetection[];
  grade_result: GradeResult | null;
  verifications: Verification[];
  is_mock: boolean;
}

export interface PipelineStage {
  name: 
    | "image_quality_check" 
    | "marker_detection" 
    | "onion_detection" 
    | "size_measurement" 
    | "defect_detection" 
    | "grading";
  status: "pending" | "running" | "done" | "failed";
  message: string;
  percent: number;
}

export interface GradeStatusResponse {
  lot_id: number;
  lot_status: LotStatus;
  overall_percent: number;
  is_complete: boolean;
  failed_stage: string | null;
  retake_message: string | null;
  is_mock: boolean;
  stages: PipelineStage[];
}
