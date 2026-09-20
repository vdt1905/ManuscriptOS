"""Deep-scan / FormatForge routes — the agno multi-agent pipeline that does
heavy DOCX formatting + LaTeX generation. Mounted under /deepscan by
backend-ai/main.py."""

import os
import json
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from .agno_router import agno_router
from .agents.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

PACKAGE_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_ROOT / "output"
OUTPUT_FORMATTED_DIR = OUTPUT_DIR / "formatted"
OUTPUT_FORMATTED_DIR.mkdir(parents=True, exist_ok=True)

# Patch config so agents resolve the output dir without a hard-coded path.
os.environ.setdefault("OUTPUT_FORMATTED_DIR", str(OUTPUT_FORMATTED_DIR))

router = APIRouter(tags=["DeepScan"])

# Fold the SSE pipeline routes (POST /api/v2/pipeline/stream + friends) in.
router.include_router(agno_router)
logger.info("Deep-scan pipeline router loaded")


@router.get("/api/health")
def health():
    return {"status": "ok", "package": "deepscan"}


@router.get("/api/styles")
def list_styles():
    styles_dir = PACKAGE_ROOT / "styles"
    return {
        "available_styles": {
            f.stem: f.stem.upper().replace("_", " ")
            for f in styles_dir.glob("*.json")
        }
    }


@router.post("/api/format")
async def format_document(
    file: UploadFile = File(...),
    style: str = Form("apa7"),
):
    """Upload a manuscript, select a style, get a formatted document back."""
    suffix = Path(file.filename or "upload.docx").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        orchestrator = Orchestrator()
        result = await orchestrator.run(input_path=tmp_path, style_id=style)

        if not result.success:
            raise HTTPException(status_code=500, detail=result.error_message or "Pipeline failed")

        return JSONResponse(content={
            "success": True,
            # bare name: that is what /api/download/{filename} takes
            "output_filename": Path(result.output_filename).name if result.output_filename else None,
            "compliance_score": result.compliance_report.overall_score if result.compliance_report else None,
            "processing_time_seconds": result.processing_time_seconds,
        })
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/api/download/{filename}")
def download_file(filename: str):
    file_path = OUTPUT_FORMATTED_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )
