from datetime import timedelta
from sqlalchemy import event
from app.db import Session, engine, now
from app.models import Application, Match, TeamCard
from app.services import public_boss_progress
from conftest import signup, create_team, guest


def seed(team_id, status, *, boarded=True, finished=False, source='web'):
    with Session.begin() as db:
        application=Application(card_type='team',team_card_id=team_id,game_id='不应公开的老板',
            source=source,status='accepted',notes='私密备注',manage_hash='not-public',expires_at=now()+timedelta(days=1))
        db.add(application);db.flush()
        match=Match(application_id=application.id,team_id=team_id,status=status,
            boarded_at=now()-timedelta(hours=3) if boarded else None,
            planned_start_at=now()-timedelta(hours=4),expected_end_at=now()-timedelta(hours=1),
            finished_at=now() if finished else None)
        db.add(match);db.flush()
        if boarded and not finished and status in ('boarded','disputed'):
            db.get(TeamCard,team_id).confirmed_boss_count+=1
        return match.id


def test_public_cards_only_expose_anonymous_current_boss_timestamps(client):
    signup(client);team=create_team(client,capacity=6)
    first=seed(team['id'],'boarded',source='screenshot')
    seed(team['id'],'disputed')
    seed(team['id'],'contacted',boarded=False)
    seed(team['id'],'completed',finished=True)
    seed(team['id'],'cancelled',finished=True)
    other=create_team(client,map_name='另一地图',capacity=3)
    seed(other['id'],'boarded')
    public=guest()
    items={item['id']:item for item in public.get('/api/team-cards').json()['items']}
    rows=items[team['id']]['boss_progress']
    assert len(rows)==2 and [r['number'] for r in rows]==[1,2]
    assert len(items[other['id']]['boss_progress'])==1
    for row in rows:
        assert set(row)=={'number','boarded_at','expected_end_at'}
        assert row['boarded_at'].endswith('Z') and row['expected_end_at'].endswith('Z')
    assert '不应公开的老板' not in str(rows) and '私密备注' not in str(rows)
    assert public.get(f"/api/team-cards/{team['id']}").json()['boss_progress']==rows
    # Overdue seats remain occupied until explicitly completed by the captain.
    assert items[team['id']]['confirmed_boss_count']==2
    with Session.begin() as db:
        match=db.get(Match,first);match.status='completed';match.finished_at=now()
        db.get(TeamCard,team['id']).confirmed_boss_count-=1
    assert len(public.get(f"/api/team-cards/{team['id']}").json()['boss_progress'])==1


def test_progress_is_batched_and_missing_end_time_stays_unknown(client):
    signup(client);one=create_team(client);two=create_team(client)
    mid=seed(one['id'],'boarded')
    with Session.begin() as db:db.get(Match,mid).expected_end_at=None
    queries=[]
    def record(*args):queries.append(args[2])
    event.listen(engine,'before_cursor_execute',record)
    try:
        with Session() as db:result=public_boss_progress(db,[one['id'],two['id']])
    finally:event.remove(engine,'before_cursor_execute',record)
    assert len(queries)==1
    assert result[two['id']]==[]
    assert result[one['id']][0]['expected_end_at'] is None
