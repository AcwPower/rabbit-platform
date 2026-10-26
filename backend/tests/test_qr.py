import base64, io
import pytest
from PIL import Image, ImageOps
from pydantic import ValidationError
from app.schemas import ContactInput
from app.qr_image import contains_qr
from conftest import post, card_data
from qr_helpers import qr_image, image_url

@pytest.mark.parametrize('format',['PNG','JPEG','WEBP'])
def test_qr_formats_and_roundtrip(format):
    value=ContactInput(qr=image_url(qr_image(),format)).qr
    assert ContactInput(qr=value).qr
    saved=Image.open(io.BytesIO(base64.b64decode(value.split(',')[1])))
    assert contains_qr(saved)

def test_qr_inverted_and_center_logo():
    image=qr_image()
    assert ContactInput(qr=image_url(ImageOps.invert(image))).qr
    center=image.width//2;size=image.width//16
    image.paste((50,150,80),(center-size,center-size,center+size,center+size))
    assert ContactInput(qr=image_url(image)).qr

@pytest.mark.parametrize('size',[(1,1),(400,300)])
def test_non_qr_rejected(size):
    with pytest.raises(ValidationError,match='上传图片非二维码'):
        ContactInput(wechat='still-not-a-qr',qr=image_url(Image.new('RGB',size,'orange')))

def test_non_qr_rejected_at_api(client):
    result=post(client,'/api/boss-cards',card_data(client,contact={'qr':image_url(Image.new('RGB',(100,100),'white'))}))
    assert result.status_code==422
    assert '上传图片非二维码' in result.text

def test_plain_wechat_still_valid():
    assert ContactInput(wechat='wechat-id').qr==''
