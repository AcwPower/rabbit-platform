<script setup>
import {computed,ref,watch,onMounted,onUnmounted} from 'vue'
import {Users,Clock3,ChevronDown,ArrowUpRight,ArrowRight} from 'lucide-vue-next'
import {api,labels} from '../api'
import {priceValue,priceUnit} from '../card-pricing'
import {timelineTime,endInput,endTimestamp,nextTeamEnd,scheduleClock,scheduleDay,scheduleDuration,scheduleProgress} from '../boarding-schedule'
const props=defineProps({teams:Array})
const emit=defineEmits(['open','detail','refresh','notice','publish'])
const current=computed(()=>(props.teams||[]).filter(t=>t.current)),history=computed(()=>(props.teams||[]).filter(t=>!t.current))
const now=ref(Date.now()),busy=ref(null),editing=ref(null),start=ref(''),end=ref(''),error=ref(''),ending=ref(null)
watch(()=>props.teams,()=>now.value=Date.now())
let timer
onMounted(()=>{timer=setInterval(()=>now.value=Date.now(),30000)})
onUnmounted(()=>clearInterval(timer))
const riding=t=>t.members.filter(m=>['boarded','disputed'].includes(m.status))
const scheduled=t=>t.members.filter(m=>['contacted','boarded','disputed'].includes(m.status))
const waiting=t=>t.members.filter(m=>m.status==='pending')
const past=t=>t.members.filter(m=>!['pending','contacted','boarded','disputed'].includes(m.status))
const summary=computed(()=>({riding:current.value.reduce((s,t)=>s+riding(t).length,0),waiting:current.value.reduce((s,t)=>s+waiting(t).length+t.members.filter(m=>m.status==='contacted').length,0),due:current.value.reduce((s,t)=>s+riding(t).filter(m=>Date.parse(m.match.expected_end_at)<=now.value+1800000).length,0)}))
const roster=t=>[...waiting(t),...scheduled(t).sort((a,b)=>{const priority=m=>m.status==='contacted'?2:0;return priority(a)-priority(b)||(Date.parse(a.match.expected_end_at)||Infinity)-(Date.parse(b.match.expected_end_at)||Infinity)})]
const startAt=m=>m.match?.planned_start_at||m.requested_start_at
const endAt=m=>m.match?.expected_end_at||(m.requested_start_at&&m.duration_hours?new Date(Date.parse(m.requested_start_at)+m.duration_hours*3600000).toISOString():null)
const endingSoon=m=>['boarded','disputed'].includes(m.status)&&Date.parse(endAt(m))>now.value&&Date.parse(endAt(m))<=now.value+1800000
const overdue=m=>['boarded','disputed'].includes(m.status)&&Date.parse(endAt(m))<=now.value
function memberState(m){return m.status==='pending'?(m.side==='applicant'?'等待处理':'新申请'):m.status==='contacted'?'待上车':m.status==='disputed'?'存在争议':overdue(m)?'超时挂机':endingSoon(m)?'即将到时':'挂机中'}
function editSchedule(id){for(const t of current.value){const m=t.members.find(m=>m.application_id===id);if(m?.match){editEnd(m,t);return}}}
defineExpose({editSchedule})
async function accept(m){if(busy.value)return;busy.value=m.application_id;error.value='';try{await api('/applications/'+m.application_id+'/accept',{method:'POST'});emit('refresh');emit('open',m.application_id);emit('notice','已同意，联系老板谈妥后确认上车')}catch(e){error.value=e.message;emit('refresh')}finally{busy.value=null}}
function editEnd(m,t){editing.value=m.match.id;start.value=endInput(m.match.planned_start_at||new Date());end.value=endInput(m.match.expected_end_at||nextTeamEnd(t.card.end_time));error.value='';ending.value=null}
async function action(m,action){busy.value=m.application_id;error.value='';try{await api('/matches/'+m.match.id+'/'+action,{method:'POST'});ending.value=null;emit('refresh');emit('notice',action==='board'?'已确认上车，老板已收到通知':'挂机已结束，老板位已释放')}catch(e){error.value=e.message;if(e.code==='VERSION_CONFLICT'){editing.value=null;emit('refresh');error.value='时段已在其他页面更新，已刷新。请重新打开调整时间。'}}finally{busy.value=null}}
async function ignoreReminder(m){busy.value=m.application_id;error.value='';try{await api('/matches/'+m.match.id+'/reminders/ignore',{method:'POST',data:{version:m.match.schedule_version}});emit('refresh');emit('notice','已忽略本次时段提醒，老板继续挂机')}catch(e){error.value=e.message;if(e.code==='VERSION_CONFLICT'){editing.value=null;emit('refresh');error.value='时段已在其他页面更新，已刷新。请重新打开调整时间。'}}finally{busy.value=null}}
async function saveEnd(m){busy.value=m.application_id;error.value='';try{await api('/matches/'+m.match.id+'/schedule',{method:'PUT',data:{planned_start_at:endTimestamp(start.value),expected_end_at:endTimestamp(end.value),version:m.match.schedule_version}});editing.value=null;emit('refresh');emit('notice','约定时段已更新，已通知老板')}catch(e){error.value=e.message;if(e.code==='VERSION_CONFLICT'){editing.value=null;emit('refresh');error.value='时段已在其他页面更新，已刷新。请重新打开调整时间。'}}finally{busy.value=null}}
</script>
<template>
<div class="captain-dashboard">
  <div class="captain-overview"><span><i class="tiny-dot"></i><strong>{{summary.riding}}</strong> 位挂机中</span><span><strong>{{summary.waiting}}</strong> 位等待上车</span><span :class="{urgent:summary.due}"><Clock3 :size="14"/><strong>{{summary.due}}</strong> 位即将 / 已到时</span><small>北京时间</small></div>
  <p v-if="error" class="error" role="alert">{{error}}</p>
  <div v-if="!current.length" class="empty-state compact"><Users :size="32"/><h2>还没有正在管理的队伍</h2><p>发布队伍后，老板的申请、上车时段和结束状态会集中显示在这里。</p><button class="button primary" @click="emit('publish')">发布队伍</button></div>
  <article v-for="team in current" :key="team.card.id" class="captain-team">
    <header class="captain-team-head"><div><div class="captain-team-eyebrow">队伍 #{{team.card.id}} <span class="tag">{{labels[team.card.status]}}</span></div><h3>{{team.card.map_name}}</h3><p>{{team.card.start_time}} — {{team.card.end_time<=team.card.start_time?'次日 ':''}}{{team.card.end_time}} · {{priceValue(team.card)}} {{priceUnit(team.card)}}</p></div><div class="captain-team-tools"><span>{{riding(team).length}} 位挂机中 · 余 {{team.card.remaining}} 位</span><button class="button small" @click="emit('detail',team.card)">队伍详情<ArrowUpRight :size="14"/></button></div></header>
    <div class="roster-heading"><h4>老板安排 <span>{{roster(team).length}} 位</span></h4><small>允许超时挂机 · 费用双方协商</small></div>
    <div v-if="roster(team).length" class="booking-labels booking-grid"><span>老板</span><span>约定挂机时段</span><span>当前进度</span><span>操作</span></div>
    <section v-for="member in roster(team)" :key="member.application_id" :id="'boss-booking-'+member.application_id" class="booking-row" :class="{soon:endingSoon(member),overdue:overdue(member),pending:member.status==='pending'}">
      <p v-if="member.notes" class="booking-member-note"><strong>老板留言：</strong>{{member.notes}}</p><div v-if="overdue(member)" class="booking-late-note"><Clock3 :size="14"/>超时挂机中，可继续挂机 · 超时费用由双方协商补齐尾款</div><div class="booking-grid">
        <div class="booking-person"><button @click="emit('open',member.application_id)">{{member.game_id}}<ArrowUpRight :size="13"/></button><div><small v-if="member.level">Lv.{{member.level}}</small><small v-else>等级未知</small><small v-if="member.source==='screenshot'">截图录入</small><span class="booking-status" :class="member.status">{{memberState(member)}}</span></div></div>
        <div class="booking-period" v-if="startAt(member)&&endAt(member)"><div class="booking-endpoint"><strong>{{scheduleClock(startAt(member))}}</strong><small>{{scheduleDay(startAt(member),now)}}上车</small></div><div class="booking-duration"><span>{{scheduleDuration(startAt(member),endAt(member))}}</span><ArrowRight :size="22" stroke-width="1.2"/></div><div class="booking-endpoint"><strong>{{scheduleClock(endAt(member))}}</strong><small>{{scheduleDay(endAt(member),now)}}结束</small></div></div>
        <div v-else class="booking-unscheduled"><Clock3 :size="16"/><span>时段待安排<small>联系老板后调整时间</small></span></div>
        <div class="booking-progress"><strong>{{scheduleProgress(member,now)}}</strong><small v-if="member.match?.boarded_at">实际 {{scheduleDay(member.match.boarded_at,now)}}{{scheduleClock(member.match.boarded_at)}} 上车</small><small v-else>{{member.status==='pending'?(member.side==='applicant'?'查看申请处理进度':'同意后可交换微信'):'微信沟通后确认上车'}}</small></div>
        <div class="booking-actions"><button v-if="member.status==='pending'&&member.side==='owner'" class="button primary small" :disabled="busy===member.application_id" @click="accept(member)">同意并查看微信</button><button v-if="member.status==='contacted'&&member.source!=='screenshot'" class="button small" @click="emit('open',member.application_id)">联系老板</button><button v-if="member.status==='pending'" class="button small" @click="emit('open',member.application_id)">{{member.side==='owner'?'详情 / 拒绝':'查看申请'}}</button><button v-else-if="member.status==='contacted'" class="button primary small" :disabled="busy===member.application_id" @click="action(member,'board')">确认上车</button><button v-else-if="member.status==='boarded'" class="button small" :disabled="busy===member.application_id" @click="ending=member.match.id;editing=null;error=''">结束挂机</button><button v-else class="button small" @click="emit('open',member.application_id)">处理争议</button><button v-if="(overdue(member)||endingSoon(member))&&!member.match?.reminder_ignored" class="booking-adjust" :disabled="busy===member.application_id" @click="ignoreReminder(member)">忽略提醒</button><span v-if="member.match?.reminder_ignored" class="booking-ignored">已忽略本次提醒</span><button v-if="member.match" class="booking-adjust" :disabled="busy===member.application_id" @click="editEnd(member,team)">调整时间</button></div>
      </div>
      <form v-if="editing===member.match?.id" class="schedule-editor" @submit.prevent="saveEnd(member)"><p v-if="member.match?.reminder_ignored" class="hint full-row">修改时段后，将按新的结束时间提醒。</p><label>约定上车（北京时间）<input type="datetime-local" v-model="start" required></label><label>约定结束（北京时间）<input type="datetime-local" v-model="end" :min="start" :max="start?endInput(Date.parse(endTimestamp(start))+7*86400000):undefined" required></label><button class="button primary small" :disabled="busy===member.application_id">保存</button><button type="button" class="button small" @click="editing=null">取消</button></form>
      <div v-if="ending===member.match?.id" class="schedule-editor"><p>结束 {{member.game_id}} 的挂机并释放 1 个老板位？老板无需再次确认。</p><button class="button primary small" :disabled="busy===member.application_id" @click="action(member,'complete')">确认结束</button><button class="button small" @click="ending=null">暂不结束</button></div>
    </section>
    <p v-if="!roster(team).length" class="booking-empty">当前没有待处理或正在挂机的老板。新的上车申请会显示在这里。</p>
    <details v-if="past(team).length" class="boarding-history"><summary>已结束及其他记录 · {{past(team).length}} <ChevronDown :size="14"/></summary><button v-for="member in past(team)" class="record-row" @click="emit('open',member.application_id)"><div><strong>{{member.game_id}}</strong><small>{{member.match?.boarded_at?timelineTime(member.match.boarded_at)+' — '+timelineTime(member.match.finished_at):'未上车'}}</small></div><span class="tag">{{labels[member.status]}}</span><ArrowUpRight :size="14"/></button></details>
  </article>
  <details v-if="history.length" class="captain-past"><summary>历史队伍 <span>{{history.length}}</span><ChevronDown :size="15"/></summary><article v-for="team in history" class="captain-team"><header class="captain-team-head"><div><h3>{{team.card.map_name}}</h3><p>队伍 #{{team.card.id}} · {{labels[team.card.status]}}</p></div><button class="button small" @click="emit('detail',team.card)">查看队伍</button></header><button v-for="member in team.members" class="record-row" @click="emit('open',member.application_id)"><div><strong>{{member.game_id}}</strong><small>{{member.match?.boarded_at?timelineTime(member.match.boarded_at)+' — '+timelineTime(member.match.finished_at):'未上车'}}</small></div><span class="tag">{{labels[member.status]}}</span></button></article></details>
</div>
</template>
