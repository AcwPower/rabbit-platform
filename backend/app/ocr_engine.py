"""Local OCR subprocess. No remote image service and no per-image persistence."""
import json,re,sys
from PIL import Image

def clean(text): return re.sub(r'\s+','',text).strip(':：')
def bounds(row):
    points=row['box'];return (min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points))
def center(row):
    x,y,r,b=bounds(row);return ((x+r)/2,(y+b)/2)
def anchor(rows,labels):return next((r for r in rows if clean(r['text']).lower() in labels),None)

def right_value(rows,label):
    if not label:return None
    x,y,r,b=bounds(label);cy=(y+b)/2
    candidates=[row for row in rows if bounds(row)[0]>=r-3 and abs(center(row)[1]-cy)<(b-y)*.65 and bounds(row)[0]-r<(b-y)*8]
    return min(candidates,key=lambda row:bounds(row)[0],default=None)

def normalized(box,size):
    width,height=size;x,y,r,b=box
    x=max(0,min(x,width-1));y=max(0,min(y,height-1));r=min(width,max(r,x+width*.02));b=min(height,max(b,y+height*.02))
    return dict(x=x/width,y=y/height,w=(r-x)/width,h=(b-y)/height)

def automatic_regions(rows,size):
    regions={};title=anchor(rows,{'角色能力'});name=anchor(rows,{'名字','名称','角色名','角色名称','昵称'})
    if title and name:
        tx,ty,tr,tb=bounds(title);nx,ny,nr,nb=bounds(name);value=right_value(rows,name)
        height=nb-ny
        profession=anchor(rows,{'职业','職業','job'})
        pitch=center(profession)[1]-center(name)[1] if profession else height*.9
        if not height*.6<pitch<height*1.6:pitch=height*.9
        width=max((bounds(value)[0]-nx)*3.15 if value else 0,(tr-tx)*3.0)
        regions['character']=normalized((min(tx,nx)-12,ty-8,min(tx,nx)-12+width,ty+pitch*18.4),size)
    else:
        relevant=[row for row in rows if re.search(r'名字|名称|角色名|Name|等级|Level|\bLv\b',row['text'],re.I)]
        if relevant:
            bb=[bounds(r) for r in relevant]
            regions['character']=normalized((min(b[0] for b in bb)-10,min(b[1] for b in bb)-10,max(b[2] for b in bb)+max(b[3]-b[1] for b in bb)*7,max(b[3] for b in bb)+10),size)
    map_title=anchor(rows,{'小地图','大地图','minimap'})
    if map_title:
        x,y,r,b=bounds(map_title);h=b-y
        # The location text sits below the minimap toolbar. Never include the lower diagram.
        left=x-(r-x)*2.25 if clean(map_title['text'])=='大地图' else x
        regions['map']=normalized((left,b+1,r+2*h,b+2.55*h),size)
        if title:
            box=regions['map'];right=min(box['x']+box['w'],(bounds(title)[0]-16)/size[0])
            box['w']=max(.02,right-box['x'])
        box=regions['map'];width,height=size
        addresses=[row for row in rows if len(clean(row['text']))>=2 and re.search(r'[\u4e00-\u9fffA-Za-z]',row['text']) and box['x']*width<=center(row)[0]<=(box['x']+box['w'])*width and box['y']*height<=center(row)[1]<=(box['y']+box['h'])*height]
        if addresses:
            bb=[bounds(row) for row in addresses]
            regions['map']=normalized((min(b[0] for b in bb)-9,min(b[1] for b in bb)-7,max(b[2] for b in bb)+9,max(b[3] for b in bb)+7),size)
    return regions

