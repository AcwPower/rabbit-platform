import uuid
from datetime import datetime,timedelta
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select,func
from app.db import Session,now
from app.models import Match,TeamCard,Application,ApplicationNotification
from app.schedule import default_end_at
from conftest import signup,create_team,guest,post,card_data,challenge


def apply_at(owner,team,boss,hours=3):
    token=uuid.uuid4().hex+uuid.uuid4().hex;boss.headers['X-Manage-Token']=token
    start=(now()+timedelta(minutes=10)).replace(second=0)
    result=post(boss,'/api/applications',dict(card_type='team',card_id=team['id'],game_id='预约老板',level=35,notes='请等我到地图后再确认上车',
        requested_start_at=start.isoformat()+'Z',duration_hours=hours,contact={'wechat':'schedule-boss'},**challenge(boss)))
    assert result.status_code==201,result.text
    aid=result.json()['id'];accepted=post(owner,f'/api/applications/{aid}/accept')
    assert accepted.status_code==200,accepted.text
    return aid,accepted.json()['match'],start


def put(client,mid,version,start,end):
    return client.put(f'/api/matches/{mid}/schedule',json={'planned_start_at':start.isoformat()+'Z','expected_end_at':end.isoformat()+'Z','version':version},headers={'X-Idempotency-Key':str(uuid.uuid4())})


def test_apply_schedule_and_captain_adjustment_preserve_actual_times(client):
    signup(client);team=create_team(client);boss=guest();aid,match,start=apply_at(client,team,boss)
    assert match['planned_start_at']==start.isoformat()+'Z'
    assert match['expected_end_at']==(start+timedelta(hours=3)).isoformat()+'Z'
    adjusted=put(client,match['id'],match['schedule_version'],start+timedelta(hours=1),start+timedelta(hours=5))
    assert adjusted.status_code==200,adjusted.text
    current=adjusted.json()['match'];assert current['schedule_version']==2 and current['boarded_at'] is None
    assert put(client,match['id'],1,start,start+timedelta(hours=2)).status_code==409
    assert post(client,f"/api/matches/{match['id']}/board").status_code==200
    after=boss.get(f'/api/applications/{aid}').json()['match']
    assert after['expected_end_at']==current['expected_end_at'] and after['boarded_at']
    actual=after['boarded_at']
    adjusted=put(client,match['id'],2,start,start+timedelta(hours=4))
    assert adjusted.status_code==200 and adjusted.json()['match']['boarded_at']==actual
    roster=client.get('/api/captain/teams').json()['teams'][0]
    member=roster['members'][0]
    assert member['notes']=='请等我到地图后再确认上车'
    assert member['game_id']=='预约老板' and member['status']=='boarded'
    assert member['match']['planned_start_at']==start.isoformat()+'Z'
    assert member['match']['expected_end_at']==(start+timedelta(hours=4)).isoformat()+'Z'
    assert guest().get('/api/captain/teams').status_code==401
    stranger=guest();signup(stranger,'其他队长')
    assert stranger.get('/api/captain/teams').json()['teams']==[]
    assert put(stranger,match['id'],3,start,start+timedelta(hours=7)).status_code==403
    assert put(boss,match['id'],3,start,start+timedelta(hours=7)).status_code==401
    assert put(client,match['id'],3,start,start).status_code==422
    assert put(client,match['id'],3,start,start+timedelta(days=8)).status_code==422
    with Session() as db:
        assert db.get(Application,aid).requested_start_at==start
        events=db.scalars(select(ApplicationNotification).where(ApplicationNotification.application_id==aid)).all()
        assert {e.event for e in events}=={'accepted','end:2','boarded','end:3'}


def test_captain_completion_releases_once_without_boss_and_notifies(client):
    signup(client);team=create_team(client);boss=guest();aid,match,start=apply_at(client,team,boss)
    assert post(client,f"/api/matches/{match['id']}/board").status_code==200
    assert post(boss,f"/api/matches/{match['id']}/complete").status_code==403
    def finish(_):
        c=guest();c.cookies.update(client.cookies);c.headers['X-CSRF-Token']=client.headers['X-CSRF-Token']
        return post(c,f"/api/matches/{match['id']}/complete").status_code
    with ThreadPoolExecutor(2) as pool:assert sorted(pool.map(finish,range(2)))==[200,409]
    detail=boss.get(f'/api/applications/{aid}').json()
    assert detail['match']['status']=='completed' and detail['match']['finished_at']
    assert detail['match']['can_complete'] is False
    assert put(client,match['id'],1,start,start+timedelta(hours=8)).status_code==409
    with Session() as db:
        assert db.get(TeamCard,team['id']).confirmed_boss_count==0
        assert db.scalar(select(func.count(ApplicationNotification.id)).where(ApplicationNotification.application_id==aid,ApplicationNotification.event=='completed'))==1


def test_boss_card_flow_uses_real_boss_name_and_team_captain_can_end(client):
    signup(client);team=create_team(client)
    boss=guest();boss.headers['X-Manage-Token']='a'*64
    bid=post(boss,'/api/boss-cards',card_data(boss,game_id='真实老板',level=35,flower='any',price_mode='any',price=None)).json()['id']
    aid=post(client,'/api/applications',dict(card_type='boss',card_id=bid,offered_team_id=team['id'],game_id='接单打手',level=70,contact={'wechat':'captain-wechat'},**challenge(client))).json()['id']
    match=client.get(f'/api/applications/{aid}').json()['match']
    roster=client.get('/api/captain/teams').json()['teams'][0]
    assert roster['members'][0]['game_id']=='真实老板' and roster['members'][0]['level']==35
    assert post(client,f"/api/matches/{match['id']}/board").status_code==200
    assert post(boss,f"/api/matches/{match['id']}/complete").status_code==403
    assert post(client,f"/api/matches/{match['id']}/complete").json()['status']=='completed'
    assert boss.get(f'/api/applications/{aid}').json()['match']['finished_at']


def test_requested_start_validation_and_closed_card_keeps_active_roster(client):
    signup(client);team=create_team(client);boss=guest();aid,match,start=apply_at(client,team,boss)
    assert post(client,f"/api/matches/{match['id']}/board").status_code==200
    assert post(client,f"/api/team-cards/{team['id']}/status",{'action':'close'}).status_code==200
    result=client.get('/api/captain/teams').json()['teams'][0]
    assert result['current'] and result['members'][0]['status']=='boarded'
    with Session.begin() as db:db.get(Match,match['id']).expected_end_at=now()-timedelta(minutes=1)
    # Planned end is a reminder only; it must never release a seat automatically.
    assert client.get('/api/captain/teams').json()['teams'][0]['members'][0]['status']=='boarded'
    from app.schemas import ApplyInput
    from pydantic import ValidationError
    import pytest
    payload=dict(card_type='team',card_id=team['id'],game_id='老板',level=35,contact={'wechat':'x'})
    for changes in ({'duration_hours':3},{'requested_start_at':start.isoformat()+'Z'},
                    {'requested_start_at':start.isoformat()+'Z','duration_hours':0},
                    {'requested_start_at':start.isoformat(),'duration_hours':3}):
        with pytest.raises(ValidationError):ApplyInput(**(payload|changes))


def test_legacy_default_end_uses_beijing_and_crosses_midnight():
    assert default_end_at(datetime(2026,10,25,12,30),'02:00')==datetime(2026,10,25,18)
    assert default_end_at(datetime(2026,10,25,16,30),'02:00')==datetime(2026,10,25,18)
    assert default_end_at(datetime(2026,10,25,18,30),'02:00')==datetime(2026,10,26,18)
