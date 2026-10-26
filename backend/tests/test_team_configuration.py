import uuid
import pytest
from sqlalchemy import select,func
from app.db import Session
from app.models import TeamCard,PartnerCard,PartnerApplication,Contact,Character
from app.map_names import map_key,map_options,POPULAR_MAPS
from conftest import signup,post,guest,card_data,challenge,apply_guest

def publish(client,need='none',slots=3):
    r=post(client,'/api/team-cards',card_data(client,boss_slots=slots,teammate_need=need));assert r.status_code==201,r.text;return r.json()

def edit(client,card,**overrides):
    payload=card_data(client,boss_slots=card['boss_slots'],teammate_need=card['teammate_need'],version=card['version'])|overrides
    return client.put(f"/api/team-cards/{card['id']}",json=payload,headers={'X-Idempotency-Key':str(uuid.uuid4())})

@pytest.mark.parametrize('need,target,job',[('none',None,None),('dragon_knight','fighter','龙骑士'),('priest','priest','')])
def test_boss_count_and_atomic_teammate_post(client,need,target,job):
    signup(client);card=publish(client,need)
    assert card['boss_slots']==card['remaining']==3
    assert card['capacity']==4+int(need!='none')
    with Session() as db:
        linked=db.get(PartnerCard,card['teammate_recruitment_id']) if card['teammate_recruitment_id'] else None
        if not target:assert linked is None;return
        assert (linked.target_role,linked.target_job)==(target,job)
        team=db.get(TeamCard,card['id']);assert linked.expires_at==team.expires_at and linked.game_id==team.game_id
    assert client.get('/api/partners/me').json()['cards'][0]['id']==card['teammate_recruitment_id']
    assert guest().get(f"/api/partners/cards/{card['teammate_recruitment_id']}").json()['public_contact'] is None

def test_capacity_limit_and_no_partial_posts(client):
    signup(client)
    r=post(client,'/api/team-cards',card_data(client,boss_slots=5,teammate_need='priest'))
    assert r.status_code==409
    with Session() as db:
        assert db.scalar(select(func.count(TeamCard.id)))==0
        assert db.scalar(select(func.count(PartnerCard.id)))==0
    assert publish(client,'none',5)['remaining']==5

def test_priest_captain_can_recruit_dragon(client):
    user=signup(client)
    with Session.begin() as db:
        character=db.scalar(select(Character).where(Character.user_id==user['id']))
        character.name='祭司队长';character.level=90;character.job='祭司'
    r=post(client,'/api/team-cards',card_data(client,game_id='祭司队长',boss_slots=3,teammate_need='dragon_knight'))
    assert r.status_code==201,r.text
    card=guest().get('/api/partners/cards/'+str(r.json()['teammate_recruitment_id'])).json()
    assert card['role']=='priest' and card['target_job']=='龙骑士'

def test_edit_sync_change_and_close(client):
    signup(client);card=publish(client,'priest');pid=card['teammate_recruitment_id']
    edited=edit(client,card,map_name='死亡之林Ⅲ');assert edited.status_code==200,edited.text
    card=edited.json();assert card['teammate_recruitment_id']==pid
    assert guest().get(f'/api/partners/cards/{pid}').json()['map_name']=='死亡之林Ⅲ'
    changed=edit(client,card,teammate_need='dragon_knight');assert changed.status_code==200,changed.text
    card=changed.json();newpid=card['teammate_recruitment_id'];assert pid!=newpid
    assert guest().get(f'/api/partners/cards/{pid}').json()['status']=='closed'
    assert post(client,f"/api/team-cards/{card['id']}/status",{'action':'close'}).status_code==200
    assert guest().get(f'/api/partners/cards/{newpid}').json()['status']=='closed'

def test_none_closes_link_and_contact_delete_covers_copy(client):
    signup(client);card=publish(client,'priest');pid=card['teammate_recruitment_id']
    assert client.delete(f"/api/contacts/team/{card['id']}",headers={'X-Idempotency-Key':str(uuid.uuid4())}).status_code==200
    with Session() as db:assert all(not c.encrypted for c in db.scalars(select(Contact)))
    edited=edit(client,card,teammate_need='none');assert edited.status_code==200,edited.text
    assert edited.json()['remaining']==3
    assert guest().get(f'/api/partners/cards/{pid}').json()['status']=='closed'

def test_dragon_requirement_and_captain_join_does_not_reduce_boss_slots(client):
    signup(client);card=publish(client,'dragon_knight');pid=card['teammate_recruitment_id'];other=guest();signup(other,'龙骑测试')
    payload=dict(card_id=pid,role='fighter',game_id='龙骑队友',level=100,job='祭司',flower='none',contact={'wechat':'dragon-contact'})
    assert post(other,'/api/partners/applications',payload|challenge(other)).status_code==409
    payload['job']='龙骑士';r=post(other,'/api/partners/applications',payload|challenge(other));assert r.status_code==201,r.text;rid=r.json()['id']
    assert post(client,f'/api/partners/applications/{rid}/accept').status_code==200
    assert post(other,f'/api/partners/applications/{rid}/join',{'wechat_confirmed':True}).status_code==403
    assert post(client,f'/api/partners/applications/{rid}/join',{'wechat_confirmed':True}).status_code==200
    assert client.get(f"/api/team-cards/{card['id']}").json()['remaining']==3
    assert guest().get(f'/api/partners/cards/{pid}').json()['status']=='matched'

