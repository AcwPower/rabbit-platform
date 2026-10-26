import uuid, io
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from sqlalchemy import select, func
from app.db import Session, now, engine
from app.models import TeamCard, BossCard, Application, Match, Contact, User, Review, Audit
from app.security import digest
from conftest import signup,post,challenge,guest,card_data,create_team,apply_guest

def accepted(owner,boss,card,name='老板测试'):
    app_id,token=apply_guest(boss,card,name)
    r=post(owner,f'/api/applications/{app_id}/accept');assert r.status_code==200,r.text
    return app_id,r.json()['match']['id'],token

def test_public_browsing_and_no_contact_leak(client):
    signup(client);card=create_team(client)
    c=guest();r=c.get('/api/team-cards');assert r.status_code==200
    assert 'captain-wechat' not in r.text
    detail=c.get(f'/api/team-cards/{card["id"]}').json()
    assert detail['public_contact'] is None and 'contact' not in detail

def test_login_and_csrf(client):
    signup(client);client.headers.pop('X-CSRF-Token')
    assert post(client,'/api/characters',{'name':'测试','level':30}).status_code==403
    client.headers['Origin']='https://evil.example'
    assert post(client,'/api/auth/logout').status_code==403

def test_unauthenticated_cannot_publish_team(client):
    assert post(client,'/api/team-cards',card_data(client)).status_code==401

def test_admin_role_does_not_bypass_character_review_flow(client):
    u=signup(client)
    with Session.begin() as db: db.get(User,u['id']).is_admin=True
    assert post(client,'/api/characters',{'name':'法师一','level':50}).status_code==403
    char=client.get('/api/me').json()['characters'][0]
    assert client.put(f"/api/admin/users/{u['id']}/characters/{char['id']}",json={'name':'法师一','level':50,'job':'法师','reason':'审核更正角色资料'},headers={'X-Idempotency-Key':str(uuid.uuid4())}).status_code==200
    assert len(client.get('/api/me').json()['characters'])==1
    create_team(client)
    assert client.get('/api/admin/overview').status_code==200

def test_anonymous_token_hashed_and_acl(client):
    signup(client);card=create_team(client);boss=guest();aid,token=apply_guest(boss,card)
    assert boss.get(f'/api/applications/{aid}').status_code==200
    stranger=guest();assert stranger.get(f'/api/applications/{aid}').status_code==403
    stranger.headers['X-Manage-Token']='x'*64
    assert stranger.get(f'/api/applications/{aid}').status_code==403
    with Session() as db:
        row=db.get(Application,aid);assert row.manage_hash==digest(token) and row.manage_hash!=token
        c=db.scalar(select(Contact).where(Contact.resource=='application'));assert 'boss-private' not in c.encrypted

def test_duplicate_and_self_apply(client):
    signup(client);card=create_team(client);boss=guest();apply_guest(boss,card)
    payload={'card_type':'team','card_id':card['id'],'game_id':'老板测试','level':35,'contact':{'wechat':'x'},**challenge(boss)}
    assert post(boss,'/api/applications',payload).status_code==409
    payload.update(challenge(client))
    assert post(client,'/api/applications',payload).json()['error']['code']=='SELF_APPLY'

def test_accept_does_not_reserve_and_contacts_authorized(client):
    signup(client);card=create_team(client);boss=guest();aid,mid,_=accepted(client,boss,card)
    assert client.get(f'/api/team-cards/{card["id"]}').json()['remaining']==1
    data=boss.get(f'/api/applications/{aid}').json();assert data['contacts']['publisher']['wechat']=='captain-wechat'
    assert post(boss,f'/api/matches/{mid}/board').status_code==403

def test_concurrent_last_seat_mysql(client):
    assert engine.dialect.name=='mysql'
    signup(client);card=create_team(client);b1,b2=guest(),guest()
    _,m1,_=accepted(client,b1,card,'老板一');_,m2,_=accepted(client,b2,card,'老板二')
    def board(mid):
        c=guest();c.cookies.update(client.cookies);c.headers['X-CSRF-Token']=client.headers['X-CSRF-Token']
        return post(c,f'/api/matches/{mid}/board').status_code
    with ThreadPoolExecutor(2) as pool: statuses=list(pool.map(board,[m1,m2]))
    assert sorted(statuses)==[200,409],statuses
    with Session() as db: assert db.get(TeamCard,card['id']).confirmed_boss_count==1

