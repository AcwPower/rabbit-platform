"""Small shared validator; importing it never loads an OCR model."""
import math

def validate_regions(value):
    if value is None: return None
    if not isinstance(value,dict) or not value or 'character' not in value or set(value)-{'character','map'}:
        raise ValueError('Choose a character region and optionally a map region')
    result={}
    for kind,box in value.items():
        if not isinstance(box,dict) or set(box)!={'x','y','w','h'}: raise ValueError('Invalid region')
        if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for v in box.values()): raise ValueError('Invalid coordinate')
        x,y,w,h=(float(box[k]) for k in ('x','y','w','h'))
        if min(x,y)<0 or min(w,h)<.02 or x+w>1.00001 or y+h>1.00001: raise ValueError('Region is outside image')
        result[kind]={'x':x,'y':y,'w':w,'h':h}
    return result