def character_fields(rows):
    result={'game_id':'','level':None,'job':'','confidence':{}}
    name=right_value(rows,anchor(rows,{'名字','名称','昵称','角色名','角色名称','游戏id','name','id'}))
    job=right_value(rows,anchor(rows,{'职业','職業','job','class'}))
    level=right_value(rows,anchor(rows,{'等级','等級','level','lv','lv.'}))
    if not job and name and level:
        # Photograph moiré can erase the pink profession LABEL while leaving its
        # VALUE readable. The profession is the sole text value between the name
        # and level in the same value column. Never infer it from HP/guild rows or
        # borrow a value from a neighboring personal-information panel.
        nx,ny,nr,nb=bounds(name);lx,ly,lr,lb=bounds(level)
        height=max(nb-ny,lb-ly);gap=center(level)[1]-center(name)[1]
        if abs(lx-nx)<height and 1.4*height<gap<3.5*height:
            candidates=[row for row in rows if abs(bounds(row)[0]-nx)<height and
                nb-height*.15<center(row)[1]<ly+height*.15 and
                re.fullmatch(r'[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z ·-]{0,29}',clean(row['text'])) and
                clean(row['text']) not in {'职业','職業','等级','等級','家族','公会','公會','血量','魔量','job','level','guild'}]
            if len(candidates)==1:job=candidates[0]
    if name:result['game_id']=name['text'].strip()[:40];result['confidence']['game_id']=name['score']
    if job:result['job']=job['text'].strip()[:30];result['confidence']['job']=job['score']
    if not level and job:
        # Some old-client pink labels are unreadable. The level is the single integer
        # directly below the profession and above the guild; do not search HP/EXP rows.
        jx,jy,jr,jb=bounds(job);height=jb-jy
        guild=anchor(rows,{'家族','公会','guild'})
        upper=bounds(guild)[1] if guild else jb+height*1.25
        candidates=[r for r in rows if re.fullmatch(r'\d{1,3}',clean(r['text'])) and jb-3<=center(r)[1]<=upper and abs(bounds(r)[0]-jx)<height*.8]
        if len(candidates)==1:level=candidates[0]
    if level:
        value=clean(level['text'])
        if value.isdecimal() and 1<=int(value)<=300:result['level']=int(value);result['confidence']['level']=level['score']
    for row in rows:
        text=row['text'].strip()
        if not result['game_id']:
            match=re.search(r'(?:角色名称|角色名|游戏\s*ID|名字|名称|昵称|Name|ID)\s*[:：]\s*(.{1,40})',text,re.I)
            if match:result['game_id']=match.group(1).strip();result['confidence']['game_id']=row['score']
        if result['level'] is None:
            match=re.search(r'(?:等级|等級|Level|\bLv\.?|\bLEV)\s*[:：.\-]?\s*(\d{1,3})\b',text,re.I)
            if match and 1<=int(match.group(1))<=300:result['level']=int(match.group(1));result['confidence']['level']=row['score']
    return result

def character_panel(rows):
    """Require the actual panel title and aligned character/stat labels, not arbitrary text."""
    title=anchor(rows,{'角色能力'})
    if not title or title['score'] < .85:return False
    x,y,r,b=bounds(title);height=b-y
    labels=[row for row in rows if row['score']>=.80 and
        x-height <= bounds(row)[0] <= r+height and b <= center(row)[1] <= b+height*24]
    has_name=anchor(labels,{'名字','名称','名稱','角色名','角色名称','角色名稱','昵称','暱稱'})
    has_job=anchor(labels,{'职业','職業'}) or character_fields(rows).get('job')
    seen={clean(row['text']) for row in labels}
    vitals=seen & {'血量','魔量','经验值','經驗值','人气度','人氣度'}
    attributes=seen & {'力量','敏捷','智力','幸运','幸運'}
    return bool(has_name and has_job and len(vitals)>=2 and attributes)

def personal_layout(rows):
    """Locate the upper character summary; pet rows below it are never candidates."""
    title=anchor(rows,{'个人情报','個人情報','个人情報','個人情报'})
    if not title or title['score']<.85:return None
    x,y,r,b=bounds(title);height=b-y
    jobs=[row for row in rows if clean(row['text']) in {'职业','職業'} and
        x+height<bounds(row)[0]<x+height*20 and b<center(row)[1]<b+height*8]
    job=min(jobs,key=lambda row:center(row)[1],default=None)
    if not job:return None
    jx,jy,jr,jb=bounds(job);jh=jb-jy
    # Main level immediately precedes profession in the same right-hand column.
    levels=[row for row in rows if clean(row['text']) in {'等级','等級'} and
        abs(bounds(row)[0]-jx)<jh and jy-jh*2.5<center(row)[1]<jy]
    level=max(levels,key=lambda row:center(row)[1],default=None)
    if not level:return None
    return {'title':title,'job':job,'level':level,'bottom':jb+jh*3.5}

def personal_region(rows,size):
    layout=personal_layout(rows)
    if not layout:return None
    x,y,r,b=bounds(layout['title']);jx,jy,jr,jb=bounds(layout['job'])
    width=max((jx-x)*2.9,(r-x)*4.3)
    return normalized((x-10,y-8,x+width,layout['bottom']+8),size)