def test_captain_completes_without_boss_confirmation_and_one_review(client):
    signup(client);card=create_team(client);boss=guest();aid,mid,_=accepted(client,boss,card)
    assert post(client,f'/api/matches/{mid}/board').status_code==200
    assert post(boss,f'/api/matches/{mid}/complete').status_code==403
    assert post(boss,f'/api/reviews?match_id={mid}',{'tags':['刷怪稳定']}).status_code==409
    r=post(client,f'/api/matches/{mid}/complete');assert r.json()['status']=='completed'
    assert post(client,f'/api/matches/{mid}/complete').status_code==409
    assert post(boss,f'/api/reviews?match_id={mid}',{'tags':['刷怪稳定'],'body':'体验正常'}).status_code==200
    assert post(boss,f'/api/reviews?match_id={mid}',{'tags':['刷怪稳定']}).status_code==409
    with Session() as db: assert db.get(TeamCard,card['id']).confirmed_boss_count==0

def test_cancel_releases_once_and_audited(client):
    signup(client);card=create_team(client);boss=guest();aid,mid,_=accepted(client,boss,card)
    post(client,f'/api/matches/{mid}/board')
    assert post(boss,f'/api/matches/{mid}/cancel').status_code==200
    assert post(boss,f'/api/matches/{mid}/cancel').status_code==409
    with Session() as db:
        assert db.get(TeamCard,card['id']).confirmed_boss_count==0
        assert db.scalar(select(Audit.id).where(Audit.action=='match_cancel'))

def test_expired_application_rejected(client):
    signup(client);card=create_team(client);boss=guest();aid,_=apply_guest(boss,card)
    with Session.begin() as db: db.get(Application,aid).expires_at=now()-timedelta(seconds=1)
    assert post(client,f'/api/applications/{aid}/accept').status_code==409

def test_edit_does_not_bump_and_conflict_version(client):
    signup(client);card=create_team(client)
    data=card_data(client,version=card['version'],notes='更新内容')
    r=client.put(f'/api/team-cards/{card["id"]}',json=data,headers={'X-Idempotency-Key':str(uuid.uuid4())})
    assert r.status_code==200,r.text
    assert r.json()['created_at']==card['created_at'] and r.json()['expires_at']==card['expires_at']
    assert client.put(f'/api/team-cards/{card["id"]}',json=data,headers={'X-Idempotency-Key':str(uuid.uuid4())}).status_code==409

def test_numeric_and_flower_validation(client):
    signup(client)
    assert post(client,'/api/team-cards',card_data(client,exp_min=900000,exp_max=200000)).status_code==422
    assert post(client,'/api/team-cards',card_data(client,flower='active',priest_count=0)).status_code==400
    assert post(client,'/api/team-cards',card_data(client,capacity=2,fighter_count=2,priest_count=1,flower='active')).status_code==409

def test_idempotent_create_and_body_mismatch(client):
    signup(client);data=card_data(client);key=str(uuid.uuid4())
    r1=post(client,'/api/team-cards',data,headers={'X-Idempotency-Key':key})
    r2=post(client,'/api/team-cards',data,headers={'X-Idempotency-Key':key})
    assert r1.status_code==201 and r1.json()['id']==r2.json()['id']
    data['notes']='different'
    assert post(client,'/api/team-cards',data,headers={'X-Idempotency-Key':key}).status_code==409
    with Session() as db: assert db.scalar(select(func.count(TeamCard.id)))==1

def test_upload_rejects_spoofed_and_oversize(client):
    assert post(client,'/api/ocr/character',files={'file':('x.png',b'not an image','image/png')}).status_code==400
    assert post(client,'/api/ocr/character',files={'file':('x.png',b'0'*(5*1024*1024+1),'image/png')}).status_code==413

def test_ocr_failure_is_actionable(client,monkeypatch):
    import httpx
    async def unavailable(*args,**kw): raise httpx.ConnectError('test offline')
    monkeypatch.setattr(httpx.AsyncClient,'post',unavailable)
    b=io.BytesIO();Image.new('RGB',(10,10),'white').save(b,'PNG')
    r=post(client,'/api/ocr/character',files={'file':('test.png',b.getvalue(),'image/png')})
    assert r.status_code==503 and '手动填写' in r.json()['error']['message']

def test_report_admin_access_and_audit(client):
    user=signup(client);card=create_team(client)
    assert client.get('/api/admin/overview').status_code==403
    r=post(client,'/api/reports',{'resource':'team','resource_id':card['id'],'reason':'这是测试举报理由',**challenge(client)});assert r.status_code==200
    with Session.begin() as db: db.get(User,user['id']).is_admin=True
    assert post(client,'/api/admin/moderate',{'resource':'team','resource_id':card['id'],'action':'hide','reason':'核实测试违规内容'}).status_code==200
    assert guest().get(f'/api/team-cards/{card["id"]}').status_code==404
    assert len(client.get('/api/admin/overview').json()['audit'])>0

