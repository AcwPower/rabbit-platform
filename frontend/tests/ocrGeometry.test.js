import {test} from 'node:test'
import assert from 'node:assert/strict'
import {point,drawBox,moveBox,resizeBox,validBox} from '../src/ocrGeometry.js'
test('reverse drag selects the same screenshot region',()=>{
  assert.deepEqual(drawBox({x:.8,y:.7},{x:.2,y:.1}),drawBox({x:.2,y:.1},{x:.8,y:.7}))
})
test('pointer outside screenshot clamps to edge',()=>{
  assert.deepEqual(point(-20,400,{left:10,top:10,width:200,height:300}),{x:0,y:1})
})
test('moving or resizing never leaves the uploaded image',()=>{
  const box={x:.2,y:.3,w:.4,h:.5}
  assert.deepEqual(moveBox(box,2,-2),{...box,x:.6,y:0})
  const enlarged=resizeBox(box,5,5)
  assert.ok(validBox(enlarged));assert.equal(enlarged.w,.8);assert.equal(enlarged.h,.7)
  assert.ok(validBox(resizeBox(box,-5,-5)))
})
