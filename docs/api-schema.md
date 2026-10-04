# AgriGrade API Schema Documentation

> **Status**: Stable v1.0  
> This specification defines the unified schema shared across the **FastAPI Backend**, **Frontend Web/Mobile**, and **On-Device Edge Inference (Android / ONNX Runtime)**.

---

## 1. Authentication & Security

All protected endpoints require an `Authorization` header containing a standard JWT Bearer token:

```http
Authorization: Bearer <JWT_ACCESS_TOKEN>
```

### Roles and Permissions Matrix
| Role | Lots Read | Lots Create | Upload Images | Run Grading | Manual Override | Admin Actions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **farmer** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **csc** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **staff** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **admin** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 2. API Endpoints

### 2.1 Create Lot
- **Endpoint**: `POST /lots`
- **Auth**: Authenticated User
- **Request Body**:
```json
{
  "farmer_name": "Ramesh Patil",
  "centre_id": 1,
  "weight_kg": 450.50,
  "lot_number": "LOT-20261003-0001" // Optional, auto-generated if omitted
}
```
- **Response** (`201 Created`): `LotResponse` (see Schema section below).

---

### 2.2 Upload Images
- **Endpoint**: `POST /lots/{id}/images`
- **Auth**: Authenticated User
- **Content-Type**: `multipart/form-data`
- **Form Fields**: `files`: 1 to 3 image files (`.jpg`, `.jpeg`, `.png`, `.webp`)
- **Constraints**: Max 3 images per lot, max 15MB per image file.
- **Response** (`201 Created`):
```json
[
  {
    "id": 10,
    "lot_id": 1,
    "storage_key": "storage/lots/1/5a6f8b...jpg",
    "sha256": "5a6f8b0e45c71d2e...",
    "width": 1920,
    "height": 1080,
    "source": "upload",
    "captured_at": "2026-10-03T10:30:00Z",
    "capture_mode": "online"
  }
]
```

---

### 2.3 Run AI Grading
- **Endpoint**: `POST /lots/{id}/grade`
- **Auth**: Authenticated User
- **Description**: Executes two-stage ML inference (YOLOv8-seg + Classifier) and Marker Calibration on all uploaded images, merges detections, runs `compute_grade`, and stores results.
- **Response** (`200 OK`): `LotResponse`

#### Capture Quality Errors (`422 Unprocessable Entity`)
When an image fails quality standards, the API returns actionable retake guidance:

```json
{
  "detail": {
    "error_code": "IMAGE_TOO_BLURRY", // or "NO_ONIONS_FOUND", "MARKER_NOT_FOUND", "TOO_MANY_OVERLAPPING_ONIONS"
    "message": "Image is too blurry to ensure accurate grading.",
    "guidance": "Please hold the camera steady, ensure good lighting, and retake the photo."
  }
}
```

| Error Code | Trigger Condition | Actionable Guidance |
| :--- | :--- | :--- |
| `IMAGE_TOO_BLURRY` | Laplacian variance < 40.0 | Hold camera steady, increase lighting, and retake. |
| `NO_ONIONS_FOUND` | 0 onion detections | Place onions clearly in centre of camera frame. |
| `MARKER_NOT_FOUND` | Reference coin/card missing | Place a standard coin (₹1, ₹2, ₹5) or calibration card beside onions. |
| `TOO_MANY_OVERLAPPING_ONIONS` | Pairwise IoU > 0.45 in >30% onions | Spread onions out on a flat surface so they don't heavily overlap. |

---

### 2.4 Get Lot Details
- **Endpoint**: `GET /lots/{id}`
- **Auth**: Authenticated User
- **Response** (`200 OK`): `LotResponse`

---

### 2.5 Manual Override (Staff Only)
- **Endpoint**: `POST /lots/{id}/override`
- **Auth**: `staff` or `admin`
- **Request Body**:
```json
{
  "reason": "Visual inspection identified internal rot in onion #4",
  "detection_overrides": [
    {
      "detection_id": 4,
      "new_class": "rotten" // good, damaged, rotten, sprouted, or undersized
    }
  ],
  "final_grade_override": null // or { "grade_a_pct": 70.0, "urs_pct": 30.0 }
}
```
- **Rules**:
  - `reason` is **mandatory** for audit compliance.
  - `original_class` is **never modified**; only `current_class` and `is_overridden=true` are updated.
  - Overall grades are automatically recomputed.
  - Full before/after record is appended to the immutable `audit_log`.

---

