import asyncio,io,os,subprocess,tempfile,hmac,json,sys
from fastapi import FastAPI,Request,HTTPException
from PIL import Image,ImageOps
from .ocr_regions import validate_regions

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
gate=asyncio.Semaphore(1)
secret=os.environ['OCR_SECRET']
Image.MAX_IMAGE_PIXELS=12000000

def recognize(raw,regions=None,mode=None):
    with tempfile.TemporaryDirectory(prefix='rabbit-ocr-') as directory:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width*image.height>12000000 or image.format not in ('JPEG','PNG','WEBP'):raise ValueError('Invalid image')
            image=ImageOps.exif_transpose(image).convert('RGB')
            path=directory+'/input.png';image.save(path)
        args=[sys.executable,'-m','app.party_ocr' if mode=='party' else 'app.ocr_engine',path]
        if regions is not None:args.append(json.dumps(regions,separators=(',',':')))
        result=subprocess.run(args,capture_output=True,timeout=19,check=True,env={**os.environ,'OMP_THREAD_LIMIT':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
        return json.loads(result.stdout)

@app.post('/recognize')
async def process(request:Request):
    if not hmac.compare_digest(request.headers.get('x-ocr-secret',''),secret):raise HTTPException(403)
    if gate.locked():raise HTTPException(429,'OCR busy')
    try:regions=validate_regions(json.loads(request.headers['x-ocr-regions']) if request.headers.get('x-ocr-regions') else None)
    except (ValueError,TypeError):raise HTTPException(400,'Invalid regions')
    raw=await request.body()
    if len(raw)>5*1024*1024:raise HTTPException(413)
    async with gate:
        try:return await asyncio.to_thread(recognize,raw,regions,request.headers.get('x-ocr-mode'))
        except Exception:raise HTTPException(422,'Unable to recognize image')
