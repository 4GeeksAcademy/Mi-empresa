import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from packages.shared.validators import (
    ALLOWED_CATEGORIES,
    ALLOWED_STATUSES,
    REQUIRED_FIELDS,
    CsvFormatError,
)

from .analysis import (
    AnalysisResult,
    analyze_incidents_csv,
)

__all__ = [
    "ALLOWED_CATEGORIES",
    "ALLOWED_STATUSES",
    "REQUIRED_FIELDS",
    "AnalysisResult",
    "CsvFormatError",
    "analyze_incidents_csv",
]
