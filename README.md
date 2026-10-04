# 🧅 AgriGrade: Automated AI Onion Quality Inspection & Agmark Grading System

> **Smart India Hackathon (SIH)**  
> **Offline-First • Tamper-Evident • Edge-Compatible • Agmark Standards Compliant**

---

## 🌟 Executive Summary

AgriGrade is an end-to-end automated quality assessment and grading system for onions. Designed specifically for Indian APMC Mandis, Procurement Hubs, and Village CSC Centers, AgriGrade combines **computer vision instance segmentation (YOLOv8-seg)**, **coin-based marker metric calibration**, **immutable audit trails**, **tamper-evident cryptographic PDF reports**, and **offline-first PWA synchronization**.

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph Client["📱 PWA Client (Field / APMC)"]
        Camera["Camera / Image Capture"] --> Calib["Marker Calibration (px -> cm)"]
        Calib --> InBrowserAI["On-Device Inference (ONNX Web / Mock)"]
        InBrowserAI --> LocalGrade["In-Browser Agmark Grading Engine"]
        LocalGrade --> IDB["IndexedDB Offline Queue"]
        IDB --> AutoSync{"Network Available?"}
    end

    subgraph Backend["🖥️ FastAPI Backend Server"]
        AutoSync -->|POST /lots/sync (Idempotent)| APIRouter["FastAPI API Router"]
        APIRouter --> Auth["JWT & RBAC Security"]
        APIRouter --> MLServer["Two-Stage Server Inference"]
        APIRouter --> GradeService["Pure Python compute_grade()"]
        APIRouter --> AuditLog["Append-Only Audit Log"]
        APIRouter --> ReportGen["ReportLab PDF & QR Generator"]
        APIRouter --> SMS["Twilio / Mock SMS Service"]
    end

    subgraph Storage["💾 Persistence & Verification"]
        AuditLog --> DB[(SQLite / PostgreSQL DB)]
        ReportGen --> CanonicalHash["SHA-256 Canonical JSON Hasher"]
        CanonicalHash --> VerifyAPI["GET /verify/{id}/view (Public HTML)"]
    end
```

---

## 🚀 Quickstart & Setup

### Option 1: One-Command Docker Setup (Recommended)

```bash
docker-compose up --build
```
- Open `http://localhost:8000/` for the **Offline-First PWA Interface**.
- Open `http://localhost:8000/docs` for the **Interactive Swagger OpenAPI Documentation**.

---

### Option 2: Native Python Setup

```bash
# 1. Clone repository & navigate to root
cd sih

# 2. Install dependencies
pip install -r requirements.txt

# 3. Seed demo database (3 centres, 4 users, 10 sample lots with reports)
python backend/seed.py

# 4. Start backend server
uvicorn backend.app.main:app --reload --port 8000
```

---

## 👥 Demo User Credentials (Pre-Seeded)

| Role | Email | Password | Responsibilities |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@agrigrade.in` | `DemoPass123!` | User governance, APMC centre creation, rule versioning |
| **Staff** | `staff@agrigrade.in` | `DemoPass123!` | Lot inspections, quality overrides, dispute resolution |
| **CSC Operator** | `csc@agrigrade.in` | `DemoPass123!` | Village-level offline lot creation and grading |
| **Farmer** | `farmer@agrigrade.in` | `DemoPass123!` | Submitting lots, viewing certificates, SMS notifications |

---

## ⏱️ 5-Minute Evaluation Demo Walkthrough

### Step 1: Offline Lot Inspection & Grading
1. Open `http://localhost:8000/` on your browser or mobile phone.
2. In browser DevTools (Network tab), toggle status to **Offline**.
3. Select an onion photo (or use the camera).
4. Click **⚡ Run AI Grading** — notice instantaneous **on-device computation** with color-coded bounding box overlays and defect metrics ($6.0\text{ cm}$ size threshold).
5. Click **💾 Save to Offline Queue** — view the lot saved locally under **📦 Offline Queue** with `PENDING` sync status.

### Step 2: Automatic Reconnection & Sync
1. Switch browser DevTools back to **Online**.
2. Notice the status badge turns **Online** and automatically syncs the offline lot to the backend server with status transitioning to **SYNCED** (`computation_source: "device"`).

