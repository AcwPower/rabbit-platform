from datetime import timedelta
import uuid
import pytest
from sqlalchemy import select
from app.db import Session, now
from app.models import PartnerCard, PartnerApplication, Contact, User
from app.maintenance import cleanup
from conftest import signup, guest, post, challenge

def data(client, **kw):
    return dict(kind='recruit',role='fighter',target_role='fighter',game_id='组队测试',level=90,
        map_name='',flower='any',level_min=60,level_max=150,start_time='20:00',end_time='02:00',
        contact={'wechat':'captain-test'},**challenge(client))|kw

def create(client, **kw):
    r=post(client,'/api/partners/cards',data(client,**kw));assert r.status_code==201,r.text;return r.json()

def apply(client,card,**kw):
    payload=dict(card_id=card['id'],role='fighter',game_id='申请角色',level=100,flower='none',
        contact={'wechat':'applicant-test'},**challenge(client))|kw
    return post(client,'/api/partners/applications',payload)

def invite(client,card,**kw):
    r=apply(client,card,**kw);assert r.status_code==201,r.text;return r.json()['id']

def change(client,id,action,payload=None):return post(client,f'/api/partners/applications/{id}/{action}',payload)
def get(client,id):return client.get(f'/api/partners/applications/{id}')

@pytest.mark.parametrize('owner_role,target',[('fighter','fighter'),('priest','fighter'),('fighter','priest'),('priest','priest')])
def test_recruit_roles_and_filters(client,owner_role,target):
    signup(client);card=create(client,role=owner_role,target_role=target)
    public=guest()
    listing=public.get(f'/api/partners/cards?kind=recruit&target_role={target}&at_time=01:00&level=100').json()
    assert listing['total']==1 and listing['items'][0]['id']==card['id']
    assert public.get('/api/partners/cards?at_time=10:00').json()['total']==0
    assert public.get('/api/partners/cards?level=20').json()['total']==0
    detail=public.get(f"/api/partners/cards/{card['id']}").json()
    assert detail['public_contact'] is None and 'contact' not in detail
    assert 'captain-test' not in str(listing)
    assert post(public,'/api/partners/cards',data(public)).status_code==401

@pytest.mark.parametrize('flower,currency,rate',[('active','rmb','12.50'),('afk','meso','1500000')])
def test_priest_job_and_inviter_captain(client,flower,currency,rate):
    signup(client,'求职祭司');card=create(client,kind='job',role='priest',target_role='any',flower=flower,hourly_rate=rate,price_currency=currency)
    captain=guest();signup(captain,'邀请队长');rid=invite(captain,card,role='priest',flower='active')
    assert get(captain,rid).json()['contacts'] is None
    assert change(captain,rid,'accept').status_code==403
    assert change(captain,rid,'join',{'wechat_confirmed':True}).status_code==409
    accepted=change(client,rid,'accept');assert accepted.status_code==200,accepted.text
    assert accepted.json()['status']=='accepted' and not accepted.json()['is_captain']
    assert change(client,rid,'join',{'wechat_confirmed':True}).status_code==403
    assert change(captain,rid,'join').status_code==422
    assert change(captain,rid,'join',{'wechat_confirmed':False}).status_code==422
    joined=change(captain,rid,'join',{'wechat_confirmed':True});assert joined.status_code==200,joined.text
    assert joined.json()['status']=='joined' and joined.json()['joined_at']
    assert get(client,rid).json()['status']=='joined'
    listing=guest().get(f'/api/partners/cards?kind=job&flower={flower}').json()
    assert listing['total']==1
    assert float(listing['items'][0]['hourly_rate'])==float(rate)

@pytest.mark.parametrize('changes',[{'role':'fighter'},{'flower':'any'},{'hourly_rate':None},{'price_currency':None},{'hourly_rate':0},{'price_currency':'meso','hourly_rate':'1.2'},{'target_role':'fighter'}])
def test_job_validation(client,changes):
    signup(client)
    payload=data(client,kind='job',role='priest',target_role='any',flower='active',hourly_rate='8.5',price_currency='rmb')|changes
    assert post(client,'/api/partners/cards',payload).status_code==422

