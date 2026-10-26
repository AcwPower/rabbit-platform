from datetime import timedelta
from sqlalchemy import select, delete, update
from .db import Session, now
from .models import *

def cleanup():
    with Session.begin() as db:
        for cls in (TeamCard,BossCard,PartnerCard):
            db.execute(update(cls).where(cls.status=='active',cls.expires_at<=now()).values(status='expired'))
        db.execute(update(Application).where(Application.status=='pending',Application.expires_at<=now()).values(status='expired',active_key=None))
        db.execute(update(PartnerApplication).where(PartnerApplication.status=='pending',PartnerApplication.expires_at<=now()).values(status='expired',active_key=None))
        db.execute(update(Contact).where(Contact.deleted_at.is_(None),Contact.expires_at<=now()).values(encrypted='',deleted_at=now()))
        db.execute(delete(LoginSession).where(LoginSession.expires_at<=now()))
        db.execute(delete(Challenge).where(Challenge.expires_at<=now()))
        db.execute(delete(RateBucket).where(RateBucket.expires_at<=now()))
        db.execute(delete(RequestKey).where(RequestKey.created_at<now()-timedelta(days=2)))
        db.execute(delete(RequestKey).where(RequestKey.status_code==0,RequestKey.created_at<now()-timedelta(minutes=5)))
    from .booking_reminders import generate_booking_reminders
    generate_booking_reminders()
    print('Cleanup and booking reminders complete')

if __name__=='__main__': cleanup()
