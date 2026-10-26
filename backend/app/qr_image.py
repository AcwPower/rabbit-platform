"""Validate QR image contents locally without opening or storing the decoded link."""

def contains_qr(image):
    import cv2
    import numpy as np
    cv2.setNumThreads(1)
    gray = np.asarray(image.convert('L'))
    detector = cv2.QRCodeDetector()
    candidates=[gray]
    if min(gray.shape)>200:
        candidates.append(cv2.resize(gray,None,fx=.5,fy=.5,interpolation=cv2.INTER_AREA))
    candidates += [255 - pixels for pixels in candidates]
    for pixels in candidates:
        try:
            text, _, _ = detector.detectAndDecode(pixels)
        except (cv2.error, UnicodeDecodeError):
            continue
        if text:
            return True
    return False