### Step 3: Staff Inspection & Override (Audit Trail)
1. In the API (`/docs`), authenticate as `staff@agrigrade.in` via `POST /auth/login`.
2. Inspect lot details via `GET /lots/{id}`.
3. Submit a manual override on an onion detection using `POST /lots/{id}/override` with a required justification reason:
   ```json
   {
     "reason": "Expert manual cut-test confirmed internal black rot",
     "detection_overrides": [{ "detection_id": 1, "new_class": "rotten" }]
   }
   ```
4. Verify that `original_class` is preserved while `current_class` is updated, grades are recomputed, and the append-only `audit_log` records the actor, reason, and before/after state.

### Step 4: Tamper-Evident Report & Public Verification
1. Call `POST /lots/{id}/report` to generate the official inspection certificate.
2. Download the PDF at `GET /reports/{report_id}/download` — inspect the embedded QR code, annotated onion visuals, defect tables, and canonical SHA-256 hash.
3. Open `http://localhost:8000/verify/{report_id}/view` — observe the **VERIFIED AUTHENTIC** green certificate.
4. **Tamper Test**: Manually alter the database lot weight or farmer name — refresh the verification URL to immediately see **TAMPERING DETECTED** in red due to cryptographic hash mismatch!

---

## 🔍 What is Real vs. Mocked

| Component | Status | Details |
| :--- | :---: | :--- |
| **Backend API & RBAC** | 🟢 **REAL** | FastAPI, JWT, bcrypt password hashing, role dependencies. |
| **Database & Migrations** | 🟢 **REAL** | SQLAlchemy 2.0 ORM, SQLite/PostgreSQL, Alembic migrations. |
| **Audit Log Immutability** | 🟢 **REAL** | ORM event listeners block updates/deletes with custom exceptions. |
| **Grading Rules Engine** | 🟢 **REAL** | Pure Python & JS engines validating `grading_rules.yaml`. |
| **PDF & QR Generation** | 🟢 **REAL** | ReportLab PDF engine, visual image annotations, qrcode generator. |
| **Public Hash Verification** | 🟢 **REAL** | Deterministic canonical JSON SHA-256 hashing and comparison. |
| **PWA & Offline Queue** | 🟢 **REAL** | Service worker cache, IndexedDB `agrigrade_db`, idempotent sync. |
| **Quality Error Handlers** | 🟢 **REAL** | Laplacian blur check, IoU bounding box overlap, marker validation. |
| **SMS Notification Service** | 🟡 **DUAL** | Twilio REST API ready; defaults to structured mock logging. |
| **YOLOv8-seg ML Pipeline** | 🟡 **DUAL** | Roboflow dataset scripts (`wagk9`), training/eval pipelines ready; default runtime uses plausible simulation for seamless demoing without requiring a GPU. |

---

## 🧠 How to Swap in the Real Trained ONNX Model

1. **Download Dataset**:
   ```bash
   python ml/download_dataset.py --api-key YOUR_ROBOFLOW_API_KEY
   ```
2. **Train YOLOv8-seg Model**:
   ```bash
   python -m ml.train --data ml/data/processed/data.yaml --epochs 50 --imgsz 640
   ```
3. **Export to ONNX**:
   ```bash
   python -m ml.export_onnx --weights runs/segment/train/weights/best.pt --output ml/models/onion_yolov8_seg.onnx
   ```
4. **Enable Production Model**:
   In `.env`, set `MOCK_MODEL=false`. The system will automatically load and execute `ml/models/onion_yolov8_seg.onnx` via ONNX Runtime!

---

## 🛡️ Known Limitations & Future Roadmap

1. **Lighting & Glare Compensation**: Extreme outdoor direct sunlight reflections will be mitigated in v2 using adaptive polarizers and CLAHE histogram equalization.
2. **Weight-Based Agmark Grading**: Current grading uses count-based percentages; the configuration structure allows seamless switching to weight-based Agmark metrics when integrated with digital Mandi weighing scales.
3. **Multi-Language Voice Prompts**: Future iterations will add Hindi and Marathi audio feedback for rural farmers during capture and grading.
