from fastapi import APIRouter, Query

from ..db import session_scope
from ..models import Incident
from ..schemas import IncidentOut

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentOut])
def list_incidents(limit: int = Query(50, gt=0, le=500)):
    with session_scope() as session:
        rows = session.query(Incident).order_by(Incident.ts.desc()).limit(limit).all()
        return [IncidentOut.model_validate(r) for r in rows]
