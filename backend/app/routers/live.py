import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func

from ..broadcast import broadcaster
from ..db import session_scope
from ..models import Camera, CongestionSample, Incident
from ..schemas import CameraOut, CongestionOut, IncidentOut

router = APIRouter()
logger = logging.getLogger(__name__)


def _initial_snapshot() -> dict:
    with session_scope() as session:
        cameras = session.query(Camera).filter(Camera.active == 1).all()
        camera_payload = [CameraOut.model_validate(c).model_dump(mode="json") for c in cameras]

        subq = (
            session.query(CongestionSample.camera_id, func.max(CongestionSample.ts).label("max_ts"))
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
        congestion_payload = [CongestionOut.model_validate(r).model_dump(mode="json") for r in rows]

        incident_rows = session.query(Incident).order_by(Incident.ts.desc()).limit(50).all()
        incident_payload = [IncidentOut.model_validate(r).model_dump(mode="json") for r in incident_rows]

    return {
        "type": "init",
        "cameras": camera_payload,
        "congestion": congestion_payload,
        "incidents": incident_payload,
    }


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json(_initial_snapshot())

    queue = broadcaster.subscribe()
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        broadcaster.unsubscribe(queue)
