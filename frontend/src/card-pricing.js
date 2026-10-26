const amounts=new Intl.NumberFormat('zh-CN',{maximumFractionDigits:2})
export function priceValue(card,field='price'){
  if(field==='price'&&card.price_mode==='any')return '自由协商'
  if(card[field]===null||card[field]===undefined||card[field]==='')return '待议'
  if(field==='price'&&card.price_mode==='experience')return amounts.format(Number(card[field]))+' 万'
  const value=Number(card[field])
  // Compact game-coin amounts only when the displayed value remains exact.
  if(card.price_mode==='hour'&&card.price_currency==='meso'){
    if(value>=100000000&&value%1000000===0)return amounts.format(value/100000000)+'亿'
    if(value>=10000&&value%100===0)return amounts.format(value/10000)+'万'
    return amounts.format(value)
  }
  return (card.price_mode==='hour'||field==='night_price'?'¥':'')+amounts.format(value)
}
export function priceUnit(card,field='price'){
  if(field==='price'&&card.price_mode==='any')return ''
  if(field==='price'&&card.price_mode==='experience')return card.price==null||card.price===''?'':'经验 / 元'
  const currency=card.price_currency==='meso'?'游戏币':''
  return field==='night_price'?currency:`${currency}${currency?' /':'/'} 小时`
}

export function priceToInput(value,gameCoins){return value==null||value===''?'':gameCoins?Number(value)/10000:Number(value)}
export function priceFromInput(value,gameCoins){return value==null||value===''?null:gameCoins?Math.round(Number(value)*10000):Number(value)}
