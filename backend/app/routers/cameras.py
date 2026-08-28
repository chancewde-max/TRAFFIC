from fastapi import APIRouter

from ..db import session_scope
from ..models import Camera
from ..schemas import CameraOut

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraOut])
def list_cameras():
    with session_scope() as session:
        rows = session.query(Camera).filter(Camera.active == 1).order_by(Camera.name).all()
        return [CameraOut.model_validate(r) for r in rows]
