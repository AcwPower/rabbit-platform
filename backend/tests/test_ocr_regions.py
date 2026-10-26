import io,json,uuid
import pytest,httpx
from PIL import Image
from app.ocr_regions import validate_regions
from app.ocr_engine import character_fields,map_fields,automatic_regions,character_panel

def row(text,x,y,w=70,h=35,score=.99):
    return {'text':text,'score':score,'box':[[x,y],[x+w,y],[x+w,y+h],[x,y+h]]}

def test_missing_level_label_uses_profession_row_not_hp():
    rows=[row('名字',10,50),row('包包测试',130,50,score=.82),row('职业',10,90),row('大副',130,90),row('78',130,130),row('家族',10,175),row('1465/2462',130,215),row('人气度',10,300),row('10',130,300)]
    result=character_fields(rows)
    assert result['level']==78 and result['job']=='大副'
    assert result['game_id']=='包包测试' and result['confidence']['game_id']==.82
    assert character_fields([row('血量',10,50),row('78',130,50)])['level'] is None

def test_missing_profession_label_keeps_readable_value_from_same_panel():
    rows=[row('角色能力',10,0,140),row('名字',10,60),row('TestKnight',130,60,180),
        row('龙骑士',130,100,100,score=.98),row('等级',10,140),row('116',130,140),
        row('血量',10,190),row('12956/12956',130,190,200),row('魔量',10,230),
        row('力量',10,400),row('561 (547+14)',130,400,200)]
    for scale in (.5,1,2):
        scaled=[{**r,'box':[[x*scale,y*scale] for x,y in r['box']]} for r in rows]
        fields=character_fields(scaled)
        assert fields['game_id']=='TestKnight' and fields['level']==116
        assert fields['job']=='龙骑士' and fields['confidence']['job']==.98
        assert character_panel(scaled)

def test_missing_profession_label_does_not_guess_from_unrelated_values():
    base=[row('名字',10,60),row('TestKnight',130,60,180),row('等级',10,140),row('116',130,140)]
    assert character_fields(base+[row('龙骑士',600,100)])['job']==''
    assert character_fields(base+[row('12956',130,100)])['job']==''
    assert character_fields(base+[row('家族',130,100)])['job']==''
    assert character_fields(base+[row('龙骑士',130,100),row('未知文字',135,102)])['job']==''
    # An isolated name and a later guild/HP value cannot form the name/job/level trio.
    distant=[row('名字',10,60),row('TestKnight',130,60,180),row('等级',10,400),row('116',130,400)]
    assert character_fields(distant+[row('公会名称',130,230)])['job']==''

def test_inline_english_and_chinese_fields():
    result=character_fields([row('Name: RabbitTest',10,20,250),row('Level: 68',10,60,160)])
    assert result['game_id']=='RabbitTest' and result['level']==68
    assert character_fields([row('等级：301',10,20)])['level'] is None

def test_map_address_not_toolbar_or_low_confidence_region():
    result=map_fields([row('大地图',20,0),row('神杨岛',20,50,score=.71),row('王冠之地',20,90,score=.99)])
    assert result['map_name']=='王冠之地' and result['map_region']==''

def test_autoboxes_follow_layout_at_different_scale():
    rows=[row('角色能力',480,278,125,41),row('名字',483,340,74,44),row('测试角色',605,347,95,39),row('大地图',369,278,93,39)]
    first=automatic_regions(rows,(1707,1280))
    scaled=[{**r,'box':[[x/2,y/2] for x,y in r['box']]} for r in rows]
    second=automatic_regions(scaled,(853.5,640))
    assert first['map']['y']<.27 and first['map']['y']+first['map']['h']<.34
    assert abs(first['character']['x']-second['character']['x'])<.02
    assert validate_regions(first)

@pytest.mark.parametrize('value',[
    {'map':{'x':0,'y':0,'w':1,'h':1}},
    {'character':{'x':-1,'y':0,'w':1,'h':1}},
    {'character':{'x':.9,'y':0,'w':.3,'h':1}},
    {'character':{'x':0,'y':0,'w':float('nan'),'h':1}},
    {'character':{'x':0,'y':0,'w':True,'h':1}},
])
def test_invalid_ocr_regions_are_rejected(value):
    with pytest.raises(ValueError):validate_regions(value)

def test_api_validates_and_forwards_regions(client,monkeypatch):
    image=io.BytesIO();Image.new('RGB',(200,100),'white').save(image,format='PNG')
    selected={'character':{'x':.4,'y':.1,'w':.5,'h':.8},'map':{'x':.05,'y':.1,'w':.3,'h':.3}}
    captured={}
    async def fake(self,url,**kwargs):
        captured.update(kwargs['headers'])
        return httpx.Response(200,json={'game_id':'测试','level':78,'map_name':'王冠之地','regions':selected})
    monkeypatch.setattr(httpx.AsyncClient,'post',fake)
    def send(regions):return client.post('/api/ocr/character',files={'file':('sample.png',image.getvalue(),'image/png')},data={'regions':regions},headers={'X-Idempotency-Key':str(uuid.uuid4())})
    assert send('{broken json').status_code==400
    assert send(json.dumps({'character':{'x':2,'y':0,'w':.3,'h':.3}})).status_code==400
    response=send(json.dumps(selected));assert response.status_code==200,response.text
    assert json.loads(captured['X-OCR-Regions'])==selected
    assert response.json()['map_name']=='王冠之地'
