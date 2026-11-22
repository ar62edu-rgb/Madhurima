from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import reports
from ..db import get_db
from ..exporters import to_pdf, to_xlsx
from ..models import User
from ..security import current_user
from ..services import get_settings, parse_range

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports(_: User = Depends(current_user)):
    return reports.catalogue()


@router.get("/{name}")
def run_report(name: str, request: Request, from_date: str | None = None, to_date: str | None = None,
               format: str = "json", _: User = Depends(current_user), db: Session = Depends(get_db)):
    if name not in reports.REGISTRY:
        raise HTTPException(404, "Unknown report")
    f, t = parse_range(from_date, to_date)
    params = dict(request.query_params)
    rep = reports.run(db, name, f, t, params)
    if format == "json":
        return rep
    s = get_settings(db)
    fname = f"{name}_{f:%Y%m%d}_{t:%Y%m%d}"
    if format == "xlsx":
        return Response(to_xlsx(rep, s), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'})
    if format == "pdf":
        return Response(to_pdf(rep, s), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'})
    raise HTTPException(400, "format must be json, xlsx or pdf")
