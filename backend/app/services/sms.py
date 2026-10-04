"""SMS notification service for dispatching inspection reports and OTPs to farmers via Twilio or Mock."""

import logging
import uuid
from typing import Any, Dict, Optional
import httpx

from ..core.config import settings
from ..models.grade_result import GradeResult
from ..models.lot import Lot
from ..models.report import Report

logger = logging.getLogger("agrigrade.sms")


def send_sms(to_phone: str, message: str) -> Dict[str, Any]:
    """Send generic SMS (e.g. OTP or notification)."""
    is_mock = (
        settings.SMS_MOCK
        or not settings.TWILIO_ACCOUNT_SID
        or not settings.TWILIO_AUTH_TOKEN
        or not settings.TWILIO_FROM_NUMBER
    )

    if is_mock:
        mock_msg_id = f"mock_sms_{uuid.uuid4().hex[:12]}"
        logger.info(
            f"[MOCK SMS] Dispatch to {to_phone} | ID: {mock_msg_id}\n"
            f"---------- MESSAGE BODY ----------\n"
            f"{message}\n"
            f"----------------------------------"
        )
        return {
            "status": "mock_sent",
            "message_id": mock_msg_id,
            "to": to_phone,
            "body": message,
            "is_mock": True,
        }

    account_sid = settings.TWILIO_ACCOUNT_SID
    auth_token = settings.TWILIO_AUTH_TOKEN
    from_number = settings.TWILIO_FROM_NUMBER
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                url,
                data={
                    "From": from_number,
                    "To": to_phone,
                    "Body": message,
                },
                auth=(account_sid, auth_token),
            )
            response.raise_for_status()
            res_data = response.json()
            return {
                "status": "sent",
                "message_id": res_data.get("sid", "unknown"),
                "to": to_phone,
                "body": message,
                "is_mock": False,
            }
    except Exception as e:
        logger.error(f"Failed to send real SMS to {to_phone}: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "to": to_phone,
            "body": message,
            "is_mock": False,
        }


def build_sms_body(
    lot: Lot,
    grade_result: GradeResult,
    report: Optional[Report] = None,
) -> str:
    """Format a concise, clear SMS inspection summary with verification link."""
    verify_id = report.id if report else lot.id
    verify_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/verify/{verify_id}/view"
    lot_num = getattr(lot, "batch_code", None) or lot.lot_number or f"LOT-{lot.id}"
    farmer_name = lot.farmer.name if lot.farmer else (lot.farmer_name or "Farmer")
    weight_val = f"{lot.weight_kg:.1f}kg" if lot.weight_kg is not None else ""

    body = (
        f"Kisan Setu Inspection Notice\n"
        f"Farmer: {farmer_name}\n"
        f"Batch: {lot_num} {weight_val}\n"
        f"Grade A: {grade_result.grade_a_pct:.1f}%\n"
        f"URS: {grade_result.urs_pct:.1f}%\n"
        f"Defective: {getattr(grade_result, 'defective_pct', 0.0):.1f}%\n"
        f"Total Onions: {grade_result.total_count}\n"
        f"Verify Certificate:\n{verify_url}"
    )
    return body


def send_report_sms(
    to_phone: str,
    lot: Lot,
    grade_result: GradeResult,
    report: Optional[Report] = None,
) -> Dict[str, Any]:
    """Send SMS report summary."""
    body = build_sms_body(lot, grade_result, report)
    return send_sms(to_phone=to_phone, message=body)
