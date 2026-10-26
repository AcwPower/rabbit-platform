import test from 'node:test'
import assert from 'node:assert/strict'
import {sixHoursLater,beijingTime} from '../src/form-time.js'

test('six-hour defaults preserve minutes and cross midnight',()=>{
  assert.equal(sixHoursLater('09:17'),'15:17')
  assert.equal(sixHoursLater('18:00'),'00:00')
  assert.equal(sixHoursLater('23:59'),'05:59')
  assert.equal(sixHoursLater(''),'')
})
test('current time uses Beijing regardless of the browser timezone',()=>{
  assert.equal(beijingTime(new Date('2026-10-26T02:35:00Z')),'10:35')
  assert.equal(beijingTime(new Date('2026-10-26T16:07:00Z')),'00:07')
})
