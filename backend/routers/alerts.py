"""Router for anomaly and consumption alerts."""
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Alert
from backend.schemas import AlertAcknowledgeResponse, AlertOut

router = APIRouter()


@router.get("/alerts", response_model=List[AlertOut])
def get_alerts(
    unacknowledged_only: bool = True,
    db: Session = Depends(get_db),
):
    """Retrieve alerts, filtered by unacknowledged status by default."""
    query = db.query(Alert)
    if unacknowledged_only:
        query = query.filter(Alert.acknowledged.is_(False))
    return query.order_by(Alert.triggered_at.desc()).all()


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertAcknowledgeResponse)
def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
):
    """Acknowledge an active alert by ID."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledged = True
    alert.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)

    return AlertAcknowledgeResponse(
        id=alert.id,
        acknowledged=True,
        acknowledged_at=alert.acknowledged_at,
        message="Alert acknowledged successfully",
    )


@router.post("/alerts/{alert_id}/reset", response_model=AlertAcknowledgeResponse)
def reset_alert(
    alert_id: int,
    db: Session = Depends(get_db),
):
    """Reset an acknowledged alert back to active status (useful for demonstrations)."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledged = False
    alert.acknowledged_at = None
    db.commit()
    db.refresh(alert)

    return AlertAcknowledgeResponse(
        id=alert.id,
        acknowledged=False,
        acknowledged_at=datetime.now(timezone.utc),
        message="Alert reset to active successfully",
    )
