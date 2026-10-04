import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union
import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Root directory of the backend
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
CONFIG_DIR = BACKEND_DIR / "config"
DEFAULT_GRADING_RULES_PATH = CONFIG_DIR / "grading_rules.yaml"


class GradingRulesConfig(BaseModel):
    """Pydantic model validating grading_rules.yaml."""
    min_size_cm: float = Field(default=6.0, description="Minimum diameter in cm for Grade A", ge=0.0)
    grade_a_definition: Optional[str] = Field(default="Grade A: Healthy onions meeting minimum size", description="Description of Grade A rule")
    urs_definition: Optional[str] = Field(default="URS: Healthy onions below minimum size", description="Description of Under-Rated / Rejected rule")
    class_bucket_mapping: Dict[str, str] = Field(
        default_factory=lambda: {
            "good": "grade_a_or_urs",
            "damaged": "defective",
            "rotten": "defective",
            "sprouted": "defective",
            "undersized": "urs",
        }
    )
    defect_classes: List[str] = Field(
        default_factory=lambda: ["good", "damaged", "rotten", "sprouted", "undersized"]
    )
    lot_grade_rules: List[Dict[str, Any]] = Field(
        default_factory=lambda: [
            {"grade": "Grade A", "condition": "grade_a_pct >= 70.0", "threshold": 70.0},
            {"grade": "Defective", "condition": "defective_pct >= 30.0", "threshold": 30.0},
            {"grade": "URS", "condition": "otherwise"}
        ]
    )
    version: str = Field(default="v2.0", description="Rule configuration version string")

    # ArUco marker configuration
    marker_side_cm: float = Field(
        default=5.0,
        description="Physical side length of the printed ArUco marker in centimetres"
    )
    # Pipeline attention thresholds (configurable without code changes)
    min_onion_count: int = Field(
        default=2,
        description="Minimum detected onions required; fewer → needs_attention"
    )
    min_confidence: float = Field(
        default=0.60,
        description="Mean detection confidence below this → needs_attention"
    )
    blur_threshold: float = Field(
        default=40.0,
        description="Laplacian variance below this → image quality check fails"
    )

    @field_validator("defect_classes")
    @classmethod
    def validate_defect_classes(cls, v: List[str]) -> List[str]:
        required = {"good", "damaged", "rotten", "sprouted", "undersized"}
        if not required.issubset(set(v)):
            raise ValueError(f"defect_classes must include all required classes: {required}")
        return v



def load_grading_rules(yaml_path: Optional[Path] = None) -> GradingRulesConfig:
    """Load and validate grading rules YAML file."""
    path = yaml_path or DEFAULT_GRADING_RULES_PATH
    if not path.exists():
        raise FileNotFoundError(f"Grading rules file not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f) or {}

    return GradingRulesConfig(**raw_data)


class Settings(BaseSettings):
    """Application configuration settings loaded from environment or .env file."""
    ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./onion_grading.db"
    SECRET_KEY: str = "change-this-super-secret-key-in-production-1234567890"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:3000", "http://localhost:8000"]
    STORAGE_DIR: str = "./storage"
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # Mocks & External
    MOCK_MODEL: bool = False
    SMS_MOCK: bool = True
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_FROM_NUMBER: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


settings = Settings()
