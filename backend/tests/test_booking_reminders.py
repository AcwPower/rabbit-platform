from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select,func
from app.db import Session,now
from app.models import Match,TeamCard,ApplicationNotification
from app.booking_reminders import generate_booking_reminders
from conftest import signup,create_team,guest,apply_guest,post,card_data,challenge


def boarded(owner,team,boss):
    aid,token=apply_guest(boss,team)
    match=post(owner,f'/api/applications/{aid}/accept').json()['match']
    assert post(owner,f"/api/matches/{match['id']}/board").status_code==200
    return aid,match['id'],token


def ending(mid,minutes,version=None):
    with Session.begin() as db:
        match=db.get(Match,mid);match.expected_end_at=now()+timedelta(minutes=minutes)
        if version:match.schedule_version=version


def notices(client):return client.get('/api/notifications').json()


def test_due_and_late_reminders_are_private_durable_once_and_do_not_release(client):
    signup(client);team=create_team(client);boss=guest();aid,mid,token=boarded(client,team,boss)
    ending(mid,31);generate_booking_reminders();assert notices(client)['total']==0
    ending(mid,20)
    with ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:generate_booking_reminders(),range(2)))
    data=notices(client);assert data['total']==1
    due=data['updates'][0]
    assert due['event']=='due:1' and due['kind']=='booking_reminder' and due['severity']=='warning'
    assert due['game_id']=='老板测试' and due['side']=='owner' and due['team_id']==team['id']
    assert 'boss-private' not in str(data) and token not in str(data)
    assert post(boss,'/api/notifications/read',{'ids':[due['id']]}).json()['read']==0
    other=guest();signup(other,'其他队长');assert notices(other)['total']==0
    assert post(client,'/api/notifications/read',{'ids':[due['id']]}).json()['read']==1
    generate_booking_reminders();assert notices(client)['total']==0
    ending(mid,-3);generate_booking_reminders()
    late=notices(client)['updates'][0];assert late['event']=='late:1' and late['severity']=='danger'
    assert late['id']!=due['id'] and '超时' in late['message']
    records=[{'type':'application','id':aid,'manage':token}]
    boss_items=post(boss,'/api/notifications/query',{'managed':records}).json()['updates']
    assert not any(x['kind']=='booking_reminder' for x in boss_items)
    with Session() as db:
        assert db.get(Match,mid).status=='boarded' and db.get(Match,mid).finished_at is None
        assert db.get(TeamCard,team['id']).confirmed_boss_count==1
        assert db.scalar(select(func.count(ApplicationNotification.id)).where(ApplicationNotification.event.like('due:%')))==1
    assert post(client,f'/api/matches/{mid}/complete').status_code==200
    assert notices(client)['total']==0
    generate_booking_reminders();assert notices(client)['total']==0


def test_rescheduling_and_late_phase_hide_stale_reminders(client):
    signup(client);team=create_team(client);aid,mid,_=boarded(client,team,guest())
    ending(mid,15);generate_booking_reminders();assert notices(client)['total']==1
    ending(mid,-1);generate_booking_reminders()
    assert [x['event'] for x in notices(client)['updates']]==['late:1']
    ending(mid,60,2);generate_booking_reminders();assert notices(client)['total']==0
    ending(mid,25);generate_booking_reminders()
    assert [x['event'] for x in notices(client)['updates']]==['due:2']
    # An expired or closed recruitment card still has a boss who must be managed.
    with Session.begin() as db:db.get(TeamCard,team['id']).status='closed'
    ending(mid,-5);generate_booking_reminders()
    assert notices(client)['updates'][0]['event']=='late:2'
    assert post(client,f'/api/matches/{mid}/cancel').status_code==200
    assert notices(client)['total']==0


def test_unboarded_booking_never_triggers_and_late_arrival_skips_obsolete_due(client):
    signup(client);team=create_team(client);aid,_=apply_guest(guest(),team)
    mid=post(client,f'/api/applications/{aid}/accept').json()['match']['id']
    ending(mid,5);generate_booking_reminders();assert notices(client)['total']==0
    assert post(client,f'/api/matches/{mid}/board').status_code==200
    ending(mid,-5);generate_booking_reminders()
    assert [x['event'] for x in notices(client)['updates']]==['late:1']


def test_boss_card_reminder_targets_actual_captain_and_names_boss(client):
    signup(client);team=create_team(client)
    boss=guest();boss.headers['X-Manage-Token']='a'*64
    bid=post(boss,'/api/boss-cards',card_data(boss,game_id='求带老板',level=35,flower='any',price_mode='any',price=None)).json()['id']
    aid=post(client,'/api/applications',dict(card_type='boss',card_id=bid,offered_team_id=team['id'],game_id='接单打手',level=70,contact={'wechat':'captain-wechat'},**challenge(client))).json()['id']
    mid=client.get(f'/api/applications/{aid}').json()['match']['id']
    assert post(client,f'/api/matches/{mid}/board').status_code==200
    ending(mid,10);generate_booking_reminders()
    reminder=next(x for x in notices(client)['updates'] if x['kind']=='booking_reminder')
    assert reminder['side']=='applicant' and reminder['game_id']=='求带老板' and reminder['map_name']==team['map_name']


def test_ignore_persists_without_ending_and_new_schedule_reenables(client):
    signup(client);team=create_team(client);boss=guest();aid,mid,_=boarded(client,team,boss)
    ending(mid,20);generate_booking_reminders();assert notices(client)['total']==1
    path=f'/api/matches/{mid}/reminders/ignore'
    assert post(boss,path,{'version':1}).status_code==401
    other=guest();signup(other,'无权限队长');assert post(other,path,{'version':1}).status_code==403
    assert post(client,path,{'version':2}).status_code==409
    assert post(client,path,{'version':1}).json()['match']['reminder_ignored'] is True
    assert post(client,path,{'version':1}).status_code==200
    ending(mid,-10);generate_booking_reminders();assert notices(client)['total']==0
    member=client.get('/api/captain/teams').json()['teams'][0]['members'][0]
    assert member['status']=='boarded' and member['match']['reminder_ignored'] is True
    with Session() as db:
        assert db.get(TeamCard,team['id']).confirmed_boss_count==1
        assert db.get(Match,mid).finished_at is None
    ending(mid,20,2);generate_booking_reminders()
    assert notices(client)['updates'][0]['event']=='due:2'
    assert post(client,path,{'version':1}).status_code==409
    assert post(client,f'/api/matches/{mid}/complete').status_code==200
    assert notices(client)['total']==0
