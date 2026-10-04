from datetime import datetime
import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from ..db.base import Base


class ImageSource(str, enum.Enum):
    CAMERA = "camera"
    UPLOAD = "upload"


class CaptureMode(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(Integer, ForeignKey("lots.id", ondelete="CASCADE"), nullable=False)
    storage_key = Column(String(500), nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    source = Column(
        SQLEnum(ImageSource, values_callable=lambda x: [e.value for e in x]),
        default=ImageSource.CAMERA,
        nullable=False
    )
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    capture_mode = Column(
        SQLEnum(CaptureMode, values_callable=lambda x: [e.value for e in x]),
        default=CaptureMode.ONLINE,
        nullable=False
    )

    lot = relationship("Lot", back_populates="images")
    detections = relationship("OnionDetection", back_populates="image", cascade="all, delete-orphan")
