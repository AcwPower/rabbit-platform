"""Captain-reviewed screenshot imports; no fabricated boss login or contact data."""
import io,json
from datetime import timedelta,timezone
import httpx
from fastapi import APIRouter,Depends,Request,File,UploadFile
from PIL import Image
from pydantic import Field,AwareDatetime
from sqlalchemy import select
from .db import get_db,now
from .config import settings
from .schemas import Input
from .models import Application,Match,BossCard
from .security import current_user,require_owner,fail,cipher,audit,digest
from .services import get_card,remaining,card_dict,iso
from .application_events import notify_application
from .party_ocr import name_key
router=APIRouter()

@router.post('/captain/teams/{team_id}/roster/recognize')
async def recognize_roster(team_id:int,request:Request,file:UploadFile=File(...),db=Depends(get_db)):
    user=current_user(request,db,True);team=get_card(db,'team',team_id);require_owner(request,db,team)
    raw=await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:fail('FILE_TOO_LARGE','图片不能超过 5 MB',413)
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('JPEG','PNG','WEBP') or image.width*image.height>12000000 or min(image.size)<60 or getattr(image,'n_frames',1)!=1:raise ValueError()
            image.verify()
    except Exception:fail('INVALID_IMAGE','请上传清晰的 PNG/JPEG/WebP 队伍截图',422)
    try:
        async with httpx.AsyncClient(timeout=24) as client:
            result=await client.post(settings.ocr_url+'/recognize',content=raw,headers={'X-OCR-Secret':settings.ocr_secret,'X-OCR-Mode':'party'})
    except httpx.HTTPError:fail('OCR_UNAVAILABLE','识别服务暂不可用，请稍后重试',503)
    if result.status_code!=200:fail('OCR_UNAVAILABLE','识别繁忙或图片无法读取，请稍后重试',503)
    data=result.json();members=data.get('members',[])
    if data.get('accepted') is not True or data.get('layout') not in ('party_table','party_hud') or not 2<=len(members)<=6:
        fail('NOT_PARTY_IMAGE','上传图片不是可识别的队伍截图。请上传“在线队员”列表或带成员姓名和血条的队伍面板，其他图片不支持。',422)
    proof={'team':team.id,'user':user.id,'members':members}
    review=cipher.encrypt(json.dumps(proof,ensure_ascii=False).encode()).decode()
    return {'layout':data['layout'],'members':members,'review_token':review,'team':card_dict(team,'team')}

class RosterMember(Input):
    index:int=Field(ge=0,le=5)
    game_id:str=Field(min_length=1,max_length=40,pattern=r'^[\w\u4e00-\u9fff]+$')
    started_at:AwareDatetime
    duration_hours:float=Field(ge=.25,le=168,allow_inf_nan=False)
class RosterImport(Input):
    review_token:str=Field(max_length=16000)
    version:int=Field(ge=1)
    members:list[RosterMember]=Field(min_length=1,max_length=6)

@router.post('/captain/teams/{team_id}/roster/import')
def import_roster(team_id:int,data:RosterImport,request:Request,db=Depends(get_db)):
    user=current_user(request,db,True);team=get_card(db,'team',team_id,True);require_owner(request,db,team)
    if data.version!=team.version:fail('VERSION_CONFLICT','队伍人数刚刚变化，请重新识别核对后保存',409)
    if team.status not in ('active','full') or team.expires_at<=now():fail('CARD_UNAVAILABLE','队伍已下架或到期，不能录入新老板',409)
    try:
        proof=json.loads(cipher.decrypt(data.review_token.encode(),ttl=1800))
        if proof['team']!=team_id or proof['user']!=user.id:raise ValueError()
        if any(m.index>=len(proof['members']) for m in data.members):raise ValueError()
    except Exception:fail('INVALID_REVIEW','识别结果已过期或无效，请重新上传截图',422)
    names=[name_key(m.game_id) for m in data.members]
    if len(set(names))!=len(names) or len({m.index for m in data.members})!=len(data.members):fail('DUPLICATE_MEMBER','同一个成员不能重复录入',422)
    if name_key(team.game_id) in names:fail('CAPTAIN_AS_BOSS','队伍主力打手不能标记为老板',422)
    if len(data.members)>remaining(team):fail('TEAM_FULL','老板位不足，请先核对现有成员或调整队伍需要的老板人数',409)
    existing=db.scalars(select(Application).where((Application.team_card_id==team.id)|(Application.offered_team_id==team.id)).with_for_update()).all()
    matches={m.application_id:m for m in db.scalars(select(Match).where(Match.team_id==team.id).with_for_update())}
    linked=[]
    for item in data.members:
        started=item.started_at.astimezone(timezone.utc).replace(tzinfo=None,microsecond=0)
        if started>now()+timedelta(minutes=2) or started<now()-timedelta(days=7):fail('INVALID_START_TIME','已上车时间应在过去 7 天内，不能填写未来时间',422)
        found=[]
        for row in existing:
            boss=db.get(BossCard,row.boss_card_id) if row.boss_card_id else None
            actual_name=boss.game_id if boss else row.game_id
            match=matches.get(row.id)
            if name_key(actual_name)!=name_key(item.game_id):continue
            if match and match.status in ('boarded','disputed'):fail('ALREADY_BOARDED',f'{item.game_id} 已在挂机清单中，请直接调整原记录',409)
            if not match and row.status=='pending' and row.expires_at<=now():row.active_key=None
            if (match and match.status=='contacted') or (not match and row.status=='pending' and row.expires_at>now()):found.append(row)
        if len(found)>1:fail('AMBIGUOUS_MEMBER',f'{item.game_id} 有多条申请，请先在清单中处理',409)
        row=found[0] if found else None
        if not row:
            scanned=proof['members'][item.index]
            row=Application(card_type='team',team_card_id=team.id,game_id=item.game_id,level=scanned.get('level'),source='screenshot',status='accepted',notes='打手通过队伍截图录入',expires_at=team.expires_at,active_key=digest(f'team:{team.id}:{name_key(item.game_id)}'))
            db.add(row);db.flush()
        else:row.status='accepted'
        match=matches.get(row.id)
        if not match:match=Match(application_id=row.id,team_id=team.id);db.add(match)
        match.status='boarded';match.planned_start_at=started;match.boarded_at=started
        match.expected_end_at=started+timedelta(hours=item.duration_hours)
        match.schedule_version=(match.schedule_version or 0)+1
        if row.source!='screenshot':notify_application(db,row,'boarded','applicant' if row.card_type=='team' else 'owner')
        linked.append(row.id)
    team.confirmed_boss_count+=len(data.members);team.version+=1
    audit(db,request,'party_screenshot_import',f'team:{team.id}',','.join(map(str,linked)))
    db.flush()
    return {'team':card_dict(team,'team'),'imported':len(linked),'application_ids':linked}
