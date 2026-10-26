import test from 'node:test'
import assert from 'node:assert/strict'
import {retryableSubmission} from '../src/retryable-submission.js'
test('lost response replays the same body, guest credential and key',async()=>{
 const calls=[];let key=0
 const send=retryableSubmission(async o=>{calls.push(structuredClone(o));if(calls.length===1)throw Object.assign(new Error('lost'),{uncertain:true});return {id:17}},()=>String(++key))
 const options={path:'/applications',method:'POST',manage:'guest-original',data:{answer:'7',contact:{wechat:'test'}}}
 await assert.rejects(send(options));options.data.answer='99'
 assert.deepEqual(await send({...options,manage:'different'}),{id:17})
 assert.deepEqual(calls[0],calls[1]);assert.equal(key,1)
 await send(options);assert.equal(key,2)
})
test('definitive validation failure permits corrected form with a new key',async()=>{
 const calls=[];let key=0
 const send=retryableSubmission(async o=>{calls.push(o);if(calls.length===1)throw new Error('validation');return {id:2}},()=>String(++key))
 await assert.rejects(send({data:{level:999}}));await send({data:{level:40}})
 assert.equal(calls[1].data.level,40);assert.notEqual(calls[0].key,calls[1].key)
})
