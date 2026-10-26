import io,json,uuid
from datetime import timedelta
from PIL import Image
from sqlalchemy import select
from app.db import Session,now
from app.models import Application,Match,TeamCard
from app.security import cipher
from conftest import signup,create_team,guest,post,challenge

def proof(team,user,members=None):
    return cipher.encrypt(json.dumps({'team':team['id'],'user':user,'members':members or [{'game_id':'现场老板','level':None}]}).encode()).decode()
def data(team,user,name='现场老板',token=None):
    return {'version':team['version'],'review_token':token or proof(team,user),'members':[{'index':0,'game_id':name,'started_at':(now()-timedelta(hours=1)).isoformat()+'Z','duration_hours':6}]}
def owner_id(client):return client.get('/api/auth/session').json()['user']['id']

def test_import_unknown_level_occupies_slot_and_manual_completion_releases(client):
    signup(client);team=create_team(client);uid=owner_id(client);p=data(team,uid);key=str(uuid.uuid4())
    result=post(client,f"/api/captain/teams/{team['id']}/roster/import",p,headers={'X-Idempotency-Key':key})
    assert result.status_code==200,result.text
    assert result.json()['team']['remaining']==team['remaining']-1
    again=post(client,f"/api/captain/teams/{team['id']}/roster/import",p,headers={'X-Idempotency-Key':key});assert again.json()==result.json()
    aid=result.json()['application_ids'][0]
    detail=client.get(f'/api/applications/{aid}').json()
    assert detail['source']=='screenshot' and detail['level'] is None
    assert not detail['contacts']['applicant']
    assert guest().get(f'/api/applications/{aid}').status_code==403
    assert post(guest(),'/api/boss/bookings/query',{'managed':[]}).json()['bookings']==[]
    public=guest().get(f"/api/team-cards/{team['id']}").json()
    assert '现场老板' not in json.dumps(public,ensure_ascii=False)
    assert post(client,f"/api/matches/{detail['match']['id']}/complete").status_code==200
    assert client.get(f"/api/team-cards/{team['id']}").json()['remaining']==team['remaining']

def test_import_reuses_existing_request_and_notifies_boss(client):
    signup(client);team=create_team(client);uid=owner_id(client);boss=guest();boss.headers['X-Manage-Token']=uuid.uuid4().hex*2
    row=post(boss,'/api/applications',{'card_type':'team','card_id':team['id'],'game_id':'现场老板','level':35,'contact':{'wechat':'test-boss'},**challenge(boss)}).json()
    result=post(client,f"/api/captain/teams/{team['id']}/roster/import",data(team,uid))
    assert result.status_code==200,result.text
    assert result.json()['application_ids']==[row['id']]
    detail=boss.get('/api/applications/'+str(row['id'])).json()
    assert detail['source']=='web' and detail['match']['status']=='boarded' and detail['level']==35

def test_import_owner_proof_capacity_duplicates_and_time_validation(client):
    signup(client);team=create_team(client,boss_slots=1);uid=owner_id(client);path=f"/api/captain/teams/{team['id']}/roster/import"
    other=guest();signup(other,'other_import_captain')
    assert post(other,path,data(team,uid)).status_code==403
    bad=data(team,uid,token='invalid');assert post(client,path,bad).status_code==422
    assert post(client,path,data(team,uid,name=team['game_id'])).status_code==422
    bad=data(team,uid);bad['members'][0]['started_at']=(now()+timedelta(hours=1)).isoformat()+'Z';assert post(client,path,bad).status_code==422
    good=post(client,path,data(team,uid));assert good.status_code==200,good.text
    assert good.json()['team']['remaining']==0
    assert post(client,path,data(team,uid)).status_code==409
    fresh=good.json()['team'];assert post(client,path,data(fresh,uid,name='另一个老板')).status_code==409
    with Session() as db:
        assert db.get(TeamCard,team['id']).confirmed_boss_count==1
        assert len(db.scalars(select(Match)).all())==1

def test_non_party_ocr_rejected_and_accepted_result_bound_to_owner(client,monkeypatch):
    import app.party_import as module
    signup(client);team=create_team(client);body=io.BytesIO();Image.new('RGB',(200,200),'white').save(body,'PNG')
    result={'accepted':False,'members':[]}
    class Reply:
        status_code=200
        def json(self):return result
    class Worker:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kw):return Reply()
    monkeypatch.setattr(module.httpx,'AsyncClient',Worker)
    def upload():return client.post(f"/api/captain/teams/{team['id']}/roster/recognize",files={'file':('test.png',body.getvalue(),'image/png')},headers={'X-Idempotency-Key':str(uuid.uuid4())})
    assert upload().status_code==422
    result.update(accepted=True,layout='party_hud',members=[{'game_id':'甲','level':None},{'game_id':'乙','level':None}])
    response=upload();assert response.status_code==200,response.text
    signed=json.loads(cipher.decrypt(response.json()['review_token'].encode()))
    assert signed['team']==team['id'] and signed['user']==owner_id(client)

def test_batch_rollback_and_screenshot_cannot_review(client):
    signup(client);team=create_team(client,boss_slots=3);uid=owner_id(client)
    path=f"/api/captain/teams/{team['id']}/roster/import"
    payload=data(team,uid,token=proof(team,uid,[{'game_id':'甲'},{'game_id':'乙'}]))
    payload['members'].append({'index':1,'game_id':'乙','started_at':(now()+timedelta(hours=2)).isoformat()+'Z','duration_hours':6})
    assert post(client,path,payload).status_code==422
    with Session() as db:
        assert db.get(TeamCard,team['id']).confirmed_boss_count==0
        assert not db.scalars(select(Match)).all()
    result=post(client,path,data(team,uid));assert result.status_code==200,result.text
    aid=result.json()['application_ids'][0]
    detail=client.get(f'/api/applications/{aid}').json();mid=detail['match']['id']
    assert post(client,f'/api/matches/{mid}/complete').status_code==200
    response=post(client,f'/api/reviews?match_id={mid}',{'tags':['沟通守时'],'body':'测试'})
    assert response.status_code==409,response.text
