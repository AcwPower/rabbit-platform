import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from app.db import Session, now
from app.models import Application, PartnerCard, PartnerApplication, AccountContact, Contact, User, Character, RegistrationProof, Audit, Report
from app.security import cipher
from conftest import signup, create_team, guest, apply_guest, post, card_data

def put(client, path, data):
    return client.put(path, json=data, headers={'X-Idempotency-Key': str(uuid.uuid4())})

def test_notifications_are_private_and_follow_request_lifecycle(client):
    signup(client); card=create_team(client)
    boss=guest(); aid,_=apply_guest(boss,card)
    assert guest().get('/api/notifications').status_code==401
    outsider=guest(); signup(outsider,'无关用户')
    assert outsider.get('/api/notifications').json()['total']==0
    response=client.get('/api/notifications'); result=response.json()
    assert result['total']==1 and result['counts']=={'applications':1,'partners':0,'updates':0}
    assert result['latest'][0]['key']==f'application:{aid}'
    assert result['latest'][0]['label']=='上车申请'
    assert 'boss-private' not in response.text and 'contacts' not in response.text
    assert response.headers['cache-control']=='no-store'
    assert post(boss,f'/api/applications/{aid}/cancel').status_code==200
    cancel_notice=client.get('/api/notifications').json()
    assert cancel_notice['counts']['applications']==0 and cancel_notice['updates'][0]['event']=='cancelled'
    assert post(client,'/api/notifications/read',{'ids':[cancel_notice['updates'][0]['id']]}).json()['read']==1
    second,_=apply_guest(boss,card,'另一老板')
    assert client.get('/api/notifications').json()['latest'][0]['id']==second
    assert post(client,f'/api/applications/{second}/reject').status_code==200
    assert client.get('/api/notifications').json()['total']==0
    third,_=apply_guest(boss,card,'第三老板')
    assert post(client,f'/api/applications/{third}/accept').status_code==200
    assert client.get('/api/notifications').json()['total']==0

def test_notification_counts_not_capped_and_unavailable_excluded(client):
    owner=signup(client); card=create_team(client)
    with Session.begin() as db:
        applicant=User(username='partner-user',password_hash='unused');db.add(applicant);db.flush()
        for i in range(110):db.add(Application(card_type='team',team_card_id=card['id'],game_id=f'老板{i}',level=30,expires_at=now()+timedelta(hours=1)))
        db.add(Application(card_type='team',team_card_id=card['id'],game_id='过期老板',level=30,expires_at=now()-timedelta(seconds=1)))
        partner=PartnerCard(owner_id=owner['id'],kind='recruit',role='fighter',target_role='fighter',game_id='队长',level=90,start_time='20:00',end_time='02:00',expires_at=now()+timedelta(hours=1))
        db.add(partner);db.flush();pid=partner.id
        db.add(PartnerApplication(card_id=pid,applicant_id=applicant.id,role='fighter',game_id='队友',level=90,expires_at=now()+timedelta(hours=1)))
    result=client.get('/api/notifications').json()
    assert result['total']==111 and result['counts']=={'applications':110,'partners':1,'updates':0}
    assert len(result['latest'])==21 and len({r['key'] for r in result['latest']})==21
    with Session.begin() as db:db.get(PartnerCard,pid).status='hidden'
    assert client.get('/api/notifications').json()['counts']['partners']==0
    assert post(client,f'/api/team-cards/{card["id"]}/status',{'action':'close'}).status_code==200
    assert client.get('/api/notifications').json()['total']==0

def test_contact_interval_cannot_be_bypassed_by_cards_and_sync_is_private(client):
    owner=signup(client);card=create_team(client)
    first=client.get('/api/profile').json()
    assert first['contact']['wechat']=='captain-wechat' and not first['can_edit_contact']
    assert put(client,'/api/profile/contact',{'wechat':'changed-wechat'}).status_code==429
    old_time=first['contact_changed_at']
    assert put(client,'/api/profile/contact',first['contact']).json()['contact_changed_at']==old_time
    assert post(client,'/api/team-cards',card_data(client,game_id='新卡片',contact={'wechat':'bypass'})).json()['error']['code']=='CONTACT_PROFILE_REQUIRED'
    assert put(client,f'/api/team-cards/{card["id"]}',card_data(client,version=card['version'],contact={'wechat':'bypass'})).status_code==409
    with Session.begin() as db:
        db.get(AccountContact,owner['id']).changed_at=now()-timedelta(days=7)
        # Deleted snapshots must stay deleted after changing the profile.
        db.add(Contact(resource='application',resource_id=99999,encrypted='',deleted_at=now(),expires_at=now()+timedelta(days=1)))
    changed=put(client,'/api/profile/contact',{'wechat':'new-account-wechat'})
    assert changed.status_code==200 and not changed.json()['can_edit_contact']
    assert client.get(f'/api/team-cards/{card["id"]}').json()['contact']['wechat']=='new-account-wechat'
    assert 'new-account-wechat' not in guest().get(f'/api/team-cards/{card["id"]}').text
    with Session() as db:
        profile=db.get(AccountContact,owner['id'])
        assert 'new-account-wechat' not in profile.encrypted
        assert 'new-account-wechat' in cipher.decrypt(profile.encrypted.encode()).decode()
        assert all('new-account-wechat' not in a.detail for a in db.scalars(select(Audit)))
    assert put(client,'/api/profile/contact',{'wechat':'another'}).status_code==429

