"""Database Seeding Script for Kisan Setu / AgriGrade Demo Environment.

Populates the database with:
- 3 Procurement Centres (C01, C02, C03)
- 4 Role-Based Users (Admin, Staff, CSC, Farmer) + sample farmers
- 10 Sample Lots with batch codes (KS-2026-00001 to KS-2026-00010), three-bucket grading,
  verifications, reports, and tamper-evident hashes.
"""

import os
import random
from datetime import datetime, timedelta
from pathlib import Path
import cv2
import numpy as np

# Ensure environment
os.environ["MOCK_MODEL"] = "true"

from backend.app.core.security import get_password_hash
from backend.app.db import Base, SessionLocal, engine
from backend.app.models.audit_log import AuditLog
from backend.app.models.centre import Centre
from backend.app.models.grade_result import GradeResult
from backend.app.models.image import CaptureMode, Image, ImageSource
from backend.app.models.lot import Lot, LotStatus
from backend.app.models.onion_detection import OnionDetection
from backend.app.models.report import Report
from backend.app.models.user import User, UserRole
from backend.app.models.verification import Verification, VerificationDecision
from backend.app.services.audit import record_audit
from backend.app.services.grading import compute_grade, determine_onion_bucket
from backend.app.services.pdf_report import generate_lot_pdf_report
from backend.app.services.report_hash import build_canonical_report_payload, compute_canonical_hash


