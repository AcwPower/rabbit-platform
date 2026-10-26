import base64, io, json
import httpx
import pytest
from fastapi import HTTPException
from PIL import Image, PngImagePlugin
from sqlalchemy import select, func
from app.db import Session
from app.models import User, RegistrationProof, Character, Challenge, Audit
from app.security import cipher, hash_password
from app.ocr_engine import character_panel, character_fields, personal_fields, personal_region
from app.registration import prepare_screenshot
from conftest import challenge, signup, guest, post

GOOD={'character_panel':True,'game_id':'注册小白兔','level':78,'job':'大副',
      'confidence':{'game_id':.99,'level':.99,'job':.99}}

def picture(size=(400,600),fmt='PNG'):
    image=Image.new('RGB',size,'white');out=io.BytesIO()
    metadata=PngImagePlugin.PngInfo();metadata.add_text('private-test','must-not-persist')
    image.save(out,format=fmt,**({'pnginfo':metadata} if fmt=='PNG' else {}))
    return out.getvalue()

def register(client,raw=None,name='新打手测试',credentials=None):
    return client.post('/api/auth/register',data={'credentials':json.dumps(credentials or
        {'username':name,'password':'Test-password-92841',**challenge(client)})},
        files={'screenshot':('image.png',picture() if raw is None else raw,'image/png')})

def ocr_response(monkeypatch,result=None,status=200):
    async def fake(*args,**kwargs):return httpx.Response(status,json=GOOD if result is None else result)
    monkeypatch.setattr(httpx.AsyncClient,'post',fake)

def assert_no_registration():
    with Session() as db:
        assert db.scalar(select(func.count(User.id)))==0
        assert db.scalar(select(func.count(RegistrationProof.user_id)))==0
        assert db.scalar(select(func.count(Character.id)))==0

def test_screenshot_cannot_be_omitted_or_replaced_by_client_claim(client):
    data={'username':'新打手测试','password':'Test-password-92841',**challenge(client)}
    r=client.post('/api/auth/register',data={'credentials':json.dumps(data)})
    assert r.status_code==422 and r.json()['error']['code']=='CHARACTER_SCREENSHOT_REQUIRED'
    assert post(client,'/api/auth/register',data|{'game_id':'伪造','level':78,'character_panel':True}).status_code==422
    assert_no_registration()

@pytest.mark.parametrize('raw,status',[ (b'not-an-image',422),(picture((1,1)),422),
    (picture(fmt='GIF'),422),(b'x'*(5*1024*1024+1),413)])
def test_bad_files_are_rejected_before_ocr(client,monkeypatch,raw,status):
    async def unexpected(*args,**kwargs):pytest.fail('Invalid images must not reach OCR')
    monkeypatch.setattr(httpx.AsyncClient,'post',unexpected)
    assert register(client,raw).status_code==status
    assert_no_registration()

@pytest.mark.parametrize('changes',[
    {'character_panel':False},{'character_panel':None},{'game_id':''},{'level':301},{'level':True},{'job':''},
    {'confidence':{'game_id':.60,'level':.99,'job':.99}},
    {'confidence':{'game_id':.99,'level':.70,'job':.99}},
])
def test_unrelated_partial_and_unclear_images_fail_closed(client,monkeypatch,changes):
    ocr_response(monkeypatch,GOOD|changes)
    r=register(client)
    assert r.status_code==422 and r.json()['error']['code']=='CHARACTER_IMAGE_REJECTED'
    assert_no_registration()

@pytest.mark.parametrize('status',[429,500])
def test_ocr_unavailable_does_not_create_account(client,monkeypatch,status):
    ocr_response(monkeypatch,status=status)
    assert register(client).status_code==503
    assert_no_registration()

def test_timeout_and_consumed_challenge(client,monkeypatch):
    async def timeout(*args,**kwargs):raise httpx.ReadTimeout('test')
    monkeypatch.setattr(httpx.AsyncClient,'post',timeout)
    data={'username':'新打手测试','password':'Test-password-92841',**challenge(client)}
    assert register(client,credentials=data).status_code==503
    with Session() as db:assert db.get(Challenge,data['challenge_id']).used
    assert register(client,credentials=data).json()['error']['code']=='CHALLENGE_EXPIRED'
    assert_no_registration()

def test_registration_image_encrypted_linked_and_private(client,monkeypatch):
    ocr_response(monkeypatch)
    r=register(client);assert r.status_code==200,r.text
    uid=r.json()['user']['id']
    client.cookies.set('rabbit_session',r.cookies.get('rabbit_session'),path='/')
    client.headers['X-CSRF-Token']=r.json()['csrf']
    path=f'/api/users/{uid}/registration-proof'
    with Session() as db:
        proof=db.get(RegistrationProof,uid)
        assert proof.game_id==GOOD['game_id'] and proof.level==78 and proof.job=='大副'
        assert not proof.encrypted_image.startswith('data:') and 'must-not-persist' not in proof.encrypted_image
        jpeg=cipher.decrypt(proof.encrypted_image.encode())
        assert jpeg.startswith(b'\xff\xd8') and b'must-not-persist' not in jpeg
        character=db.scalar(select(Character).where(Character.user_id==uid))
        assert character.name==proof.game_id
    me=client.get('/api/me').json();assert me['has_registration_proof'] and len(me['characters'])==1
    assert 'image' not in me
    own=client.get(path);assert own.status_code==200 and own.headers['cache-control']=='no-store'
    assert base64.b64decode(own.json()['image'].split(',')[1])==jpeg
    stranger=guest();assert stranger.get(path).status_code==401
    another=signup(stranger,'另一个打手')
    assert stranger.get(path).status_code==403
    with Session.begin() as db:db.get(User,another['id']).is_admin=True
    assert stranger.get(path).status_code==200
    overview=stranger.get('/api/admin/overview').json()
    assert next(u for u in overview['users'] if u['id']==uid)['has_registration_proof']
    assert 'data:image' not in json.dumps(overview)
    with Session() as db:
        assert db.scalar(select(Audit).where(Audit.action=='view_registration_image',Audit.resource==f'user:{uid}'))
    with Session.begin() as db:db.get(User,uid).status='banned'
    assert client.get(path).status_code==401

