import test from 'node:test'
import assert from 'node:assert/strict'
import {priceValue,priceUnit,priceToInput,priceFromInput} from '../src/card-pricing.js'

test('old RMB cards, experience pricing and free negotiation keep their units',()=>{
  assert.equal(priceValue({price_mode:'hour',price:'8.50'}),'¥8.5')
  assert.equal(priceUnit({price_mode:'hour'}),'/ 小时')
  assert.equal(priceValue({price_mode:'experience',price:8}),'8 万')
  assert.equal(priceUnit({price_mode:'experience',price:8}),'经验 / 元')
  assert.equal(priceValue({price_mode:'any',price:null}),'自由协商')
  assert.equal(priceUnit({price_mode:'any'}),'')
})
test('game coins are labeled and compacted without rounding negotiated amounts',()=>{
  const card={price_mode:'hour',price_currency:'meso',price:'1500000.00',night_price:'9000000.00'}
  assert.equal(priceValue(card),'150万')
  assert.equal(priceUnit(card),'游戏币 / 小时')
  assert.equal(priceValue(card,'night_price'),'900万')
  assert.equal(priceUnit(card,'night_price'),'游戏币')
  assert.equal(priceValue({...card,price:1500001}),'1,500,001')
  assert.equal(priceValue({...card,price:1000000000000}),'10,000亿')
  assert.equal(priceValue({...card,price:null}),'待议')
})

test('game coin form uses ten-thousands while stored amounts roundtrip unchanged',()=>{
 assert.equal(priceToInput(1500000,true),150)
 assert.equal(priceFromInput('150',true),1500000)
 for(const amount of [1,12345,1500001,1000000000000])assert.equal(priceFromInput(priceToInput(amount,true),true),amount)
 assert.equal(priceFromInput('',true),null)
 assert.equal(priceToInput(null,true),'')
 assert.equal(priceFromInput('8.50',false),8.5)
})