def create_dummy_sample_image(output_path: Path, width=640, height=480) -> Path:
    """Create a realistic dummy onion inspection image on disk."""
    img = np.ones((height, width, 3), dtype=np.uint8) * 235
    for _ in range(8):
        cx = random.randint(80, width - 80)
        cy = random.randint(80, height - 80)
        radius = random.randint(25, 45)
        color = (
            random.randint(60, 110),
            random.randint(90, 160),
            random.randint(160, 220),
        )
        cv2.circle(img, (cx, cy), radius, color, -1)
        cv2.circle(img, (cx, cy), radius, (50, 50, 50), 2)

    # Reference coin marker
    cv2.circle(img, (50, 50), 20, (180, 180, 180), -1)
    cv2.circle(img, (50, 50), 20, (60, 60, 60), 2)
    cv2.putText(img, "Rs1", (40, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img)
    return output_path


def seed_database():
    """Main seed execution function."""
    print("Initializing Kisan Setu Demo Database...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # ==========================================
        # 1. SEED CENTRES (3 Centres)
        # ==========================================
        centres_data = [
            {"code": "C01", "name": "Nashik APMC Mandi", "district": "Nashik", "state": "Maharashtra", "address": "Market Yard, Panchavati, Nashik 422003"},
            {"code": "C02", "name": "Lasalgaon Onion Trading Hub", "district": "Nashik", "state": "Maharashtra", "address": "Main APMC Yard, Lasalgaon 422306"},
            {"code": "C03", "name": "Pune Agricultural Procurement Centre", "district": "Pune", "state": "Maharashtra", "address": "Gultekdi Market Yard, Pune 411037"},
            {"code": "C04", "name": "Solapur Farmers APMC Mandi", "district": "Solapur", "state": "Maharashtra", "address": "Solapur APMC Complex, Solapur 413002"},
        ]
        centres = []
        for c in centres_data:
            existing = db.query(Centre).filter(Centre.code == c["code"]).first()
            if not existing:
                centre_obj = Centre(
                    code=c["code"],
                    name=c["name"],
                    district=c["district"],
                    state=c["state"],
                    address=c["address"],
                    is_active=True,
                )
                db.add(centre_obj)
                db.commit()
                db.refresh(centre_obj)
                centres.append(centre_obj)
            else:
                centres.append(existing)

        print(f"[OK] Seeded {len(centres)} Procurement Centres (C01, C02, C03, C04)")

        # ==========================================
        # 2. SEED USERS (4 Roles + Farmers)
        # ==========================================
        users_data = [
            {"name": "System Administrator", "email": "admin@agrigrade.in", "role": UserRole.ADMIN, "centre_id": centres[0].id, "phone": "+919876543201"},
            {"name": "Senior Inspection Staff", "email": "staff@agrigrade.in", "role": UserRole.STAFF, "centre_id": centres[0].id, "phone": "+919876543202"},
            {"name": "CSC Village Operator", "email": "csc@agrigrade.in", "role": UserRole.CSC, "centre_id": centres[1].id, "phone": "+919876543203"},
            {"name": "Ramesh Patil", "email": "farmer@agrigrade.in", "role": UserRole.FARMER, "centre_id": centres[0].id, "phone": "+919876543204"},
            {"name": "Sanjay Rao", "email": "sanjay@agrigrade.in", "role": UserRole.FARMER, "centre_id": centres[0].id, "phone": "+919876543205"},
            {"name": "Kailas Shinde", "email": "kailas@agrigrade.in", "role": UserRole.FARMER, "centre_id": centres[1].id, "phone": "+919876543206"},
            {"name": "Ramesh Kumar", "email": "ramesh.kumar@agrigrade.in", "role": UserRole.FARMER, "centre_id": centres[3].id, "phone": "+919876543207"},
        ]
        users = {}
        for u in users_data:
            existing = db.query(User).filter(User.phone == u["phone"]).first()
            if not existing:
                user_obj = User(
                    name=u["name"],
                    email=u["email"],
                    hashed_password=get_password_hash("DemoPass123!"),
                    role=u["role"],
                    centre_id=u["centre_id"],
                    phone=u["phone"],
                    is_active=True,
                )
                db.add(user_obj)
                db.commit()
                db.refresh(user_obj)
                users[u["email"]] = user_obj
            else:
                users[u["email"]] = existing

        primary_farmer = users["farmer@agrigrade.in"]
        ramesh_kumar = users["ramesh.kumar@agrigrade.in"]
        primary_staff = users["staff@agrigrade.in"]
        primary_admin = users["admin@agrigrade.in"]

        print(f"[OK] Seeded Demo Users (Admin, Staff, CSC, Farmers) [Password: DemoPass123! | Dev OTP: 123456]")

        # ==========================================
        # 3. SEED SAMPLE LOTS (including KS-2026-00125 for Ramesh Kumar at Centre 04)
        # ==========================================
        lot_definitions = [
            ("KS-2026-00001", "Ramesh Patil", primary_farmer.id, 250.0, centres[0].id, LotStatus.REPORTED, "approved", None),
            ("KS-2026-00002", "Ramesh Patil", primary_farmer.id, 180.0, centres[0].id, LotStatus.REPORTED, "approved", None),
            ("KS-2026-00003", "Sanjay Rao", users["sanjay@agrigrade.in"].id, 320.0, centres[0].id, LotStatus.OVERRIDDEN, "overridden", "Manual inspection found excessive rotten onions near core"),
            ("KS-2026-00004", "Kailas Shinde", users["kailas@agrigrade.in"].id, 450.0, centres[1].id, LotStatus.APPROVED, "approved", None),
            ("KS-2026-00005", "Ramesh Patil", primary_farmer.id, 120.0, centres[0].id, LotStatus.APPROVED, "approved", None),
            ("KS-2026-00006", "Tukaram More", None, 280.0, centres[1].id, LotStatus.OVERRIDDEN, "overridden", "Size threshold mismatch with local wholesale specifications"),
            ("KS-2026-00007", "Anil Jadhav", None, 350.0, centres[2].id, LotStatus.REPORTED, "approved", None),
            ("KS-2026-00008", "Babanrao Kadam", None, 190.0, centres[2].id, LotStatus.PENDING_REVIEW, None, None),
            ("KS-2026-00009", "Dnyaneshwar Gaikwad", None, 410.0, centres[0].id, LotStatus.PENDING_REVIEW, None, None),
            ("KS-2026-00010", "Vilasrao Chavan", None, 150.0, centres[0].id, LotStatus.DRAFT, None, None),
            ("KS-2026-00125", "Ramesh Kumar", ramesh_kumar.id, 520.0, centres[3].id, LotStatus.OVERRIDDEN, "overridden", "Visual inspection identified high internal neck rot in sample onions"),
        ]

        storage_base = Path("storage/lots")
        storage_base.mkdir(parents=True, exist_ok=True)

        for i, (batch_code, f_name, f_id, weight, c_id, lot_status, decision, override_reason) in enumerate(lot_definitions, start=1):
            existing_lot = db.query(Lot).filter(Lot.batch_code == batch_code).first()

            if existing_lot:
                continue

            lot_date = datetime.utcnow() - timedelta(days=(10 - i), hours=random.randint(1, 8))

            lot = Lot(
                batch_code=batch_code,
                client_lot_id=f"demo_client_id_{i:03d}",
                lot_number=batch_code,
                farmer_id=f_id,
                farmer_name=f_name,
                centre_id=c_id,
                crop="onion",
                batch_date=lot_date,
                weight_kg=weight,
                status=lot_status,
                created_at=lot_date,
            )
            db.add(lot)
            db.commit()
            db.refresh(lot)

            # 1. Create sample image
            img_path = storage_base / str(lot.id) / "sample_capture.jpg"
            create_dummy_sample_image(img_path)

            img_rec = Image(
                lot_id=lot.id,
                storage_key=str(img_path.as_posix()),
                sha256=f"demo_sha256_hash_seed_{i:04d}",
                width=640,
                height=480,
                source=ImageSource.CAMERA,
                captured_at=lot_date,
                capture_mode=CaptureMode.ONLINE,
            )
            db.add(img_rec)
            db.commit()
            db.refresh(img_rec)

            if lot_status == LotStatus.DRAFT:
                continue

            # 2. Generate detections
            onion_count = random.randint(8, 14)
            classes_pool = ["good", "good", "good", "good", "damaged", "rotten", "sprouted", "undersized"]
            detections = []
            raw_onions = []

            for det_idx in range(onion_count):
                cls = random.choice(classes_pool)
                conf = round(random.uniform(0.85, 0.98), 2)
                diam = round(random.uniform(4.5, 8.5), 1)
                x1 = random.randint(50, 450)
                y1 = random.randint(50, 350)
                bbox = [x1, y1, x1 + random.randint(60, 90), y1 + random.randint(60, 90)]

                bucket = determine_onion_bucket(cls, diam)

                det = OnionDetection(
                    lot_id=lot.id,
                    image_id=img_rec.id,
                    bbox=bbox,
                    original_class=cls,
                    current_class=cls,
                    bucket=bucket,
                    confidence=conf,
                    diameter_cm=diam,
                    is_overridden=False,
                    computation_source="server" if i % 2 == 0 else "device",
                    created_at=lot_date,
                )
                db.add(det)
                detections.append(det)
                raw_onions.append({"class": cls, "diameter_cm": diam})

            db.commit()

            # 3. Compute Grade
            grade_data = compute_grade(raw_onions)
            grade_res = GradeResult(
                lot_id=lot.id,
                grade_a_pct=grade_data["grade_a_pct"],
                urs_pct=grade_data["urs_pct"],
                defective_pct=grade_data["defective_pct"],
                lot_grade=grade_data["lot_grade"],
                lot_grade_label=grade_data["lot_grade_label"],
                lot_grade_pct=grade_data["lot_grade_pct"],
                total_count=grade_data["total_onions"],
                raw_counts=grade_data["raw_counts"],
                defect_breakdown=grade_data["defect_breakdown"],
                rule_version="v2.0",
                computation_source="server" if i % 2 == 0 else "device",
                is_device_computed=(i % 2 != 0),
                computed_at=lot_date,
            )
            db.add(grade_res)
            lot.ai_result = grade_data
            lot.final_result = grade_data
            db.commit()

            # 4. Add Verification (if approved or overridden)
            if decision:
                final_lot_grade = "URS" if decision == "overridden" else grade_data["lot_grade"]
                ver_obj = Verification(
                    lot_id=lot.id,
                    verifier_id=primary_staff.id,
                    decision=VerificationDecision.OVERRIDDEN if decision == "overridden" else VerificationDecision.APPROVED,
                    ai_lot_grade=grade_data["lot_grade"],
                    final_lot_grade=final_lot_grade,
                    reason=override_reason,
                    created_at=lot_date + timedelta(minutes=1),
                )
                db.add(ver_obj)
                if decision == "overridden":
                    final_snapshot = dict(grade_data)
                    final_snapshot["lot_grade"] = final_lot_grade
                    final_snapshot["is_overridden"] = True
                    lot.final_result = final_snapshot
                db.commit()

            # 5. Generate Report (for reported lots)
            if lot_status == LotStatus.REPORTED:
                canonical_payload = build_canonical_report_payload(
                    lot=lot,
                    grade_result=grade_res,
                    detections=detections,
                    version=1,
                )
                r_hash = compute_canonical_hash(canonical_payload)
                report_rec = Report(
                    lot_id=lot.id,
                    version=1,
                    report_hash=r_hash,
                    rule_version="v2.0",
                    is_mock=True,
                    generated_by=primary_staff.id,
                    generated_at=lot_date + timedelta(minutes=2),
                )
                db.add(report_rec)
                db.commit()
                db.refresh(report_rec)

                pdf_path = generate_lot_pdf_report(
                    lot=lot,
                    grade_result=grade_res,
                    detections=detections,
                    report=report_rec,
                )
                report_rec.pdf_path = str(pdf_path.as_posix())
                db.commit()

            # 6. Record Audit Log
            record_audit(
                db=db,
                action="seed_lot",
                entity_type="lot",
                entity_id=lot.id,
                actor_id=primary_admin.id,
                before=None,
                after={"batch_code": lot.batch_code, "status": lot.status.value, "is_demo": True},
                reason="Initial demo seed data generation",
            )
            db.commit()

        print(f"[OK] Seeded 10 Sample Lots (KS-2026-00001 to KS-2026-00010)")
        print("\nKisan Setu Demo Environment Ready!")
        print("----------------------------------------------------------------------")
        print("  Admin:   admin@agrigrade.in   | DemoPass123! | +919876543201")
        print("  Staff:   staff@agrigrade.in   | DemoPass123! | +919876543202")
        print("  CSC:     csc@agrigrade.in     | DemoPass123! | +919876543203")
        print("  Farmer:  farmer@agrigrade.in  | DemoPass123! | +919876543204 (OTP: 123456)")
        print("----------------------------------------------------------------------")

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
