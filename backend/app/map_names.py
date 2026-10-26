import json,re,unicodedata
from pathlib import Path

CATALOG=json.loads((Path(__file__).parent/'data'/'popular_maps.json').read_text())
POPULAR_MAPS=CATALOG['maps']
ROMANS=dict(zip(('I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII'),range(1,13)))
CHINESE=dict(zip(('一','二','三','四','五','六','七','八','九','十','十一','十二'),range(1,13)))

def map_key(name):
    name=re.sub(r'[\s\u200B-\u200D\uFEFF]+','',unicodedata.normalize('NFKC',name))
    name=re.sub(r'(?<![A-Za-z])[IVX]+(?![A-Za-z])',lambda m:str(ROMANS.get(m[0].upper(),m[0])),name,flags=re.I)
    name=re.sub(r'(?<=[\u3400-\u9fff<])[一二三四五六七八九十]+(?=号|层|地区|军营)',lambda m:str(CHINESE.get(m[0],m[0])),name)
    return name.lower()

def map_options(extras):
    names={}
    for name in [*POPULAR_MAPS,*sorted(extras)]:
        if name and map_key(name):names.setdefault(map_key(name),name.strip())
    return list(names.values())
