import jsQR from 'jsqr'

const nonQr = '上传图片非二维码'
function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file), image = new Image()
    image.onload = () => { URL.revokeObjectURL(url); resolve(image) }
    image.onerror = () => { URL.revokeObjectURL(url); reject(new Error(nonQr)) }
    image.src = url
  })
}

export async function prepareQr(file) {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw new Error(nonQr)
  if (file.size > 5 * 1024 * 1024) throw new Error('图片不能超过 5 MB，请截取二维码区域后重试')
  const image = await loadImage(file)
  if (image.width * image.height > 20000000) throw new Error('图片尺寸过大，请截取二维码区域后重试')
  const scale = Math.min(1, 1400 / Math.max(image.width, image.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(image.width * scale))
  canvas.height = Math.max(1, Math.round(image.height * scale))
  const context = canvas.getContext('2d', {willReadFrequently:true})
  context.fillStyle = '#fff'; context.fillRect(0, 0, canvas.width, canvas.height)
  context.drawImage(image, 0, 0, canvas.width, canvas.height)
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height)
  if (!jsQR(pixels.data, pixels.width, pixels.height, {inversionAttempts:'attemptBoth'})) throw new Error(nonQr)
  // Re-encode to remove metadata and keep the existing server size limit.
  let value = canvas.toDataURL('image/png')
  for (const quality of [.9, .75, .6]) {
    if (value.split(',')[1].length * .75 <= 500000) return value
    value = canvas.toDataURL('image/jpeg', quality)
  }
  if (value.split(',')[1].length * .75 > 500000) throw new Error('图片过大，请只截取二维码区域后重试')
  return value
}
