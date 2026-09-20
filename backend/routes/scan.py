import os
import re
import sys
import uuid
from pathlib import Path
import boto3
from botocore.client import Config
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Ensure root and backend paths are resolvable
backend_dir = Path(__file__).resolve().parent.parent
root_dir = backend_dir.parent
for p in (str(backend_dir), str(root_dir)):
    if p not in sys.path:
        sys.path.append(p)

try:
    from backend.database import get_db
    from backend.models import Product, Scan, RuleResult
except ImportError:
    from database import get_db
    from models import Product, Scan, RuleResult

load_dotenv(override=True)

router = APIRouter()

AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-south-1").strip()
S3_BUCKET = os.getenv("S3_BUCKET_NAME", "complyscan-labels-9153").strip()
AWS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
AWS_SECRET = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()

SCANS_DB = {}
scan_counter = 1

custom_config = Config(
    region_name=AWS_REGION,
    signature_version="s3v4"
)

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_KEY,
    aws_secret_access_key=AWS_SECRET,
    config=custom_config
)

textract_client = boto3.client(
    "textract",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_KEY,
    aws_secret_access_key=AWS_SECRET,
    config=custom_config
)


class RenamePayload(BaseModel):
    title: str


@router.post("/scan")
async def scan_label(file: UploadFile = File(...), db: Session = Depends(get_db)):
    global scan_counter
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image.")

    file_extension = file.filename.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{file_extension}"

    # Reset file cursor before upload to guarantee full read
    await file.seek(0)

    try:
        s3_client.upload_fileobj(
            file.file,
            S3_BUCKET,
            unique_filename,
            ExtraArgs={"ContentType": file.content_type}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 Upload failed: {str(e)}")

    try:
        response = textract_client.detect_document_text(
            Document={
                "S3Object": {
                    "Bucket": S3_BUCKET,
                    "Name": unique_filename
                }
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Textract processing failed: {str(e)}")

    extracted_text = []
    for item in response.get("Blocks", []):
        if item["BlockType"] == "LINE":
            extracted_text.append(item["Text"].strip())

    # Permanent URL (or fallback to max 7-day presigned URL)
    image_url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{unique_filename}"
    try:
        # 7-day presigned URL fallback in case the bucket blocks public read
        presigned_fallback = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": unique_filename},
            ExpiresIn=604800
        )
        if presigned_fallback:
            image_url = presigned_fallback
    except Exception:
        pass

    # =========================================================
    # DYNAMIC LEGAL METROLOGY EXTRACTION
    # =========================================================
    full_text = " ".join(extracted_text)

    # 1. Net Quantity
    net_match = re.search(
        r"(?:(?:net\s*(?:wt\.?|weight|qty|quantity)?[:.]?\s*)?)(\b\d+(?:\.\d+)?\s*(?:g|gm|gms|kg|ml|l|ltr|pieces|units)\b)",
        full_text,
        re.IGNORECASE
    )
    val_net_wt = f"Net Wt.: {net_match.group(1).strip()}" if net_match else None

    # 2. MRP & Unit Sale Price
    mrp_lines = []
    for line in extracted_text:
        line_clean = line.strip()
        line_lower = line_clean.lower()
        if any(k in line_lower for k in ["m.r.p", "mrp", "rs.", "₹"]) and any(c.isdigit() for c in line_clean):
            mrp_lines.append(line_clean)
        elif any(k in line_lower for k in ["per g", "per ml", "per kg", "per unit"]):
            mrp_lines.append(line_clean)
    val_mrp = " | ".join(dict.fromkeys(mrp_lines[:2])) if mrp_lines else None

    # 3. Manufacturer Details
    mfg_line = None
    for line in extracted_text:
        line_clean = line.strip()
        line_lower = line_clean.lower()
        if any(k in line_lower for k in ["mkt. by", "mfd. by", "mkd. by", "manufactured by", "packed by", "marketed by"]):
            mfg_line = line_clean
            break

    if not mfg_line:
        for line in extracted_text:
            if any(k in line.lower() for k in ["private limited", "pvt. ltd", "pvt ltd", "foods limited", "industries"]):
                mfg_line = line.strip()
                break

    address_line = next(
        (
            l.strip() for l in extracted_text
            if (re.search(r"\b\d{6}\b", l) or any(k in l.lower() for k in ["mumbai", "delhi", "bengaluru", "kolkata", "chennai", "center", "tower", "floor", "road", "marg", "sector", "estate", "nagar"]))
            and not any(bad in l.lower() for bad in ["mkt. by", "mfd. by", "mkd. by", "ingredients", "nutrition"])
        ),
        None
    )

    if mfg_line and address_line and address_line not in mfg_line:
        val_mfg = f"{mfg_line} {address_line}"
    elif mfg_line:
        val_mfg = mfg_line
    else:
        val_mfg = None

    # 4. Mfg / Pkg Date
    date_matches = re.findall(r"\b\d{2}[/-]\d{2}[/-]\d{2,4}\b", full_text)
    if date_matches:
        combined_dates = []
        for line in extracted_text:
            if any(k in line.lower() for k in ["pkd", "use by", "mfg", "exp"]) and re.search(r"\d{2}[/-]\d{2}", line):
                combined_dates.append(line.strip())

        if combined_dates:
            val_date = " | ".join(combined_dates[:2])
        else:
            tags_found = []
            for t in ["Pkd.", "USE BY:"]:
                if any(t.lower().replace(":", "") in l.lower() for l in extracted_text):
                    tags_found.append(t)

            if len(tags_found) >= 2 and len(date_matches) >= 2:
                val_date = f"{tags_found[0]} {date_matches[0]} | {tags_found[1]} {date_matches[1]}"
            elif tags_found and date_matches:
                val_date = f"{tags_found[0]} {date_matches[0]}"
            else:
                val_date = " | ".join(date_matches[:2])
    else:
        val_date = None

    # 5. Consumer Care Contacts
    care_findings = []
    toll_free_match = re.search(r"\b1800\s*\d{2,4}\s*\d{3,4}\b|\b\d{10,12}\b", full_text)
    if toll_free_match:
        care_findings.append(toll_free_match.group(0).strip())
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", full_text)
    if email_match:
        care_findings.append(email_match.group(0).strip())
    val_care = " | ".join(care_findings) if care_findings else None

    rule_results = [
        {
            "rule": "Net Quantity",
            "status": "pass" if val_net_wt else "fail",
            "detail": "Standard metric weight/volume declaration verified" if val_net_wt else "Net quantity declaration not found on label",
            "scanned_value": val_net_wt if val_net_wt else "Not Detected"
        },
        {
            "rule": "MRP & Unit Sale Price",
            "status": "pass" if val_mrp else "fail",
            "detail": "MRP / Unit sale price declaration verified" if val_mrp else "MRP declaration missing or unreadable",
            "scanned_value": val_mrp if val_mrp else "Not Detected"
        },
        {
            "rule": "Manufacturer Details",
            "status": "pass" if val_mfg else "fail",
            "detail": "Packer / Manufacturer identifier detected" if val_mfg else "Manufacturer or packer details missing",
            "scanned_value": val_mfg if val_mfg else "Not Detected"
        },
        {
            "rule": "Mfg / Pkg Date",
            "status": "pass" if val_date else "fail",
            "detail": "Packaging or manufacturing date detected" if val_date else "Packaging / Expiry date declaration not found",
            "scanned_value": val_date if val_date else "Not Detected"
        },
        {
            "rule": "Consumer Care",
            "status": "pass" if val_care else "fail",
            "detail": "Consumer grievance helpline/email verified" if val_care else "No consumer grievance phone or email found",
            "scanned_value": val_care if val_care else "Not Detected"
        }
    ]

    all_passed = all(r["status"] == "pass" for r in rule_results)
    db_status = "pass" if all_passed else "fail"
    ui_status = "COMPLIANT" if all_passed else "NON-COMPLIANT"

    # Save to SQLite
    current_id = scan_counter
    scan_counter += 1

    try:
        new_product = Product(image=image_url)
        db.add(new_product)
        db.flush()

        new_scan = Scan(
            product_id=new_product.id,
            extracted_text="\n".join(extracted_text),
            overall_status=db_status
        )
        db.add(new_scan)
        db.flush()

        for r in rule_results:
            db_rule = RuleResult(
                scan_id=new_scan.id,
                rule_name=r["rule"],
                status=r["status"],
                detail=f"{r['detail']} (Value: {r['scanned_value']})"
            )
            db.add(db_rule)

        db.commit()
        current_id = new_scan.id
    except Exception as db_err:
        db.rollback()
        print(f"[Scan Save Warning] Could not persist scan to database: {db_err}")

    result_payload = {
        "id": current_id,
        "scan_id": current_id,
        "image_url": image_url,
        "extracted_text": extracted_text,
        "rule_results": rule_results,
        "overall_status": ui_status
    }

    SCANS_DB[str(current_id)] = result_payload
    return result_payload


@router.get("/scans")
def list_scans(db: Session = Depends(get_db)):
    """Returns scan history for dashboard.html"""
    try:
        scans = db.query(Scan).order_by(Scan.timestamp.desc()).limit(20).all()
        if scans:
            return [
                {
                    "id": s.id,
                    "scan_id": s.id,
                    "overall_status": "COMPLIANT" if s.overall_status.lower() == "pass" else "NON-COMPLIANT",
                    "status": s.overall_status,
                    "timestamp": s.timestamp.isoformat(),
                    "created_at": s.timestamp.isoformat()
                }
                for s in scans
            ]
    except Exception as e:
        print(f"[Database Query Warning] {e}")

    return list(reversed(list(SCANS_DB.values())))


@router.get("/report/{report_id}")
async def get_report(report_id: str, db: Session = Depends(get_db)):
    """Returns scan results for report.html"""
    if report_id in SCANS_DB:
        return SCANS_DB[report_id]

    try:
        scan_record = db.query(Scan).filter(Scan.id == int(report_id)).first()
        if scan_record:
            rules = [
                {
                    "rule": r.rule_name,
                    "status": r.status,
                    "detail": r.detail or ""
                }
                for r in scan_record.rule_results
            ]
            return {
                "id": scan_record.id,
                "scan_id": scan_record.id,
                "image_url": scan_record.product.image if scan_record.product else "",
                "extracted_text": (scan_record.extracted_text or "").split("\n"),
                "rule_results": rules,
                "overall_status": "COMPLIANT" if scan_record.overall_status.lower() == "pass" else "NON-COMPLIANT"
            }
    except Exception:
        pass

    if SCANS_DB:
        return list(SCANS_DB.values())[-1]

    raise HTTPException(status_code=404, detail="Report not found. Please run a new scan.")


@router.delete("/scans/{scan_id}")
def delete_scan(scan_id: int, db: Session = Depends(get_db)):
    """Delete a scan record and its associated rule results."""
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    try:
        if scan.product:
            db.delete(scan.product)
        db.delete(scan)
        db.commit()

        SCANS_DB.pop(str(scan_id), None)
        return {"status": "success", "message": f"Scan #{scan_id} deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete scan: {str(e)}")


@router.patch("/scans/{scan_id}")
def rename_scan(scan_id: int, payload: RenamePayload, db: Session = Depends(get_db)):
    """Rename a scan without overwriting the S3 image link."""
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    try:
        if str(scan_id) in SCANS_DB:
            SCANS_DB[str(scan_id)]["title"] = payload.title
        return {"status": "success", "title": payload.title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename scan: {str(e)}")