from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select,func
from app.db import Session,now
from app.models import Match,RequestKey
from conftest import signup,create_team,guest,post,apply_guest,card_data,challenge
from test_captain_schedule import apply_at,put


def query(client,managed=None):
    response=post(client,'/api/boss/bookings/query',{'managed':managed or []})
    assert response.status_code==200,response.text
    return response.json()['bookings']


def test_guest_boss_sees_current_times_adjustments_overtime_and_finished_history(client):
    signup(client);team=create_team(client);boss=guest();aid,match,start=apply_at(client,team,boss)
    records=[{'type':'application','id':aid,'manage':boss.headers['X-Manage-Token']}]
    booking=query(boss,records)[0]
    assert booking['game_id']=='预约老板' and booking['captain_name']==team['game_id']
    assert booking['status']=='contacted' and booking['current']
    assert booking['planned_start_at']==start.isoformat()+'Z' and booking['boarded_at'] is None
    assert booking['expected_end_at']==(start+timedelta(hours=3)).isoformat()+'Z'
    assert 'contacts' not in booking and 'wechat' not in booking and records[0]['manage'] not in str(booking)
    assert post(client,f"/api/matches/{match['id']}/board").status_code==200
    assert put(client,match['id'],1,start,start+timedelta(hours=4)).status_code==200
    assert query(boss,records)[0]['expected_end_at']==(start+timedelta(hours=4)).isoformat()+'Z'
    with Session.begin() as db:db.get(Match,match['id']).expected_end_at=now()-timedelta(minutes=12)
    late=query(boss,records)[0]
    assert late['status']=='boarded' and late['current'] and late['boarded_at'] and late['finished_at'] is None
    assert post(client,f"/api/matches/{match['id']}/complete").status_code==200
    ended=query(boss,records)[0]
    assert ended['status']=='completed' and not ended['current'] and ended['finished_at']


def test_guest_query_credentials_are_scoped_and_do_not_create_write_snapshots(client):
    signup(client);team=create_team(client);boss=guest();aid,token=apply_guest(boss,team)
    records=[{'type':'application','id':aid,'manage':token}]
    with Session() as db:before=db.scalar(select(func.count(RequestKey.key_hash)))
    own=query(boss,records)
    assert len(own)==1 and own[0]['status']=='pending'
    assert query(guest())==[] and query(client)==[]
    assert query(guest(),[records[0]|{'manage':'b'*64}])==[]
    assert query(guest(),[records[0]|{'type':'boss'}])==[]
    with Session() as db:assert db.scalar(select(func.count(RequestKey.key_hash)))==before
    response=boss.post('/api/boss/bookings/query',json={'managed':records},headers={'Origin':'http://wrong.example'})
    assert response.status_code==403


def test_claimed_boss_card_and_logged_in_boss_get_only_their_own_arrangements(client):
    signup(client);team=create_team(client)
    boss=guest();token=uuid4().hex+uuid4().hex;boss.headers['X-Manage-Token']=token
    bid=post(boss,'/api/boss-cards',card_data(boss,game_id='认领老板本人',level=35,flower='any',price_mode='any',price=None)).json()['id']
    aid=post(client,'/api/applications',dict(card_type='boss',card_id=bid,offered_team_id=team['id'],game_id='接单打手',level=70,contact={'wechat':'captain-wechat'},**challenge(client))).json()['id']
    booking=query(boss,[{'type':'boss','id':bid,'manage':token}])[0]
    assert booking['game_id']=='认领老板本人' and booking['application_id']==aid and booking['status']=='contacted'
    assert booking['access']=={'type':'boss','id':bid}
    assert query(client)==[]
    other=guest();signup(other,'registered_boss')
    applied=post(other,'/api/applications',dict(card_type='team',card_id=team['id'],game_id='登录老板',level=35,contact={'wechat':'login-boss'},**challenge(other)))
    assert applied.status_code==201,applied.text
    own=query(other)
    assert len(own)==1 and own[0]['game_id']=='登录老板' and own[0]['application_id']==applied.json()['id']
    assert other.post('/api/boss/bookings/query',json={'managed':[]},headers={'X-CSRF-Token':'invalid'}).status_code==403
