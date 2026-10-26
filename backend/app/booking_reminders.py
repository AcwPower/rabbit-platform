"""Persist one reminder per booking schedule and phase; never change occupancy."""
from datetime import timedelta
from sqlalchemy import select,or_
from .db import Session, now
from .models import Match, TeamCard, Application, User
from .application_events import notify_application


def generate_booking_reminders():
    at=now()
    with Session() as db:
        candidates=db.execute(select(Match.id,Match.team_id,Match.application_id)
            .join(TeamCard,TeamCard.id==Match.team_id).join(User,User.id==TeamCard.owner_id)
            .where(Match.status.in_(['boarded','disputed']),or_(Match.reminder_ignored_version.is_(None),Match.reminder_ignored_version!=Match.schedule_version),Match.expected_end_at<=at+timedelta(minutes=30),User.status=='active')).all()
    for match_id,team_id,application_id in candidates:
        with Session.begin() as db:
            # Match lifecycle uses the same lock order, preventing double alerts
            # and making completion/rescheduling win atomically over old timers.
            db.scalar(select(TeamCard).where(TeamCard.id==team_id).with_for_update())
            application=db.scalar(select(Application).where(Application.id==application_id).with_for_update())
            match=db.scalar(select(Match).where(Match.id==match_id).with_for_update())
            if not match or match.status not in ('boarded','disputed') or not match.expected_end_at:continue
            if match.reminder_ignored_version==match.schedule_version:continue
            if match.expected_end_at>at+timedelta(minutes=30):continue
            phase='late' if match.expected_end_at<=at else 'due'
            recipient='owner' if application.card_type=='team' else 'applicant'
            notify_application(db,application,f'{phase}:{match.schedule_version}',recipient)
