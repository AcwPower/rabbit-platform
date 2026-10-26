import {test} from 'node:test'
import assert from 'node:assert/strict'
import {reconcileNotifications,badgeNumber} from '../src/notification-state.js'
const item=(id,kind='application')=>({id,kind,key:`${kind}:${id}`})
test('existing pending requests establish a baseline and do not ring on every poll',()=>{
  const first=reconcileNotifications({latest:[item(3)]},null)
  assert.equal(first.initial,true)
  assert.equal(reconcileNotifications({latest:[item(3)]},first.watermarks).fresh.length,0)
})
test('a replacement request alerts even when the pending count stays the same',()=>{
  const baseline=reconcileNotifications({latest:[item(3)]},null)
  const next=reconcileNotifications({latest:[item(4)]},baseline.watermarks)
  assert.deepEqual(next.fresh,[item(4)])
  assert.equal(next.initial,false)
})
test('request types with identical numeric IDs remain distinct',()=>{
  const next=reconcileNotifications({latest:[item(7),item(7,'partner_application')]},{application:7,partner_application:6})
  assert.deepEqual(next.fresh,[item(7,'partner_application')])
})
test('processing/expiry and a later reload never reset high-water marks',()=>{
  const empty=reconcileNotifications({latest:[]},{application:12,partner_application:9})
  const reload=reconcileNotifications({latest:[item(11)]},JSON.parse(JSON.stringify(empty.watermarks)))
  assert.equal(reload.fresh.length,0)
  assert.equal(reload.watermarks.application,12)
  assert.equal(badgeNumber(105),'99+')
})
test('accept and boarding events for the same application remain distinct',()=>{
  const accepted={...item(18,'progress'),application_id:4,event:'accepted'}
  const boarded={...item(19,'progress'),application_id:4,event:'boarded'}
  const baseline=reconcileNotifications({latest:[accepted]},null)
  const next=reconcileNotifications({latest:[boarded,accepted]},baseline.watermarks)
  assert.deepEqual(next.fresh,[boarded])
  assert.equal(reconcileNotifications({latest:[boarded]},next.watermarks).fresh.length,0)
})
test('due and overdue reminders announce once per phase, including after reload',()=>{
 const due={...item(27,'booking_reminder'),event:'due:1'}
 const first=reconcileNotifications({latest:[due]},null)
 assert.deepEqual(first.fresh,[due])
 assert.equal(reconcileNotifications({latest:[due]},JSON.parse(JSON.stringify(first.watermarks))).fresh.length,0)
 const late={...item(28,'booking_reminder'),event:'late:1'}
 const next=reconcileNotifications({latest:[late]},first.watermarks)
 assert.deepEqual(next.fresh,[late])
 const changed={...item(29,'booking_reminder'),event:'due:2'}
 assert.deepEqual(reconcileNotifications({latest:[changed]},next.watermarks).fresh,[changed])
})

test('a new boss claim is fresh once, and boarding remains a separate notification',()=>{
 const claimed={...item(31,'progress'),application_id:9,event:'claimed'}
 const first=reconcileNotifications({latest:[claimed]},null)
 assert.deepEqual(first.fresh,[claimed])
 const restored=JSON.parse(JSON.stringify(first.watermarks))
 assert.equal(reconcileNotifications({latest:[claimed]},restored).fresh.length,0)
 const boarded={...item(32,'progress'),application_id:9,event:'boarded'}
 assert.deepEqual(reconcileNotifications({latest:[boarded,claimed]},restored).fresh,[boarded])
})