def test_full_boss_capacity_leaves_reserved_teammate_space(client):
    signup(client);card=publish(client,'priest',1);boss=guest();aid,_=apply_guest(boss,card)
    mid=post(client,f'/api/applications/{aid}/accept').json()['match']['id']
    assert post(client,f'/api/matches/{mid}/board').status_code==200
    detail=client.get(f"/api/team-cards/{card['id']}").json()
    assert detail['remaining']==0 and detail['capacity']==3
    assert guest().get('/api/team-cards?available=true').json()['total']==0
    # The teammate's reserved space does not let another boss board.
    payload=dict(card_type='team',card_id=card['id'],game_id='另一老板',level=35,contact={'wechat':'boss-other'},**challenge(boss))
    assert post(boss,'/api/applications',payload).status_code==409

def test_map_aliases_dedupe_search_and_keep_distinct_areas(client):
    signup(client);card=publish(client)
    edited=edit(client,card,map_name='森林迷宫III');assert edited.status_code==200
    result=guest().get('/api/team-cards',params={'map_name':'森林迷宫Ⅲ'}).json();assert result['total']==1
    assert map_key('森林迷宫 ３')==map_key('森林迷宫Ⅲ')
    assert map_key('地铁一号线<第４地区>')==map_key('地铁1号线<第4地区>')
    assert map_key('死亡之林Ⅰ')!=map_key('死亡之林Ⅱ')
    names=map_options([' 森林迷宫Ⅲ ','森林迷宫３','猴子森林','猴子森林I'])
    assert len(names)==len(POPULAR_MAPS)==89

@pytest.mark.parametrize('need',['priest','dragon_knight'])
def test_teammate_levels_roundtrip_edit_and_application_guard(client,need):
    signup(client)
    result=post(client,'/api/team-cards',card_data(client,boss_slots=3,teammate_need=need,teammate_level_min=80,teammate_level_max=130))
    assert result.status_code==201,result.text
    card=result.json();pid=card['teammate_recruitment_id']
    detail=client.get(f"/api/team-cards/{card['id']}").json()
    assert (detail['teammate_level_min'],detail['teammate_level_max'])==(80,130)
    linked=guest().get(f'/api/partners/cards/{pid}').json()
    assert (linked['level_min'],linked['level_max'])==(80,130)
    # Older callers omitting the new fields must not reset the requirement.
    edited=edit(client,card,map_name='死亡之林Ⅲ');assert edited.status_code==200,edited.text
    card=edited.json();assert (card['teammate_level_min'],card['teammate_level_max'])==(80,130)
    edited=edit(client,card,teammate_level_min=90,teammate_level_max=120);assert edited.status_code==200,edited.text
    card=edited.json();assert card['teammate_recruitment_id']==pid
    linked=guest().get(f'/api/partners/cards/{pid}').json()
    assert (linked['level_min'],linked['level_max'])==(90,120)
    other=guest();signup(other,'等级测试')
    payload=dict(card_id=pid,role='priest' if need=='priest' else 'fighter',game_id='等级队友',job='祭司' if need=='priest' else '龙骑士',flower='active' if need=='priest' else 'none',contact={'wechat':'level-contact'})
    assert post(other,'/api/partners/applications',payload|{'level':89}|challenge(other)).status_code==409
    assert post(other,'/api/partners/applications',payload|{'level':121}|challenge(other)).status_code==409
    assert post(other,'/api/partners/applications',payload|{'level':90}|challenge(other)).status_code==201

def test_invalid_teammate_level_range_is_atomic(client):
    signup(client)
    for lo,hi in [(0,100),(80,301),(130,80)]:
        result=post(client,'/api/team-cards',card_data(client,boss_slots=3,teammate_need='priest',teammate_level_min=lo,teammate_level_max=hi))
        assert result.status_code==422,result.text
    with Session() as db:
        assert db.scalar(select(func.count(TeamCard.id)))==0
        assert db.scalar(select(func.count(PartnerCard.id)))==0
    card=publish(client,'priest')
    edited=edit(client,card,teammate_level_max=100);assert edited.status_code==200,edited.text
    card=edited.json()
    invalid=edit(client,card,teammate_level_min=101)
    assert invalid.status_code==422,invalid.text
    detail=client.get(f"/api/team-cards/{card['id']}").json()
    assert (detail['teammate_level_min'],detail['teammate_level_max'],detail['version'])==(1,100,card['version'])
