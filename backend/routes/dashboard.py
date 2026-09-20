import sys
from pathlib import Path
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

# Resolve path so imports work whether run locally from root, backend/, or on Vercel
backend_dir = Path(__file__).resolve().parent.parent
root_dir = backend_dir.parent

for path in (str(backend_dir), str(root_dir)):
    if path not in sys.path:
        sys.path.append(path)

try:
    from backend.database import get_db
    from backend.models import Scan, RuleResult
except ImportError:
    from database import get_db
    from models import Scan, RuleResult

# Keep prefix as "/dashboard". main.py mounts it both with and without "/api"
router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


@router.get("")
@router.get("/")
def get_dashboard(db: Session = Depends(get_db)):

    total_scans = db.query(Scan).count()

    compliant = (
        db.query(Scan)
        .filter(Scan.overall_status == "pass")
        .count()
    )

    non_compliant = (
        db.query(Scan)
        .filter(Scan.overall_status == "fail")
        .count()
    )

    failed_rules = (
        db.query(RuleResult)
        .filter(RuleResult.status == "fail")
        .all()
    )

    violation_breakdown = {}

    for result in failed_rules:
        rule_name = result.rule_name

        if rule_name not in violation_breakdown:
            violation_breakdown[rule_name] = 0

        violation_breakdown[rule_name] += 1

    return {
        "total_scans": total_scans,
        "compliant": compliant,
        "non_compliant": non_compliant,
        "violation_breakdown": violation_breakdown
    }