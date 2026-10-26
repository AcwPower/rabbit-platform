export const clamp = (n, min = 0, max = 1) => Math.min(max, Math.max(min, n))
export function point(clientX, clientY, bounds) {
  return {x: clamp((clientX - bounds.left) / bounds.width), y: clamp((clientY - bounds.top) / bounds.height)}
}
export function drawBox(a, b) {
  return {x: Math.min(a.x,b.x), y: Math.min(a.y,b.y), w: Math.abs(a.x-b.x), h: Math.abs(a.y-b.y)}
}
export function moveBox(box, dx, dy) {
  return {...box, x: clamp(box.x+dx,0,1-box.w), y: clamp(box.y+dy,0,1-box.h)}
}
export function resizeBox(box, dx, dy) {
  return {...box, w: clamp(box.w+dx,.02,1-box.x), h: clamp(box.h+dy,.02,1-box.y)}
}
export function validBox(box) {
  return box && ['x','y','w','h'].every(k=>Number.isFinite(box[k])) && box.x>=0 && box.y>=0 && box.w>=.02 && box.h>=.02 && box.x+box.w<=1.001 && box.y+box.h<=1.001
}
