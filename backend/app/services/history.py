from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from ..models import CongestionSample


def get_history(session: Session, camera_id: str, since_hours: float) -> list[CongestionSample]:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=since_hours)
    return (
        session.query(CongestionSample)
        .filter(CongestionSample.camera_id == camera_id, CongestionSample.ts >= since)
        .order_by(CongestionSample.ts.asc())
        .all()
    )
