import {ref,watch,onMounted,onUnmounted} from 'vue'
import {api,auth,saved} from './api'
import {reconcileNotifications} from './notification-state'

export function useNotifications() {
  const total=ref(0),counts=ref({applications:0,partners:0,updates:0}),updates=ref([]),items=ref([]),available=ref(false),banner=ref(null),soundEnabled=ref(true),soundReady=ref(false)
  let timer,context,generation=0,inflight=null,seen=null,queuedSound=false,mounted=false,disposed=false,lastPoll=0,firstRefresh=true
  const originalTitle=document.title.replace(/^(?:\(\d+ 条(?:消息|待处理)\) )+/,'')
  const read=key=>{try{return JSON.parse(localStorage.getItem(key))}catch{return null}}
  const write=(key,value)=>{try{localStorage.setItem(key,JSON.stringify(value))}catch{}}
  const managed=()=>saved().filter(r=>['boss','application'].includes(r.type)).slice(0,100).map(({type,id,manage})=>({type,id,manage}))
  const storageKey=()=>`rabbit-notifications:${auth.user?.id||'guest'}`
  soundEnabled.value=read('rabbit-notification-sound')!==false
  function play() {
    if(!soundEnabled.value||!total.value)return
    if(!context||context.state!=='running'){queuedSound=true;return}
    queuedSound=false
    try {
      const start=context.currentTime
      for(const [offset,frequency] of [[0,660],[.18,880]]) {
        const oscillator=context.createOscillator(),gain=context.createGain()
        oscillator.type='sine';oscillator.frequency.value=frequency
        gain.gain.setValueAtTime(0,start+offset);gain.gain.linearRampToValueAtTime(.11,start+offset+.025)
        gain.gain.exponentialRampToValueAtTime(.001,start+offset+.22)
        oscillator.connect(gain);gain.connect(context.destination)
        oscillator.start(start+offset);oscillator.stop(start+offset+.24)
        oscillator.onended=()=>{oscillator.disconnect();gain.disconnect()}
      }
    } catch {soundReady.value=false}
  }
  async function unlock() {
    if(!soundEnabled.value||!available.value)return
    try {
      const Audio=window.AudioContext||window.webkitAudioContext
      if(!Audio)return
      context ||=new Audio()
      if(context.state!=='running')await context.resume()
      soundReady.value=context.state==='running'
      if(queuedSound)play()
    } catch {soundReady.value=false}
  }
  function toggleSound(){soundEnabled.value=!soundEnabled.value;write('rabbit-notification-sound',soundEnabled.value);if(soundEnabled.value)unlock();else queuedSound=false}
  async function refresh(force=false) {
    available.value=Boolean(auth.user||managed().length)
    if(disposed||!available.value||inflight||(!force&&Date.now()-lastPoll<4000))return
    const epoch=generation,key=storageKey(),request={}
    inflight=request;lastPoll=Date.now()
    try {
      const records=managed()
      const data=records.length?await api('/notifications/query',{method:'POST',data:{managed:records},notify:false}):await api('/notifications')
      if(disposed||epoch!==generation)return
      total.value=data.total;counts.value=data.counts;updates.value=data.updates||[];items.value=data.latest||[]
      const disk=read(key)
      // Another open tab may have already announced the same request.
      const previous=seen||disk ? Object.fromEntries(['application','partner_application','progress','booking_reminder'].map(kind=>[kind,Math.max(seen?.[kind]||0,disk?.[kind]||0)])) : null
      const next=reconcileNotifications(data,previous)
      seen=next.watermarks;write(key,seen)
      if(!data.total){banner.value=null;queuedSound=false}
      else if(next.fresh.length || (!banner.value&&(next.initial||firstRefresh))) {
        banner.value={item:next.fresh[0]||data.latest[0],initial:next.initial||firstRefresh}
        if((!next.initial&&!firstRefresh&&next.fresh.length)||next.fresh.some(item=>item.kind==='booking_reminder'||item.event==='claimed'))play()
      } else if(banner.value&&!data.latest.some(item=>item.key===banner.value.item?.key)) {
        banner.value=null
      } else if(banner.value) {
        banner.value={...banner.value,item:data.latest.find(item=>item.key===banner.value.item?.key)}
      }
      firstRefresh=false
      document.title=data.total?`(${data.total} 条消息) ${originalTitle}`:originalTitle
    } catch(e) {
      if(epoch===generation&&e.code==='LOGIN_REQUIRED'){total.value=0;counts.value={applications:0,partners:0,updates:0};banner.value=null;queuedSound=false;document.title=originalTitle}
    } finally {if(inflight===request)inflight=null}
  }
  function visible(){if(!document.hidden)refresh()}
  function changed(){refresh(true)}
  async function markRead(ids){if(!ids.length)return;await api('/notifications/read',{method:'POST',data:{ids,managed:managed()},notify:false});generation++;inflight=null;await refresh(true)}
  function reset(){generation++;inflight=null;seen=null;firstRefresh=true;updates.value=[];items.value=[];total.value=0;counts.value={applications:0,partners:0,updates:0};banner.value=null;queuedSound=false;lastPoll=0;document.title=originalTitle;if(mounted)refresh(true)}
  watch(()=>auth.user?.id,reset)
  onMounted(()=>{mounted=true;refresh(true);timer=setInterval(()=>{if(!document.hidden||Date.now()-lastPoll>29000)refresh()},5000);document.addEventListener('visibilitychange',visible);window.addEventListener('focus',visible);window.addEventListener('rabbit:data-changed',changed);window.addEventListener('rabbit:managed-changed',changed);window.addEventListener('storage',visible);window.addEventListener('pointerdown',unlock);window.addEventListener('keydown',unlock)})
  onUnmounted(()=>{disposed=true;generation++;clearInterval(timer);document.title=originalTitle;context?.close().catch(()=>{});document.removeEventListener('visibilitychange',visible);window.removeEventListener('focus',visible);window.removeEventListener('rabbit:data-changed',changed);window.removeEventListener('rabbit:managed-changed',changed);window.removeEventListener('storage',visible);window.removeEventListener('pointerdown',unlock);window.removeEventListener('keydown',unlock)})
  return {total,counts,updates,items,available,markRead,banner,soundEnabled,soundReady,toggleSound,refresh,dismiss:()=>{banner.value=null}}
}
