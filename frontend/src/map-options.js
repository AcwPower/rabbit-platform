const romans = {I:1,II:2,III:3,IV:4,V:5,VI:6,VII:7,VIII:8,IX:9,X:10,XI:11,XII:12}
const chinese = {一:1,二:2,三:3,四:4,五:5,六:6,七:7,八:8,九:9,十:10,十一:11,十二:12}
const collator = new Intl.Collator('zh-CN-u-co-pinyin', {numeric:true,sensitivity:'base'})

// Normalize comparison keys only. Keep the game's display name and distinct areas.
export function mapKey(name) {
  return String(name ?? '').normalize('NFKC').replace(/[\s\u200B-\u200D\uFEFF]+/gu,'')
    .replace(/(?<![A-Za-z])[IVX]+(?![A-Za-z])/gi, value=>romans[value.toUpperCase()] ?? value)
    .replace(/(?<=[\p{Script=Han}<])[一二三四五六七八九十]+(?=号|层|地区|军营)/gu, value=>chinese[value] ?? value)
    .toLocaleLowerCase('en')
}

export function mapOptions(catalog, extras=[]) {
  const byId=new Set(), byName=new Map()
  for (const row of catalog.entries ?? catalog.maps.map(name=>({name}))) {
    if (row.map_id && byId.has(row.map_id)) continue
    if (row.map_id) byId.add(row.map_id)
    const name=row.name.trim(), key=mapKey(name)
    if (key && !byName.has(key)) byName.set(key,name)
  }
  for (const value of extras) {
    if (typeof value!=='string') continue
    const name=value.trim(), key=mapKey(name)
    if (key && !byName.has(key)) byName.set(key,name)
  }
  return [...byName.values()].sort((a,b)=>collator.compare(mapKey(a),mapKey(b)))
}
