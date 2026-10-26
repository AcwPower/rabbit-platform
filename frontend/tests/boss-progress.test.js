import test from 'node:test'
import assert from 'node:assert/strict'
import {bossProgress} from '../src/boss-progress.js'
const member={boarded_at:'2026-10-26T14:00:00Z',expected_end_at:'2026-10-26T18:00:00Z'}
test('uses actual boarding time, crosses midnight and updates the remaining duration',()=>{
  const result=bossProgress(member,Date.parse('2026-10-26T16:00:00Z'))
  assert.equal(result.percent,50);assert.equal(result.elapsed,'2 小时');assert.equal(result.remaining,'剩余 2 小时')
  assert.equal(bossProgress({...member,expected_end_at:'2026-10-26T20:00:00Z'},Date.parse('2026-10-26T16:00:00Z')).percent,33)
})
test('only reaches 100% at the end, then stays capped and requires confirmation',()=>{
  const end=Date.parse(member.expected_end_at)
  assert.equal(bossProgress(member,end-1).percent,99)
  assert.equal(bossProgress(member,end-20*60000).tone,'soon')
  assert.equal(bossProgress(member,end).remaining,'已到时 · 待确认')
  const result=bossProgress(member,end+8*60000)
  assert.equal(result.percent,100);assert.equal(result.tone,'overdue');assert.equal(result.remaining,'已到时 8 分钟 · 待确认')
})
test('unknown schedules never fabricate progress and clock skew cannot make it negative',()=>{
  for(const changes of [{expected_end_at:null},{boarded_at:null},{expected_end_at:'bad'},{expected_end_at:member.boarded_at}]){
    const result=bossProgress({...member,...changes});assert.equal(result.percent,null);assert.equal(result.remaining,'结束时间待安排')
  }
  const result=bossProgress(member,Date.parse(member.boarded_at)-60000)
  assert.equal(result.percent,0);assert.equal(result.elapsed,'不到 1 分钟')
})
