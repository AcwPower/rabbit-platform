from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from sqlalchemy import select,func
from app.db import Session
from app.models import Application,Match,TeamCard,BossCard,ApplicationNotification
from conftest import signup,create_team,guest,post,card_data,challenge


def boss_card():
    boss=guest();token=uuid4().hex+uuid4().hex;boss.headers['X-Manage-Token']=token
    response=post(boss,'/api/boss-cards',card_data(boss,game_id='claim-boss',level=35,notes='请先微信确认地图集合位置',flower='any',price_mode='any',price=None,contact={'wechat':'private-boss-claim'},public_contact=True))
    assert response.status_code==201,response.text
    return boss,response.json(),[{'type':'boss','id':response.json()['id'],'manage':token}]


def payload(client,card,team):
    return dict(card_type='boss',card_id=card['id'],offered_team_id=team['id'],game_id=team['game_id'],level=team['level'],contact={'wechat':'captain-wechat'},**challenge(client))


def test_first_claim_immediately_opens_contacts_and_notifies_only_boss(client):
    signup(client);team=create_team(client);boss,card,records=boss_card()
    assert guest().get(f"/api/boss-cards/{card['id']}").json()['public_contact'] is None
    claimed=post(client,'/api/applications',payload(client,card,team))
    assert claimed.status_code==201 and claimed.json()['claimed'],claimed.text
    aid=claimed.json()['id'];detail=client.get(f'/api/applications/{aid}').json()
    assert detail['status']=='accepted' and detail['match']['status']=='contacted'
    assert detail['match']['planned_start_at'] and detail['match']['expected_end_at']
    bookings=post(boss,'/api/boss/bookings/query',{'managed':records}).json()['bookings']
    assert bookings[0]['expected_end_at']==detail['match']['expected_end_at']
    assert detail['contacts']['publisher']['wechat']=='private-boss-claim'
    assert client.get('/api/captain/teams').json()['teams'][0]['members'][0]['notes']=='请先微信确认地图集合位置'
    assert client.get(f"/api/team-cards/{team['id']}").json()['remaining']==team['remaining']
    assert guest().get(f'/api/applications/{aid}').status_code==403
    notices=post(boss,'/api/notifications/query',{'managed':records}).json()
    assert notices['counts']=={'applications':0,'partners':0,'updates':1}
    notice=notices['updates'][0]
    assert notice['event']=='claimed' and notice['side']=='owner'
    assert notice['access']=={'type':'boss','id':card['id']}
    assert 'private-boss-claim' not in str(notices)
    assert post(guest(),'/api/notifications/query',{'managed':[]}).json()['total']==0
    assert post(boss,'/api/notifications/read',{'managed':records,'ids':[notice['id']]}).json()['read']==1
    assert post(boss,'/api/notifications/query',{'managed':records}).json()['total']==0
    assert client.get('/api/boss-cards').json()['total']==0
    assert post(boss,f"/api/matches/{detail['match']['id']}/board").status_code==403
    assert post(client,f"/api/matches/{detail['match']['id']}/board").status_code==200
    assert post(client,f"/api/matches/{detail['match']['id']}/complete").status_code==200
    assert post(boss,'/api/notifications/query',{'managed':records}).json()['updates'][0]['event']=='completed'


def test_competing_captains_have_exactly_one_winner_and_one_private_contact_reader(client):
    signup(client,'claim_captain_one');one=create_team(client)
    other=guest();signup(other,'claim_captain_two');two=create_team(other)
    boss,card,_=boss_card();p1=payload(client,card,one);p2=payload(other,card,two)
    barrier=Barrier(2)
    def claim(c,p):
        barrier.wait(timeout=10)
        return post(c,'/api/applications',p)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(claim,client,p1);second=pool.submit(claim,other,p2)
        responses=[first.result(),second.result()]
    assert sorted(r.status_code for r in responses)==[201,409],[r.text for r in responses]
    winner=next(i for i,r in enumerate(responses) if r.status_code==201)
    clients=[client,other];aid=responses[winner].json()['id']
    assert clients[winner].get(f'/api/applications/{aid}').json()['contacts']['publisher']['wechat']=='private-boss-claim'
    assert clients[1-winner].get(f'/api/applications/{aid}').status_code==403
    assert responses[1-winner].json()['error']['code']=='BOSS_CLAIMED'
    with Session() as db:
        assert db.scalar(select(func.count(Application.id)).where(Application.boss_card_id==card['id']))==1
        assert db.scalar(select(func.count(Match.id)))==1
        assert db.scalar(select(func.count(ApplicationNotification.id)).where(ApplicationNotification.event=='claimed'))==1
        assert db.get(BossCard,card['id']).status=='matched'
        assert db.get(TeamCard,one['id']).confirmed_boss_count==db.get(TeamCard,two['id']).confirmed_boss_count==0


def test_claim_replay_does_not_duplicate_and_cancel_revokes_contact_then_reopens_card(client):
    signup(client);team=create_team(client);boss,card,_=boss_card()
    key=str(uuid4());data=payload(client,card,team)
    first=post(client,'/api/applications',data,headers={'X-Idempotency-Key':key})
    assert first.status_code==201,first.text
    replay=post(client,'/api/applications',data,headers={'X-Idempotency-Key':key})
    assert replay.json()==first.json()
    aid=first.json()['id'];mid=client.get(f'/api/applications/{aid}').json()['match']['id']
    assert post(client,f'/api/matches/{mid}/cancel').status_code==200
    assert client.get(f'/api/applications/{aid}').json()['contacts'] is None
    assert boss.get(f"/api/boss-cards/{card['id']}").json()['status']=='active'
    other=guest();signup(other,'claim_after_cancel');second=create_team(other)
    second_claim=post(other,'/api/applications',payload(other,card,second));assert second_claim.status_code==201,second_claim.text
    assert client.get(f"/api/applications/{second_claim.json()['id']}").status_code==403
    assert client.get(f'/api/applications/{aid}').json()['contacts'] is None


def test_unqualified_team_cannot_lock_boss_or_get_contact(client):
    signup(client);team=create_team(client,level_min=80,level_max=100);boss,card,_=boss_card()
    result=post(client,'/api/applications',payload(client,card,team))
    assert result.status_code==409 and result.json()['error']['code']=='LEVEL_MISMATCH'
    assert boss.get(f"/api/boss-cards/{card['id']}").json()['status']=='active'
    other=guest();signup(other,'not_the_team_owner')
    assert post(other,'/api/applications',payload(other,card,team)).status_code==403
    assert post(guest(),'/api/applications',payload(guest(),card,team)).status_code==401
    with Session() as db:
        assert db.scalar(select(func.count(Application.id)).where(Application.boss_card_id==card['id']))==0
