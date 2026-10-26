import base64, io
import cv2
from PIL import Image

def qr_image():
    params=cv2.QRCodeEncoder_Params()
    params.correction_level=cv2.QRCodeEncoder_CORRECT_LEVEL_H
    modules=cv2.QRCodeEncoder_create(params).encode('https://example.com/qr-contact-test')
    modules=cv2.copyMakeBorder(modules,4,4,4,4,cv2.BORDER_CONSTANT,value=255)
    image=Image.fromarray(modules).convert('RGB')
    return image.resize((image.width*7,image.height*7),Image.Resampling.NEAREST)

def image_url(image,format='PNG'):
    stream=io.BytesIO();image.save(stream,format=format)
    return 'data:image/'+format.lower()+';base64,'+base64.b64encode(stream.getvalue()).decode()
