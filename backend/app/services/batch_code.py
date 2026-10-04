"""Batch code generation service.

Generates atomic per-year lot batch codes formatted as KS-{YYYY}-{5-digit sequence}
(e.g., KS-2026-00001).
"""

from datetime import datetime
import re
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models.lot import Lot


def generate_batch_code(db: Session, year: int = None) -> str:
    """Generate the next atomic batch code for the given year.
    
    Format: KS-{YYYY}-{sequence:05d} (e.g. KS-2026-00001)
    """
    if year is None:
        year = datetime.utcnow().year

    prefix = f"KS-{year}-"
    pattern = re.compile(rf"^KS-{year}-(\d{{5}})$")

    # Fetch all batch codes for this year to find the true highest sequence number
    existing_lots = db.scalars(
        select(Lot.batch_code).where(Lot.batch_code.like(f"{prefix}%"))
    ).all()

    max_seq = 0
    for code in existing_lots:
        if code:
            match = pattern.match(code)
            if match:
                seq = int(match.group(1))
                if seq > max_seq:
                    max_seq = seq

    next_seq = max_seq + 1
    return f"KS-{year}-{next_seq:05d}"