### 2.6 Generate Inspection Report
- **Endpoint**: `POST /lots/{id}/report`
- **Auth**: Authenticated User
- **Description**: Generates the official tamper-evident PDF inspection report with annotated image, QR code, defect breakdown, and canonical SHA-256 digital signature. If an older active report exists, it is marked superseded.
- **Response** (`201 Created`): `ReportResponse`
```json
{
  "id": 1,
  "lot_id": 10,
  "version": 1,
  "superseded_by": null,
  "pdf_path": "storage/reports/report_lot_10_v1_a1b2c3d4.pdf",
  "report_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "rule_version": "v1.0",
  "is_mock": true,
  "generated_by": 2,
  "generated_at": "2026-10-03T10:35:00Z"
}
```

---

### 2.7 Download Report PDF
- **Endpoint**: `GET /reports/{report_id}/download`
- **Auth**: Public / Authenticated
- **Response** (`200 OK`): `application/pdf` binary stream.

---

### 2.8 Public Report Verification (JSON API)
- **Endpoint**: `GET /verify/{report_id}`
- **Auth**: None (Public)
- **Description**: Recomputes the SHA-256 hash over current database state and compares against the stored report signature to verify authenticity or detect tampering.
- **Response** (`200 OK`):
```json
{
  "report_id": 1,
  "lot_id": 10,
  "lot_number": "LOT-20261003-0001",
  "farmer_name": "Ramesh Patil",
  "centre_name": "Nashik APMC Centre",
  "version": 1,
  "status": "VALID", // "VALID", "TAMPERED", "SUPERSEDED"
  "is_valid": true,
  "is_superseded": false,
  "superseded_by_report_id": null,
  "stored_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "computed_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "grade_a_pct": 85.0,
  "urs_pct": 15.0,
  "total_count": 12,
  "generated_at": "2026-10-03T10:35:00Z",
  "is_mock": true,
  "summary": "Official AgriGrade inspection report verified authentic."
}
```

---

### 2.9 Mobile-Responsive Verification Page (HTML View)
- **Endpoint**: `GET /verify/{report_id}/view`
- **Auth**: None (Public)
- **Description**: Mobile-optimized HTML inspection certificate card scanned directly from the PDF QR code.

---

## 3. Core Data Schemas

### `LotResponse`
```typescript
interface LotResponse {
  id: number;
  lot_number: string | null;
  farmer_name: string;
  centre_id: number;
  centre?: {
    id: number;
    name: string;
    address?: string | null;
  };
  weight_kg: number;
  status: "draft" | "graded" | "reported" | "archived";
  created_at: string; // ISO-8601
  images: ImageResponse[];
  detections: OnionDetectionResponse[];
  grade_result?: GradeResultResponse | null;
  is_mock: boolean;
}
```

### `ReportResponse`
```typescript
interface ReportResponse {
  id: number;
  lot_id: number;
  version: number;
  superseded_by?: number | null;
  pdf_path?: string | null;
  report_hash: string; // 64-character SHA-256
  rule_version: string;
  is_mock: boolean;
  generated_by?: number | null;
  generated_at: string; // ISO-8601
}
```

### `ReportVerifyResponse`
```typescript
interface ReportVerifyResponse {
  report_id: number;
  lot_id: number;
  lot_number: string;
  farmer_name: string;
  centre_name: string;
  version: number;
  status: "VALID" | "TAMPERED" | "SUPERSEDED";
  is_valid: boolean;
  is_superseded: boolean;
  superseded_by_report_id?: number | null;
  stored_hash: string;
  computed_hash: string;
  grade_a_pct: number;
  urs_pct: number;
  total_count: number;
  generated_at: string;
  is_mock: boolean;
  summary: string;
}
```

### `OnionDetectionResponse`
```typescript
interface OnionDetectionResponse {
  id: number;
  lot_id: number;
  image_id: number;
  bbox: [number, number, number, number]; // [x1, y1, x2, y2]
  mask_polygon?: [number, number][] | null; // [[x, y], ...]
  original_class: "good" | "damaged" | "rotten" | "sprouted" | "undersized";
  current_class: "good" | "damaged" | "rotten" | "sprouted" | "undersized";
  confidence: number; // 0.0 - 1.0
  diameter_cm?: number | null;
  is_overridden: boolean;
  created_at: string; // ISO-8601
}
```

### `GradeResultResponse`
```typescript
interface GradeResultResponse {
  id: number;
  lot_id: number;
  grade_a_pct: number; // e.g. 85.50
  urs_pct: number;     // e.g. 14.50 (grade_a_pct + urs_pct = 100.0%)
  total_count: number;
  raw_counts: {
    good: number;
    damaged: number;
    rotten: number;
    sprouted: number;
    undersized: number;
  };
  defect_breakdown: {
    [className: string]: {
      count: number;
      pct: number;
    };
  };
  rule_version: string;
  computed_at: string; // ISO-8601
}
```
