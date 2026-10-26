const MINUTE=60000
const stamp=value=>value?Date.parse(value):NaN
const duration=minutes=>{
  const hours=Math.floor(minutes/60),rest=minutes%60
  return [hours?`${hours} 小时`:'',rest?`${rest} 分钟`:''].filter(Boolean).join(' ')||'不到 1 分钟'
}

export function bossProgress(member,now=Date.now()){
  const start=stamp(member.boarded_at),end=stamp(member.expected_end_at)
  const elapsed=Number.isFinite(start)?duration(Math.max(0,Math.floor((now-start)/MINUTE))):'待确认'
  if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start){
    return {percent:null,tone:'',remaining:'结束时间待安排',elapsed,total:'待安排'}
  }
  const overdue=now>=end
  // Round down so 100% is reserved for the actual agreed end time.
  const percent=Math.max(0,Math.min(100,Math.floor((now-start)/(end-start)*100)))
  return {percent,tone:overdue?'overdue':end-now<=30*MINUTE?'soon':'',elapsed,
    total:duration(Math.max(1,Math.round((end-start)/MINUTE))),
    remaining:overdue?`已到时${now-end>=MINUTE?' '+duration(Math.floor((now-end)/MINUTE)):''} · 待确认`:
      `剩余 ${duration(Math.ceil((end-now)/MINUTE))}`}
}
