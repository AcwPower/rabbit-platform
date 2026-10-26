from sqlalchemy import select
from .models import ApplicationNotification

def notify_application(db, application, event, recipient_side):
    existing=db.scalar(select(ApplicationNotification.id).where(
        ApplicationNotification.application_id==application.id,
        ApplicationNotification.recipient_side==recipient_side,
        ApplicationNotification.event==event))
    if not existing:
        db.add(ApplicationNotification(application_id=application.id,event=event,recipient_side=recipient_side))
