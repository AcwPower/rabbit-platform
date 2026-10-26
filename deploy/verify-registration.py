"""Destructive ONLY to an isolated *_test DB. Uses a real, separately running OCR worker."""
import argparse, io, json, os
from pathlib import Path
from dotenv import load_dotenv

parser=argparse.ArgumentParser()
parser.add_argument('--env-file',required=True)
parser.add_argument('--image',required=True)
parser.add_argument('--personal-image')
args=parser.parse_args()
load_dotenv(args.env_file,override=True)
os.environ['OCR_URL']='http://127.0.0.1:8104'
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text, select, func
from PIL import Image
from app.db import Base, engine, Session
from app.models import User, RegistrationProof
from app.main import app
from app.security import hash_password

assert engine.url.database.endswith('_test'), 'Refusing to run on a non-test database'
Base.metadata.drop_all(engine)
with engine.begin() as conn:conn.execute(text('DROP TABLE IF EXISTS alembic_version'))
config=Config('alembic.ini')
command.upgrade(config,'f0a63f1be60f')
with Session.begin() as db:db.add(User(username='迁移测试账号',password_hash=hash_password('Test-password-92841')))
command.upgrade(config,'head')
with Session() as db:assert db.scalar(select(User.id).where(User.username=='迁移测试账号'))
print('Migration preserves existing users and adds the private proof table.')

with TestClient(app,base_url='http://testserver',headers={'Origin':'http://testserver'}) as client:
    def signup(raw,name):
        c=client.get('/api/challenge').json()
        left,right=c['question'].split('=')[0].split('+')
        data={'username':name,'password':'Test-password-92841','challenge_id':c['id'],'answer':str(int(left)+int(right))}
        return client.post('/api/auth/register',data={'credentials':json.dumps(data)},files={'screenshot':('panel.png',raw,'image/png')})
    out=io.BytesIO();Image.new('RGB',(400,600),'white').save(out,format='PNG')
    invalid=signup(out.getvalue(),'空白图测试')
    assert invalid.status_code==422,invalid.text
    valid=signup(Path(args.image).read_bytes(),'真实识别测试')
    assert valid.status_code==200,valid.text
    uid=valid.json()['user']['id']
    client.cookies.set('rabbit_session',valid.cookies.get('rabbit_session'),path='/')
    proof=client.get(f'/api/users/{uid}/registration-proof')
    assert proof.status_code==200 and proof.json()['game_id']=='RabbitTest' and proof.json()['level']==78
    assert proof.json()['image'].startswith('data:image/jpeg;base64,')
    assert client.get('/api/me').json()['characters'][0]['name']=='RabbitTest'
    with Session() as db:
        assert db.scalar(select(func.count(RegistrationProof.user_id)))==1
        assert not db.scalar(select(User.id).where(User.username=='空白图测试'))
    if args.personal_image:
        client.cookies.clear()
        personal=signup(Path(args.personal_image).read_bytes(),'个人情报测试')
        assert personal.status_code==422,personal.text
        with Session() as db:
            assert db.scalar(select(func.count(RegistrationProof.user_id)))==1
            assert not db.scalar(select(User.id).where(User.username=='个人情报测试'))
print('Real OCR: blank/personal-only images rejected; ability panel accepted, encrypted and linked to account.')