def test_duplicate_username_does_not_add_image_or_character(client,monkeypatch):
    ocr_response(monkeypatch)
    assert register(client).status_code==200
    assert register(guest()).status_code==409
    with Session() as db:
        assert db.scalar(select(func.count(RegistrationProof.user_id)))==1
        assert db.scalar(select(func.count(Character.id)))==1

def test_failed_transaction_leaves_no_partial_account(client,monkeypatch):
    ocr_response(monkeypatch)
    def fail_session(*args):raise HTTPException(503,'injected test failure')
    monkeypatch.setattr('app.main.set_session',fail_session)
    assert register(client).status_code==503
    assert_no_registration()

def test_existing_account_login_unchanged(client):
    with Session.begin() as db:db.add(User(username='历史账号',password_hash=hash_password('Test-password-92841')))
    r=post(client,'/api/auth/login',{'username':'历史账号','password':'Test-password-92841',**challenge(client)})
    assert r.status_code==200
    client.cookies.set('rabbit_session',r.cookies.get('rabbit_session'),path='/')
    assert not client.get('/api/me').json()['has_registration_proof']

def row(text,y,x=10,width=90):
    return {'text':text,'score':.99,'box':[[x,y],[x+width,y],[x+width,y+30],[x,y+30]]}

def test_panel_requires_real_labels_in_alignment_not_injected_heading():
    rows=[row('角色能力',0,width=140),row('名字',50),row('職業',100),row('等級',150),row('血量',200),row('魔量',250),row('敏捷',300)]
    assert character_panel(rows)
    assert not character_panel(rows[1:])
    assert not character_panel(rows[:4])
    assert not character_panel(rows[:6])
    assert not character_panel([rows[0]]+[row(r['text'],i*50+50,x=1000) for i,r in enumerate(rows[1:])])
    fields=character_fields(rows+[row('测试角色',50,x=150),row('大副',100,x=150),row('78',150,x=150)])
    assert fields['level']==78 and fields['job']=='大副'

def test_normalization_removes_metadata_and_limits_resolution():
    raw=prepare_screenshot(picture((3000,2000)))
    with Image.open(io.BytesIO(raw)) as image:
        assert max(image.size)==2000 and image.format=='JPEG'
        assert 'private-test' not in image.info

@pytest.mark.parametrize('panel',['ability','personal'])
def test_only_ability_panel_is_sufficient_for_registration(client,monkeypatch,panel):
    candidate={**GOOD,'panel_type':panel,'panel_detected':True}
    ocr_response(monkeypatch,{'registration_candidates':[candidate]})
    assert register(client).status_code==(200 if panel=='ability' else 422)

def test_personal_panel_cannot_rescue_unclear_ability_panel(client,monkeypatch):
    unclear={**GOOD,'panel_type':'ability','panel_detected':True,'confidence':{'game_id':.4,'level':1,'job':1}}
    personal={**GOOD,'panel_type':'personal','panel_detected':True}
    ocr_response(monkeypatch,{'registration_candidates':[unclear,personal]})
    assert register(client).status_code==422
    assert_no_registration()

def test_both_panels_pass_only_when_ability_panel_is_valid(client,monkeypatch):
    ability={**GOOD,'panel_type':'ability','panel_detected':True}
    personal={**GOOD,'panel_type':'personal','panel_detected':True,'game_id':'别人的角色','level':13}
    ocr_response(monkeypatch,{'registration_candidates':[personal,ability]})
    r=register(client);assert r.status_code==200
    with Session() as db:
        proof=db.get(RegistrationProof,r.json()['user']['id'])
        assert proof.game_id==GOOD['game_id'] and proof.level==78

def test_never_mix_partial_fields_across_panels(client,monkeypatch):
    ability={**GOOD,'panel_type':'ability','panel_detected':True,'game_id':''}
    personal={**GOOD,'panel_type':'personal','panel_detected':True,'level':None}
    ocr_response(monkeypatch,{**GOOD,'registration_candidates':[ability,personal]})
    assert register(client).status_code==422
    assert_no_registration()

def test_personal_information_uses_character_name_and_level_not_pet():
    rows=[row('個人情報',0,width=140),row('等級',170,x=250),row('78',170,x=380),
        row('職業',210,x=250),row('大副',210,x=380),row('人氣度',260,x=250),
        row('家族',300,x=250),row('测试角色',310,x=50),row('宠物情报',500),
        row('蝙蝠怪',550),row('等级',700),row('13',700,x=150)]
    result=personal_fields(rows)
    assert result['panel_detected'] and result['game_id']=='测试角色'
    assert result['level']==78 and result['job']=='大副'
    box=personal_region(rows,(800,900));assert (box['y']+box['h'])*900<500
    assert not personal_fields([r for r in rows if r['text']!='等級'])['panel_detected']
