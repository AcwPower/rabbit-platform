import test from 'node:test'
import assert from 'node:assert/strict'
import {scheduleClock,scheduleDay,scheduleDuration,scheduleProgress,endInput,endTimestamp,nextTeamEnd} from '../src/boarding-schedule.js'
const now=Date.parse('2026-10-25T16:00:00Z')
const member={status:'boarded',match:{planned_start_at:'2026-10-25T12:00:00Z',boarded_at:'2026-10-25T12:30:00Z',expected_end_at:'2026-10-25T18:00:00Z',finished_at:null}}
test('Beijing appointment display distinguishes dates across midnight',()=>{
 assert.equal(scheduleDay(member.match.planned_start_at,now),'昨天 ')
 assert.equal(scheduleDay(member.match.expected_end_at,now),'今天 ')
 assert.equal(scheduleClock(member.match.expected_end_at),'02:00')
 assert.equal(scheduleDuration(member.match.planned_start_at,member.match.expected_end_at),'6 小时')
 assert.equal(scheduleDay('2026-10-26T18:00:00Z',now),'明天 ')
})
test('progress uses planned end, preserves actual time and never completes overdue bookings',()=>{
 assert.equal(scheduleProgress(member,now),'剩余 2 小时')
 assert.equal(scheduleProgress(member,now+3*3600000),'已超时 1 小时')
 assert.equal(member.status,'boarded')
 assert.equal(member.match.boarded_at,'2026-10-25T12:30:00Z')
 assert.equal(scheduleProgress({...member,status:'contacted'},now),'等待确认上车')
 assert.equal(scheduleProgress({status:'contacted',match:{planned_start_at:'2026-10-25T17:00:00Z'}},now),'1 小时后上车')
 assert.equal(scheduleProgress({status:'pending',side:'applicant'},now),'等待老板同意')
})
test('Beijing inputs roundtrip regardless of host timezone and old records use team end',()=>{
 assert.equal(endInput('2026-10-25T18:00:00Z'),'2026-10-26T02:00')
 assert.equal(endTimestamp('2026-10-26T02:00'),'2026-10-25T18:00:00.000Z')
 assert.equal(nextTeamEnd('02:00',Date.parse('2026-10-25T12:30:00Z')),'2026-10-25T18:00:00.000Z')
})