def test_profile_first_save_concurrency_and_authenticated_scope(client):
    user=signup(client)
    assert guest().get('/api/profile').status_code==401
    assert guest().put('/api/profile/contact',json={'wechat':'x'},headers={'X-Idempotency-Key':str(uuid.uuid4())}).status_code==401
    clients=[guest(),guest()]
    for c in clients:c.cookies.update(client.cookies);c.headers['X-CSRF-Token']=client.headers['X-CSRF-Token']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda pair:put(pair[0],'/api/profile/contact',{'wechat':pair[1]}).status_code,zip(clients,['first','second'])))
    assert sorted(results)==[200,429]
    stranger=guest();signup(stranger,'另一账号')
    assert stranger.get('/api/profile').json()['contact'] is None
    assert put(client,'/api/profile/contact',{'wechat':'x','user_id':user['id']}).status_code==422

def test_character_is_admin_only_with_request_and_audit(client):
    user=signup(client);character=client.get('/api/me').json()['characters'][0]
    assert post(client,'/api/characters',{'name':'绕过审核','level':100}).status_code==403
    assert client.delete(f'/api/characters/{character["id"]}',headers={'X-Idempotency-Key':str(uuid.uuid4())}).status_code==403
    payload={'name':'正确角色','level':116,'job':'龙骑士','reason':'核实截图中的角色信息'}
    path=f'/api/admin/users/{user["id"]}/characters/{character["id"]}'
    assert put(client,path,payload).status_code==403
    assert client.get(f'/api/admin/users/{user["id"]}/characters').status_code==403
    request=post(client,'/api/profile/character-request',payload)
    assert request.status_code==200
    assert post(client,'/api/profile/character-request',payload).status_code==409
    assert client.get('/api/me').json()['characters'][0]==character
    moderator=guest();admin_user=signup(moderator,'资料管理员')
    with Session.begin() as db:db.get(User,admin_user['id']).is_admin=True
    assert put(moderator,path,payload).status_code==200
    updated=client.get('/api/me').json()['characters'][0]
    assert (updated['name'],updated['level'],updated['job'])==('正确角色',116,'龙骑士')
    wrong_path=f'/api/admin/users/{admin_user["id"]}/characters/{character["id"]}'
    assert put(moderator,wrong_path,payload).status_code==404
    with Session() as db:
        assert db.get(RegistrationProof,user['id']).game_id=='注册角色'
        assert db.scalar(select(Audit.id).where(Audit.action=='admin_character_changed'))
        assert db.get(Report,request.json()['id']).resource_id==user['id']

def test_qr_profile_validation_still_enforced(client):
    from test_qr import image_url
    from PIL import Image
    signup(client)
    r=put(client,'/api/profile/contact',{'qr':image_url(Image.new('RGB',(100,100),'white'))})
    assert r.status_code==422 and '上传图片非二维码' in r.text
    assert client.get('/api/profile').json()['contact'] is None

def test_v1_hides_teammate_feature_and_preserves_existing_data(client,monkeypatch):
    from app.config import settings
    user=signup(client)
    card=create_team(client,boss_slots=3,teammate_need='priest')
    pid=card['teammate_recruitment_id']
    with Session.begin() as db:
        applicant=User(username='pending-partner',password_hash='unused');db.add(applicant);db.flush()
        db.add(PartnerApplication(card_id=pid,applicant_id=applicant.id,role='priest',flower='active',game_id='祭司',level=90,expires_at=now()+timedelta(hours=1)))
    assert client.get('/api/notifications').json()['counts']['partners']==1
    monkeypatch.setattr(settings,'teammate_recruitment_enabled',False)
    assert client.get('/api/meta').json()['features']['teammate_recruitment'] is False
    assert client.get('/api/meta').json()['partners']==0
    assert client.get('/api/partners/cards').status_code==404
    assert client.get('/api/partners/me').status_code==404
    assert client.get('/api/notifications').json()['counts']['partners']==0
    assert post(client,'/api/team-cards',card_data(client,teammate_need='priest')).status_code==409
    edited=put(client,f'/api/team-cards/{card["id"]}',card_data(client,boss_slots=3,version=card['version'],map_name='隐藏功能后编辑'))
    assert edited.status_code==200,edited.text
    assert edited.json()['remaining']==3 and edited.json()['teammate_recruitment_id']==pid
    new=create_team(client)
    assert new['teammate_need']=='none' and new['teammate_recruitment_id'] is None
    with Session() as db:
        assert db.get(PartnerCard,pid).status=='active'
        assert db.scalar(select(PartnerApplication).where(PartnerApplication.card_id==pid)).status=='pending'

def test_other_accounts_cannot_spoof_character_change_requests(client):
    user=signup(client)
    with Session.begin() as db:
        db.add(Report(resource='appeal',resource_id=user['id'],reporter_hash='unrelated',reason='角色资料修改申请：伪造申请'))
    assert client.get('/api/profile').json()['character_requests']==[]
    assert post(client,'/api/profile/character-request',{'name':'我的角色','level':78,'job':'大副','reason':'本人请求更正角色'}).status_code==200
