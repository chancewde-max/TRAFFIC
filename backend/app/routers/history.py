from fastapi import APIRouter, Query

from ..db import session_scope
from ..schemas import HistoryPoint
from ..services.history import get_history

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=list[HistoryPoint])
def history(
    camera_id: str = Query(...),
    hours: float = Query(6.0, gt=0, le=168),
):
    with session_scope() as session:
        rows = get_history(session, camera_id, hours)
        if not rows:
            return []
        return [
            HistoryPoint(ts=r.ts, vehicle_count=r.vehicle_count, avg_speed_mps=r.avg_speed_mps)
            for r in rows
        ]
