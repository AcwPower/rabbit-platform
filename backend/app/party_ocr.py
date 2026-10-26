"""Read only party-table or repeated HP-bar party HUD screenshots."""
import json,re,sys,unicodedata
import numpy as np
from PIL import Image,ImageOps
from .ocr_engine import make_engine,read,bounds,center,clean

def name_key(value):return unicodedata.normalize('NFKC',value).strip().casefold()
def valid_name(text):
    return bool(re.fullmatch(r'[\w\u4e00-\u9fff]{1,40}',text)) and not text.isdecimal() and not any(x in text for x in ('获取物品','獲取物品','队员','隊員','社区','社區','名字','等级','等級','职业','職業'))

def table_members(rows):
    expanded=[]
    for row in rows:
        numbers=row['text'].split();x,y,r,b=bounds(row)
        if len(numbers)>1 and all(v.isdigit() and 1<=int(v)<=300 for v in numbers) and b-y>(r-x)*1.5:
            step=(b-y)/len(numbers)
            for i,value in enumerate(numbers):expanded.append({**row,'text':value,'box':[[x,y+i*step],[r,y+i*step],[r,y+(i+1)*step],[x,y+(i+1)*step]]})
        else:expanded.append(row)
    rows=expanded
    titles=[r for r in rows if re.search(r'在线队员|在線隊員',clean(r['text']))]
    for title in titles:
        x,y,right,b= bounds(title);h=b-y
        headers=[r for r in rows if b<center(r)[1]<b+3*h]
        names=next((r for r in headers if clean(r['text']).lstrip('·•.☆★') in ('名字','名称','名稱')),None)
        jobs=next((r for r in headers if clean(r['text']).lstrip('·•.') in ('职业','職業','R业','R業')),None)
        levels=next((r for r in headers if clean(r['text']).lstrip('·•.') in ('等级','等級')),None)
        if not names or not jobs or not levels:continue
        bottom=min([bounds(r)[1] for r in rows if re.search('离线队员|離線隊員',clean(r['text'])) and bounds(r)[1]>b] or [b+h*13])
        nx=center(names)[0];jx=center(jobs)[0];lx=center(levels)[0]
        if not nx<jx<lx:continue
        output=[]
        for row in sorted(rows,key=lambda r:center(r)[1]):
            rx,ry=center(row);text=clean(row['text']).lstrip('☆★·•')
            if not center(names)[1]+h*.5<ry<bottom or not nx-h*2<rx<jx-h or not valid_name(text) or row['score']<.55:continue
            job=next((r for r in rows if abs(center(r)[1]-ry)<h*.6 and abs(center(r)[0]-jx)<h*2 and r!=row),None)
            level=next((r for r in rows if abs(center(r)[1]-ry)<h*.6 and abs(center(r)[0]-lx)<h*2 and re.fullmatch(r'\d{1,3}',clean(r['text']))),None)
            if not job:continue
            lv=int(clean(level['text'])) if level else None
            if lv is not None and not 1<=lv<=300:continue
            output.append({'game_id':text,'level':lv,'job':clean(job['text']),'confidence':round(row['score'],3)})
        if 2<=len(output)<=6:return output
    return []

def hud_members(image,rows,engine=None):
    a=np.asarray(image);height,width=a.shape[:2]
    red=(a[:,:,0]>170)&(a[:,:,1]<115)&(a[:,:,2]<115)
    strips=[]
    for y in range(height):
        edges=np.diff(np.r_[False,red[y],False].astype(int));starts=np.where(edges==1)[0];ends=np.where(edges==-1)[0]
        if not len(starts):continue
        i=int(np.argmax(ends-starts));left,right=int(starts[i]),int(ends[i])
        if right-left<max(18,width*.08):continue
        if strips and y-strips[-1][3]<=8 and abs(left-strips[-1][0])<12:
            old=strips[-1];strips[-1]=(min(left,old[0]),old[1],max(right,old[2]),y+1)
        else:strips.append((left,y,right,y+1))
    bands=[]
    for left,top,right,bottom in strips:
        bh=bottom-top;bw=right-left
        crop=a[max(0,top-12):min(height,bottom+12),max(0,left-12):min(width,right+12)]
        white=(crop.min(axis=2)>195).mean();black=(crop.max(axis=2)<85).mean()
        if 2<=bh<=height*.12 and bw>4*bh and white>.1 and black>.08:bands.append((left,top,right,bottom))
    for bar in bands:
        aligned=[b for b in bands if abs(b[0]-bar[0])<max(8,width*.035) and abs(b[2]-bar[2])<max(12,width*.06)]
        if not 2<=len(aligned)<=6:continue
        aligned.sort(key=lambda b:b[1]);gaps=np.diff([(b[1]+b[3])/2 for b in aligned])
        if gaps.max()>gaps.min()*1.8:continue
        output=[]
        for left,top,right,bottom in aligned:
            cy=(top+bottom)/2;pitch=float(np.median(gaps))
            candidates=[r for r in rows if bounds(r)[2]<=left+3 and bounds(r)[0]>=left-(right-left)*2.5 and abs(center(r)[1]-cy)<pitch*.45 and valid_name(clean(r['text'])) and r['score']>=.45]
            row=min(candidates,key=lambda r:abs(center(r)[1]-cy),default=None)
            if not row and engine:
                crop=image.crop((max(0,int(left-(right-left)*1.8)),max(0,int(cy-pitch*.45)),left-5,min(height,int(cy+pitch*.45))))
                local=read(engine,ImageOps.expand(crop,border=20,fill='white'))
                candidates=[r for r in local if valid_name(clean(r['text'])) and r['score']>.45]
                row=max(candidates,key=lambda r:len(clean(r['text'])),default=None)
            output.append({'game_id':re.split('获取|獲取',clean(row['text']))[0] if row else '', 'level':None,'job':'','confidence':round(row['score'],3) if row else 0})
        if len(output)==len(aligned) and sum(bool(m['game_id']) for m in output)>=2:return output
    return []

def recognize(path):
    with Image.open(path) as source:image=ImageOps.exif_transpose(source).convert('RGB')
    image.thumbnail((1800,1800))
    if image.width<700:image=image.resize((image.width*4,image.height*4),Image.Resampling.NEAREST)
    engine=make_engine();rows=read(engine,image)
    members=table_members(rows);layout='party_table'
    if not members:members=hud_members(image,rows,engine);layout='party_hud'
    unique=[];seen=set()
    for row in members:
        key=name_key(row['game_id'])
        if key and key in seen:continue
        seen.add(key);unique.append(row)
    return {'accepted':len(unique)>=2,'layout':layout if unique else None,'members':unique,'needs_confirmation':True}

if __name__=='__main__':print(json.dumps(recognize(sys.argv[1]),ensure_ascii=False))
