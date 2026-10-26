import uuid
from sqlalchemy import select,func
from app.db import Session
from app.models import ApplicationNotification
from conftest import signup,create_team,guest,apply_guest,post,card_data,challenge


def query(client,managed=()):
    response=post(client,'/api/notifications/query',{'managed':list(managed)})
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    return response.json()


def test_guest_boss_gets_accept_and_board_progress_and_persistent_read(client):
    signup(client);team=create_team(client)
    boss=guest();aid,token=apply_guest(boss,team)
    records=[{'type':'application','id':aid,'manage':token}]
    assert query(boss,records)['total']==0
    match=post(client,f'/api/applications/{aid}/accept').json()['match']
    result=query(boss,records)
    assert result['counts']['updates']==1 and result['updates'][0]['event']=='accepted'
    notice=result['updates'][0]
    assert notice['side']=='applicant' and notice['application_id']==aid
    assert 'boss-private' not in str(result) and token not in str(result)
    assert query(guest())['total']==0
    assert query(guest(),[records[0]|{'manage':'x'*64}])['total']==0
    assert post(guest(),'/api/notifications/read',{'ids':[notice['id']]}).json()['read']==0
    assert post(boss,'/api/notifications/read',{'managed':records,'ids':[notice['id']]}).json()['read']==1
    assert query(guest(),records)['total']==0  # A second browser with the same management link sees the read state.
    assert post(client,f"/api/matches/{match['id']}/board").status_code==200
    result=query(boss,records)
    assert result['total']==1 and result['updates'][0]['event']=='boarded'
    assert result['updates'][0]['id']>notice['id']
    # Invalid duplicate action cannot generate another boarding notice.
    assert post(client,f"/api/matches/{match['id']}/board").status_code==409
    assert query(boss,records)['total']==1
    assert post(boss,'/api/notifications/read',{'managed':records,'ids':[result['updates'][0]['id']]}).json()['read']==1
    assert query(boss,records)['total']==0


def test_logged_in_applicant_progress_is_private(client):
    signup(client);team=create_team(client)
    boss=guest();signup(boss,'老板账号')
    data=dict(card_type='team',card_id=team['id'],game_id='登录老板',level=35,contact={'wechat':'login-boss'},**challenge(boss))
    result=post(boss,'/api/applications',data);assert result.status_code==201,result.text
    aid=result.json()['id']
    accepted=post(client,f'/api/applications/{aid}/accept').json()
    assert boss.get('/api/notifications').json()['updates'][0]['event']=='accepted'
    assert client.get('/api/notifications').json()['total']==0
    stranger=guest();signup(stranger,'另一老板')
    assert stranger.get('/api/notifications').json()['total']==0
    assert post(client,f"/api/matches/{accepted['match']['id']}/board").status_code==200
    notices=boss.get('/api/notifications').json()['updates']
    assert [n['event'] for n in notices]==['boarded','accepted']
    assert post(stranger,'/api/notifications/read',{'ids':[n['id'] for n in notices]}).json()['read']==0
    assert post(boss,'/api/notifications/read',{'ids':[n['id'] for n in notices]}).json()['read']==2
    assert boss.get('/api/notifications').json()['total']==0


def test_guest_boss_card_owner_has_claimed_and_boarding_notice(client):
    signup(client);team=create_team(client,capacity=3)
    boss=guest();token=uuid.uuid4().hex+uuid.uuid4().hex;boss.headers['X-Manage-Token']=token
    card=post(boss,'/api/boss-cards',card_data(boss,game_id='求带老板',level=35,flower='any',price_mode='any',price=None)).json()
    records=[{'type':'boss','id':card['id'],'manage':token}]
    data=dict(card_type='boss',card_id=card['id'],offered_team_id=team['id'],game_id='打手',level=70,contact={'wechat':'captain-wechat'},**challenge(client))
    applied=post(client,'/api/applications',data);assert applied.status_code==201,applied.text
    aid=applied.json()['id']
    pending=query(boss,records)
    assert pending['counts']['applications']==0 and pending['latest'][0]['access']=={'type':'boss','id':card['id']}
    assert pending['updates'][0]['event']=='claimed'
    accepted=client.get(f'/api/applications/{aid}');assert accepted.status_code==200,accepted.text
    assert client.get('/api/notifications').json()['total']==0
    assert post(client,f"/api/matches/{accepted.json()['match']['id']}/board").status_code==200
    result=query(boss,records)
    assert result['updates'][0]['event']=='boarded' and result['updates'][0]['side']=='owner'
    assert result['updates'][0]['access']=={'type':'boss','id':card['id']}
    assert query(guest(),[records[0]|{'id':card['id']+1}])['total']==0
    # A token authorizes only its original record, not other guest applications.
    other=guest();other_id,_=apply_guest(other,team,'其他老板')
    assert query(boss,[records[0]|{'type':'application','id':other_id}])['total']==0
    with Session() as db:
        assert db.scalar(select(func.count(ApplicationNotification.id)).where(ApplicationNotification.application_id==aid))==2


def test_notification_query_still_checks_origin_csrf_and_does_not_store_poll_keys(client):
    from app.models import RequestKey
    signup(client)
    with Session() as db:before=db.scalar(select(func.count(RequestKey.key_hash)))
    for _ in range(3):assert query(client)['total']==0
    with Session() as db:assert db.scalar(select(func.count(RequestKey.key_hash)))==before
    assert client.post('/api/notifications/query',json={'managed':[]},headers={'Origin':'https://unrelated.example'}).status_code==403
    assert client.post('/api/notifications/query',json={'managed':[]},headers={'X-CSRF-Token':'invalid'}).status_code==403
