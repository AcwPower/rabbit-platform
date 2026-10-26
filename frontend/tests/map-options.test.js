import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {mapKey,mapOptions} from '../src/map-options.js'
const catalog=JSON.parse(readFileSync(new URL('../src/data/popular-maps.json',import.meta.url),'utf8'))

test('numbered areas stay together and sort numerically across Roman/full-width forms',()=>{
  const maps=mapOptions({maps:['死亡之林Ⅳ','雪人谷','死亡之林Ⅱ','死亡之林Ⅲ','死亡之林Ⅰ','遗迹之墓10','遗迹之墓2','遗迹之墓１']})
  assert.deepEqual(maps.filter(n=>n.startsWith('死亡之林')),['死亡之林Ⅰ','死亡之林Ⅱ','死亡之林Ⅲ','死亡之林Ⅳ'])
  assert.deepEqual(maps.filter(n=>n.startsWith('遗迹之墓')),['遗迹之墓１','遗迹之墓2','遗迹之墓10'])
})
test('deduplicates map IDs and equivalent names from OCR or custom entries',()=>{
  assert.deepEqual(mapOptions({entries:[{map_id:1,name:'森林迷宫Ⅲ'},{map_id:1,name:'另一个来源别名'},{map_id:2,name:'森林迷宫Ⅳ'}]},[' 森林迷宫III ','森林迷宫３','森林迷宫\u200bⅢ','森林迷宫4','']),['森林迷宫Ⅲ','森林迷宫Ⅳ'])
})
test('does not merge different submaps or unnumbered maps with separate IDs',()=>{
  const maps=mapOptions(catalog)
  assert.equal(maps.length,89)
  assert.ok(maps.includes('猴子森林'))
  assert.ok(maps.includes('猴子森林I'))
  assert.ok(maps.includes('猴子森林Ⅱ'))
  assert.notEqual(mapKey('死亡之林Ⅰ'),mapKey('死亡之林Ⅱ'))
  assert.equal(new Set(catalog.entries.map(x=>x.map_id)).size,89)
})
test('complete catalog and every form use deterministic sorted order',()=>{
  assert.deepEqual(mapOptions(catalog),catalog.maps)
  assert.deepEqual(mapOptions(catalog,[...catalog.maps].reverse()),catalog.maps)
  assert.equal(mapKey('结冰的平原Ⅱ'),mapKey('结冰的平原2'))
  assert.equal(mapKey('通天塔＜１层＞'),mapKey('通天塔<1层>'))
})
