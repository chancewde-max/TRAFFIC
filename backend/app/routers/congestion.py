from fastapi import APIRouter
from sqlalchemy import func

from ..db import session_scope
from ..models import CongestionSample
from ..schemas import CongestionOut

router = APIRouter(prefix="/api/congestion", tags=["congestion"])


@router.get("", response_model=list[CongestionOut])
def latest_congestion():
    with session_scope() as session:
        subq = (
            session.query(
                CongestionSample.camera_id, func.max(CongestionSample.ts).label("max_ts")
            )
            .group_by(CongestionSample.camera_id)
            .subquery()
        )
        rows = (
            session.query(CongestionSample)
            .join(
                subq,
                (CongestionSample.camera_id == subq.c.camera_id)
                & (CongestionSample.ts == subq.c.max_ts),
            )
            .all()
        )
        return [CongestionOut.model_validate(r) for r in rows]
