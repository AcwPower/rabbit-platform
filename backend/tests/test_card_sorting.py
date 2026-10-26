from datetime import timedelta
from app.db import Session,now
from app.models import TeamCard,Match
from conftest import signup,create_team,guest
from test_public_boss_progress import seed


def clone_team(template, **changes):
    # Seed enough independent cards to test pagination without hitting the
    # separate per-publisher API limit (covered by platform tests).
    with Session.begin() as db:
        original=db.get(TeamCard,template['id'])
        values={column.name:getattr(original,column.name) for column in TeamCard.__table__.columns if column.name!='id'}
        row=TeamCard(**(values|changes));db.add(row);db.flush()
        return {'id':row.id}


def ids(client,query=''):
    r=client.get('/api/team-cards'+query)
    assert r.status_code==200,r.text
    return [c['id'] for c in r.json()['items']]


def test_available_first_then_future_end_then_unknown_and_overdue(client):
    signup(client)
    open_old=create_team(client,map_name='有空位老队伍')
    open_new=clone_team(open_old,map_name='有空位新队伍')
    later=clone_team(open_old,map_name='晚结束')
    soon=clone_team(open_old,map_name='快结束')
    overdue=clone_team(open_old,map_name='已到时')
    unknown=clone_team(open_old,map_name='时间未知')
    with Session.begin() as db:
        for n,c in enumerate([open_old,open_new,later,soon,overdue,unknown]):
            db.get(TeamCard,c['id']).created_at=now()-timedelta(minutes=60-n)
    for c,minutes in [(later,120),(soon,20),(overdue,-20),(unknown,None)]:
        mid=seed(c['id'],'boarded')
        with Session.begin() as db:db.get(Match,mid).expected_end_at=now()+timedelta(minutes=minutes) if minutes is not None else None
    public=guest()
    assert ids(public)==[c['id'] for c in [open_new,open_old,soon,later,unknown,overdue]]
    assert ids(public,'?sort=latest')==[c['id'] for c in [unknown,overdue,soon,later,open_new,open_old]]
    assert ids(public,'?available=true')==[open_new['id'],open_old['id']]
    # Cancelled/finished matches cannot influence expected availability.
    with Session.begin() as db:
        db.query(Match).filter(Match.team_id==later['id']).update({'status':'completed','finished_at':now()})
    assert ids(public).index(later['id'])>ids(public).index(soon['id'])
    assert public.get('/api/team-cards?sort=not-valid').status_code==422


def test_ordering_happens_before_pagination(client):
    signup(client)
    oldest=create_team(client)
    others=[clone_team(oldest) for _ in range(20)]
    with Session.begin() as db:
        db.get(TeamCard,oldest['id']).created_at=now()-timedelta(days=1)
        for card in others:db.get(TeamCard,card['id']).confirmed_boss_count=1
    first=ids(guest());second=ids(guest(),'?page=2')
    assert len(first)==20 and len(second)==1
    assert first[0]==oldest['id'] and not set(first)&set(second)
