"""Registration-only image checks. OCR is a format check, not proof of ownership."""
import io
import math
import httpx
from PIL import Image, ImageOps
from .config import settings
from .security import fail

MAX_UPLOAD = 5 * 1024 * 1024

def prepare_screenshot(raw):
    if len(raw) > MAX_UPLOAD:
        fail('FILE_TOO_LARGE', '角色截图不能超过 5 MB', 413)
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ('PNG', 'JPEG', 'WEBP') or getattr(source, 'n_frames', 1) != 1:
                raise ValueError()
            if source.width * source.height > 12000000 or min(source.size) < 160:
                raise ValueError()
            source.load()
            rgba = ImageOps.exif_transpose(source).convert('RGBA')
            image = Image.new('RGB', rgba.size, 'white')
            image.paste(rgba, mask=rgba.getchannel('A'))
            image.thumbnail((2000, 2000))
    except Exception:
        fail('INVALID_CHARACTER_IMAGE', '图片无效：请上传清晰的 PNG/JPEG/WebP 角色截图，尺寸至少 160 × 160 且不超过 1200 万像素', 422)
    # Re-encode to strip metadata and embedded payloads. Store only this reviewed image.
    for quality in (94, 88, 80):
        out = io.BytesIO()
        image.save(out, format='JPEG', quality=quality)
        if out.tell() <= 1500000:
            return out.getvalue()
    fail('CHARACTER_IMAGE_TOO_COMPLEX', '图片内容过多，请只截取完整的角色能力窗口后重试', 422)

async def review_screenshot(raw):
    try:
        async with httpx.AsyncClient(timeout=22) as client:
            response = await client.post(settings.ocr_url + '/recognize', content=raw,
                headers={'X-OCR-Secret': settings.ocr_secret, 'Content-Type': 'application/octet-stream'})
    except httpx.HTTPError:
        fail('CHARACTER_REVIEW_UNAVAILABLE', '截图审核暂不可用，请稍后重试，账号尚未创建', 503)
    if response.status_code == 422:
        fail('CHARACTER_IMAGE_REJECTED', '无法识别角色能力信息，请上传左侧完整的「角色能力」窗口；个人情报资料卡不能用于注册', 422)
    if response.status_code != 200:
        fail('CHARACTER_REVIEW_UNAVAILABLE', '截图审核繁忙，请稍后重试，账号尚未创建', 503)
    try:
        result = response.json()
        # During a rolling worker update the previous ability-only response remains valid.
        candidates=result.get('registration_candidates', [{**result,'panel_type':'ability','panel_detected':result.get('character_panel')}])
        for candidate in candidates[:2]:
            confidence = candidate.get('confidence', {})
            name, level, job = candidate.get('game_id'), candidate.get('level'), candidate.get('job')
            valid = (candidate.get('panel_detected') is True and candidate.get('panel_type') == 'ability'
                and isinstance(name, str) and 1 <= len(name.strip()) <= 40 and type(level) is int and 1 <= level <= 300
                and isinstance(job, str) and 1 <= len(job.strip()) <= 30)
            for field, threshold in (('game_id', .90), ('level', .93), ('job', .85)):
                score = float(confidence.get(field, 0))
                valid = valid and math.isfinite(score) and threshold <= score <= 1
            if valid:
                return {'game_id': name.strip(), 'level': level, 'job': job.strip(),
                    'confidence': {key: confidence[key] for key in ('game_id', 'level', 'job')}}
        fail('CHARACTER_IMAGE_REJECTED', '图片不符合要求：必须包含完整的「角色能力」窗口，清晰显示名字、职业、等级和属性信息；只有「个人情报」或宠物信息无法通过', 422)
    except (ValueError, TypeError, KeyError, AttributeError):
        fail('CHARACTER_REVIEW_UNAVAILABLE', '截图审核结果异常，请稍后重试，账号尚未创建', 503)