def test_recruit_contact_join_and_revoke(client):
    signup(client);card=create(client,target_role='priest',flower='afk')
    applicant=guest();signup(applicant,'申请祭司')
    assert apply(applicant,card).status_code==409
    assert apply(applicant,card,role='priest',flower='active').status_code==409
    assert apply(applicant,card,role='priest',flower='afk',level=10).status_code==409
    rid=invite(applicant,card,role='priest',flower='afk')
    assert apply(applicant,card,role='priest',flower='afk').status_code==409
    stranger=guest();signup(stranger,'路人测试')
    assert get(stranger,rid).status_code==403
    assert change(stranger,rid,'accept').status_code==403
    assert get(client,rid).json()['contacts'] is None
    assert change(client,rid,'accept').json()['status']=='accepted'
    assert get(applicant,rid).json()['contacts']['publisher']['wechat']=='captain-test'
    assert change(applicant,rid,'join',{'wechat_confirmed':True}).status_code==403
    assert change(client,rid,'join',{'wechat_confirmed':True}).json()['status']=='joined'
    assert change(client,rid,'join',{'wechat_confirmed':True}).status_code==409
    assert change(applicant,rid,'cancel').status_code==200
    assert get(client,rid).json()['contacts'] is None
    with Session() as db:
        contact=db.scalar(select(Contact).where(Contact.resource=='partner',Contact.resource_id==card['id']))
        assert 'captain-test' not in contact.encrypted
        assert db.get(PartnerApplication,rid).active_key is None

def test_owner_version_status_and_expiry(client):
    signup(client);card=create(client)
    assert apply(client,card).status_code==409
    update=data(client,version=card['version'],map_name='王冠之地')
    headers={'X-Idempotency-Key':str(uuid.uuid4())}
    edited=client.put(f"/api/partners/cards/{card['id']}",json=update,headers=headers)
    assert edited.status_code==200,edited.text
    assert edited.json()['expires_at']==card['expires_at']
    assert edited.json()['created_at']==card['created_at']
    assert client.put(f"/api/partners/cards/{card['id']}",json=update,headers={'X-Idempotency-Key':str(uuid.uuid4())}).status_code==409
    update.update(version=2,role='priest')
    assert client.put(f"/api/partners/cards/{card['id']}",json=update,headers={'X-Idempotency-Key':str(uuid.uuid4())}).status_code==409
    a=guest();signup(a,'已同意队友');rid=invite(a,card);assert change(client,rid,'accept').status_code==200
    b=guest();signup(b,'待处理队友');pending=invite(b,card)
    assert post(client,f"/api/partners/cards/{card['id']}/status",{'action':'matched'}).status_code==200
    assert get(b,pending).json()['status']=='cancelled'
    assert change(client,rid,'join',{'wechat_confirmed':True}).status_code==200
    assert guest().get('/api/partners/cards').json()['total']==0

def test_deletion_replay_moderation_and_cleanup(client):
    me=signup(client);card=create(client)
    other=guest();signup(other,'队友隐私测试');rid=invite(other,card)
    key=str(uuid.uuid4());accept=f'/api/partners/applications/{rid}/accept'
    assert post(client,accept,headers={'X-Idempotency-Key':key}).status_code==200
    assert other.delete(f"/api/partners/contacts/partner/{card['id']}",headers={'X-Idempotency-Key':str(uuid.uuid4())}).status_code==403
    assert client.delete(f"/api/partners/contacts/partner/{card['id']}",headers={'X-Idempotency-Key':str(uuid.uuid4())}).status_code==200
    assert get(other,rid).json()['contacts']['publisher'] is None
    assert 'captain-test' not in post(client,accept,headers={'X-Idempotency-Key':key}).text
    report=post(other,'/api/reports',{'resource':'partner','resource_id':card['id'],'reason':'测试举报卡片内容',**challenge(other)})
    assert report.status_code==200,report.text
    with Session.begin() as db:db.get(User,me['id']).is_admin=True
    assert post(client,'/api/admin/moderate',{'resource':'partner','resource_id':card['id'],'action':'hide','reason':'测试隐藏原因'}).status_code==200
    assert get(other,rid).json()['contacts'] is None
    assert change(client,rid,'join',{'wechat_confirmed':True}).status_code==409
    assert other.get(f"/api/partners/cards/{card['id']}").status_code==404
    assert any(c['type']=='partner' for c in client.get('/api/admin/overview').json()['cards'])
    new=create(client)
    expired=invite(other,new)
    with Session.begin() as db:
        db.get(PartnerCard,new['id']).expires_at=now()-timedelta(days=8)
        db.get(PartnerApplication,expired).expires_at=now()-timedelta(days=8)
        for c in db.scalars(select(Contact)):c.expires_at=now()-timedelta(days=1)
    cleanup()
    assert get(other,expired).json()['status']=='expired'
    with Session() as db:
        assert db.get(PartnerApplication,expired).active_key is None
        assert db.get(PartnerCard,new['id']).status=='expired'
        assert all(not c.encrypted for c in db.scalars(select(Contact)))