def test_contact_deletion_and_cleanup(client):
    signup(client);card=create_team(client);boss=guest();aid,mid,_=accepted(client,boss,card)
    r=client.delete(f'/api/contacts/team/{card["id"]}',headers={'X-Idempotency-Key':str(uuid.uuid4())});assert r.status_code==200
    assert boss.get(f'/api/applications/{aid}').json()['contacts']['publisher'] is None
    from app.maintenance import cleanup
    with Session.begin() as db:
        db.get(TeamCard,card['id']).expires_at=now()-timedelta(days=8)
        c=db.scalar(select(Contact).where(Contact.resource=='application'));c.expires_at=now()-timedelta(seconds=1)
    cleanup()
    with Session() as db:
        assert db.get(TeamCard,card['id']).status=='expired'
        c=db.scalar(select(Contact).where(Contact.resource=='application'));assert c.encrypted=='' and c.deleted_at

def test_anonymous_boss_card_is_claimed_without_owner_approval(client):
    boss=guest();boss.headers['X-Manage-Token']='a'*64
    data=card_data(boss,game_id='求车老板',level=35,flower='any',price_mode='any',price=None)
    r=post(boss,'/api/boss-cards',data);assert r.status_code==201,r.text;bid=r.json()['id']
    signup(client);team=create_team(client)
    data={'card_type':'boss','card_id':bid,'offered_team_id':team['id'],'game_id':'接单打手','level':70,'contact':{'wechat':'captain-wechat'},**challenge(client)}
    r=post(client,'/api/applications',data);assert r.status_code==201,r.text
    aid=r.json()['id'];assert r.json()['claimed'] is True
    assert boss.get(f'/api/boss-cards/{bid}').json()['status']=='matched'
    assert client.get(f'/api/applications/{aid}').json()['contacts']['publisher']['wechat']=='captain-wechat'
    assert post(boss,f'/api/applications/{aid}/accept').status_code==409

def test_filter_overnight(client):
    signup(client);create_team(client)
    assert client.get('/api/team-cards?at_time=01:00').json()['total']==1
    assert client.get('/api/team-cards?at_time=12:00').json()['total']==0

def test_replay_challenge(client):
    data=card_data(client);signup(client)
    assert post(client,'/api/team-cards',data).status_code==201
    assert post(client,'/api/team-cards',data).status_code==400


def test_large_qr_roundtrip_and_public_edit(client):
    import base64, io, random
    from PIL import Image
    from qr_helpers import qr_image
    signup(client)
    image=Image.frombytes('RGB',(480,480),random.Random(42).randbytes(480*480*3))
    code=qr_image();image.paste(code,((480-code.width)//2,(480-code.height)//2))
    stream=io.BytesIO();image.save(stream,format='PNG')
    qr='data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()
    card=create_team(client,contact={'wechat':'qr-owner','qr':qr},public_contact=True)
    with Session() as db:
        saved=db.scalar(select(Contact).where(Contact.resource=='team'))
        assert len(saved.encrypted)>65535
    visible=guest().get(f'/api/team-cards/{card["id"]}').json()
    assert visible['public_contact']['qr'].startswith('data:image/')
    response=client.put(f'/api/team-cards/{card["id"]}',json=card_data(client,version=card['version'],contact={'wechat':'qr-owner','qr':qr},public_contact=True),headers={'X-Idempotency-Key':str(uuid.uuid4())})
    assert response.status_code==200,response.text


def test_idempotency_never_retains_private_contacts(client):
    from app.models import RequestKey
    from app.security import cipher
    signup(client);card=create_team(client);boss=guest();aid,_=apply_guest(boss,card)
    key=str(uuid.uuid4())
    response=post(client,f'/api/applications/{aid}/accept',headers={'X-Idempotency-Key':key})
    assert response.json()['contacts']['applicant']['wechat']=='boss-private'
    replay=post(client,f'/api/applications/{aid}/accept',headers={'X-Idempotency-Key':key})
    assert replay.json()['contacts'] is None
    with Session() as db:
        for entry in db.scalars(select(RequestKey).where(RequestKey.status_code>0)):
            raw=cipher.decrypt(entry.response.encode()).decode()
            assert 'boss-private' not in raw and 'captain-wechat' not in raw
