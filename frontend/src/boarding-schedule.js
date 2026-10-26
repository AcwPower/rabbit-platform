const HOUR=3600000
const clock=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'})
const day=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit'})
export const timelineTime=value=>value?`${day.format(new Date(value))} ${clock.format(new Date(value))}`:'未上车'
export const endInput=value=>value?new Date(new Date(value).getTime()+8*HOUR).toISOString().slice(0,16):''
export const endTimestamp=value=>new Date(value+'+08:00').toISOString()
export function nextTeamEnd(time,now=Date.now()){
  const local=new Date(now+8*HOUR),[hours,minutes]=time.split(':').map(Number)
  local.setUTCHours(hours,minutes,0,0)
  if(local.getTime()<=now+8*HOUR)local.setUTCDate(local.getUTCDate()+1)
  return new Date(local.getTime()-8*HOUR).toISOString()
}

export const scheduleClock=value=>value?clock.format(new Date(value)):'—'
export function scheduleDay(value,now=Date.now()){
  if(!value)return ''
  const date=endInput(value).slice(0,10),today=endInput(now).slice(0,10)
  const offset=Math.round((Date.parse(date)-Date.parse(today))/86400000)
  return offset===0?'今天 ':offset===1?'明天 ':offset===-1?'昨天 ':`${Number(date.slice(5,7))}月${Number(date.slice(8,10))}日 `
}
function minutesLabel(minutes){const h=Math.floor(minutes/60),m=minutes%60;return `${h?h+' 小时':''}${h&&m?' ':''}${m?m+' 分钟':''}`||'不到 1 分钟'}
export function scheduleDuration(start,end){return minutesLabel(Math.max(0,Math.round((Date.parse(end)-Date.parse(start))/60000)))}
export function scheduleProgress(member,now=Date.now()){
  if(member.status==='pending')return member.side==='applicant'?'等待老板同意':'等待你处理'
  const match=member.match||{},start=Date.parse(match.planned_start_at),end=Date.parse(match.expected_end_at)
  if(member.status==='disputed')return '待处理争议'
  if(member.status==='contacted')return start>now?`${minutesLabel(Math.ceil((start-now)/60000))}后上车`:'等待确认上车'
  if(!Number.isFinite(end))return '结束时间待安排'
  return end>now?`剩余 ${minutesLabel(Math.ceil((end-now)/60000))}`:`已超时 ${minutesLabel(Math.floor((now-end)/60000))}`
}
