import os, uuid, io, json
from unittest.mock import patch
import httpx
from PIL import Image
import pytest
from dotenv import load_dotenv
load_dotenv(os.environ.get('TEST_ENV_FILE','/home/ubuntu/rabbit-test.env'),override=True)
from app.db import engine, Base
from app import models
from app.main import app
from app.config import settings
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def database(monkeypatch):
    if not engine.url.database.endswith('_test'):
        raise RuntimeError('Tests must only run against a dedicated *_test database')
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    # Exercise the retained teammate feature as well as the V1-off tests.
    monkeypatch.setattr(settings,'teammate_recruitment_enabled',True)
    yield

@pytest.fixture
def client():
    with TestClient(app,base_url='http://testserver') as c:
        c.headers['Origin']='http://testserver'
        yield c

def challenge(client):
    c=client.get('/api/challenge').json()
    a,b=c['question'].split('=')[0].split('+')
    return {'challenge_id':c['id'],'answer':str(int(a)+int(b))}

def post(client,path,data=None,**kw):
    headers={'X-Idempotency-Key':str(uuid.uuid4()),**kw.pop('headers',{})}
    return client.post(path,json=data,headers=headers,**kw)

def signup(client,name='队长测试'):
    # These tests isolate account/business logic from the OCR model. Real OCR is
    # exercised separately with the synthetic character-panel image.
    async def recognized(*args,**kwargs):
        return httpx.Response(200,json={'character_panel':True,'game_id':'注册角色','level':78,'job':'大副',
            'confidence':{'game_id':.99,'level':.99,'job':.99}})
    image=io.BytesIO();Image.new('RGB',(400,600),'white').save(image,format='PNG')
    with patch('httpx.AsyncClient.post',recognized):
        r=client.post('/api/auth/register',data={'credentials':json.dumps({'username':name,'password':'Test-password-92841',**challenge(client)})},
            files={'screenshot':('character.png',image.getvalue(),'image/png')})
    assert r.status_code==200,r.text
    client.cookies.set('rabbit_session',r.cookies.get('rabbit_session'),path='/')
    client.headers['X-CSRF-Token']=r.json()['csrf']
    return r.json()['user']

def guest():
    c=TestClient(app,base_url='http://testserver');c.headers['Origin']='http://testserver';return c

def card_data(client,**kw):
    return dict(game_id='火毒队长',level=70,map_name='僵尸森林',capacity=2,fighter_count=1,priest_count=0,flower='none',price_mode='hour',price='8.50',level_min=20,level_max=90,exp_min=500000,exp_max=800000,start_time='20:00',end_time='02:00',duration_hours=24,contact={'wechat':'captain-wechat'},**challenge(client))|kw

def create_team(client,**kw):
    r=post(client,'/api/team-cards',card_data(client,**kw));assert r.status_code==201,r.text;return r.json()

def apply_guest(client,card,game_id='老板测试'):
    manage=uuid.uuid4().hex+uuid.uuid4().hex
    client.headers['X-Manage-Token']=manage
    data=dict(card_type='team',card_id=card['id'],game_id=game_id,level=35,contact={'wechat':'boss-private'},**challenge(client))
    r=post(client,'/api/applications',data);assert r.status_code==201,r.text
    return r.json()['id'],manage