def personal_fields(rows):
    result={'game_id':'','level':None,'job':'','confidence':{},'panel_type':'personal','panel_detected':False}
    layout=personal_layout(rows)
    if not layout:return result
    x,y,r,b=bounds(layout['title']);jx,jy,jr,jb=bounds(layout['job']);height=jb-jy
    level=right_value(rows,layout['level']);job=right_value(rows,layout['job'])
    support=[row for row in rows if clean(row['text']) in {'人气度','人氣度','家族','公会','公會','联盟','聯盟'} and
        abs(bounds(row)[0]-jx)<height and jb<center(row)[1]<layout['bottom']]
    result['panel_detected']=bool(support and layout['job']['score']>=.8 and layout['level']['score']>=.8)
    if job:result['job']=job['text'].strip()[:30];result['confidence']['job']=job['score']
    if level and clean(level['text']).isdecimal() and 1<=int(clean(level['text']))<=300:
        result['level']=int(clean(level['text']));result['confidence']['level']=level['score']
    # The character name is on the blue plate below the avatar, left of the summary.
    names=[row for row in rows if x-height*.5<=bounds(row)[0] and bounds(row)[2]<jx and
        jb-height*.5<center(row)[1]<layout['bottom'] and re.search(r'[\u4e00-\u9fffA-Za-z]',row['text'])]
    name=max(names,key=lambda row:center(row)[1],default=None)
    if name:result['game_id']=name['text'].strip()[:40];result['confidence']['game_id']=name['score']
    return result

def map_fields(rows):
    # Labels and toolbar buttons are not location names. Keep OCR spelling; no invented dictionary correction.
    candidates=[r for r in rows if len(clean(r['text']))>=2 and re.search(r'[\u4e00-\u9fffA-Za-z]',r['text']) and clean(r['text']) not in {'小地图','大地图','世界地图','minimap','map'}]
    candidates.sort(key=lambda r:center(r)[1])
    if not candidates:return {'map_name':'','map_region':'','map_confidence':0}
    main=candidates[-1]
    region=candidates[-2] if len(candidates)>1 else None
    return {'map_name':main['text'].strip()[:60],'map_region':region['text'].strip()[:60] if region and region['score']>=.9 else '', 'map_confidence':main['score']}

def make_engine():
    from rapidocr import RapidOCR
    return RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads':1,'EngineConfig.onnxruntime.inter_op_num_threads':1,'Global.log_level':'error'})

def read(engine,image):
    result=engine(image)
    if not result.txts:return []
    return [{'text':t,'score':float(s),'box':b.tolist()} for t,s,b in zip(result.txts,result.scores,result.boxes)]

def recognize(path,regions=None):
    engine=make_engine()
    with Image.open(path) as original:
        image=original.convert('RGB');size=image.size
    if regions is None:
        overview=image.copy();overview.thumbnail((1800,1800))
        rows=read(engine,overview)
        sx,sy=size[0]/overview.width,size[1]/overview.height
        for row in rows:row['box']=[[x*sx,y*sy] for x,y in row['box']]
        regions=automatic_regions(rows,size)
    else: rows=[]
    profile_box=personal_region(rows,size)
    sections={}
    def read_box(box):
        x,y,w,h=(box[k] for k in ('x','y','w','h'))
        crop=image.crop((round(x*size[0]),round(y*size[1]),round((x+w)*size[0]),round((y+h)*size[1])))
        scale=min(1.0,1400/max(crop.size));crop=crop.resize((max(1,round(crop.width*scale)),max(1,round(crop.height*scale))))
        return read(engine,crop)
    for kind,box in regions.items():
        # Bound large crops; preserve source pixels instead of magnifying moiré in camera photos.
        sections[kind]=read_box(box)
    character=sections.get('character',rows)
    result=character_fields(character)
    result['character_panel']=character_panel(character) or character_panel(rows)
    candidates=[]
    if result['character_panel']:
        candidates.append({**result,'confidence':dict(result['confidence']),'panel_type':'ability','panel_detected':True})
    if profile_box:
        profile_rows=read_box(profile_box)
        profile=personal_fields(profile_rows)
        if profile['panel_detected']:candidates.append(profile)
        if not result['character_panel'] and profile['panel_detected']:
            result={**profile,'confidence':dict(profile['confidence']),'character_panel':False}
            regions['character']=profile_box;sections['character']=profile_rows
    result['registration_candidates']=candidates
    result.update(map_fields(sections.get('map',[])))
    result['confidence']['map_name']=result.pop('map_confidence')
    result['uncertain_fields']=[key for key in ('game_id','level','map_name') if result.get(key) and result['confidence'].get(key,0)<.93]
    result.update(regions=regions,needs_confirmation=True,engine='rapidocr',text='\n\n'.join(('角色能力' if kind=='character' else '小地图地址')+'\n'+'\n'.join(r['text'] for r in section) for kind,section in sections.items())[:4000],message='请核对两个区域的识别结果后填入表单')
    return result

if __name__=='__main__':
    if sys.argv[1]=='--prepare':make_engine();print('Local OCR models ready')
    else:print(json.dumps(recognize(sys.argv[1],json.loads(sys.argv[2]) if len(sys.argv)>2 else None),ensure_ascii=False))
