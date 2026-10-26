<script setup>
import {computed,ref,onMounted,onUnmounted,watch} from 'vue'
import {ChevronDown} from 'lucide-vue-next'
import {bossProgress} from '../boss-progress'
import {timelineTime} from '../boarding-schedule'
const props=defineProps({members:{type:Array,default:()=>[]},cardId:Number})
const expanded=ref(false),now=ref(Date.now())
const rows=computed(()=>props.members.map(member=>({...member,...bossProgress(member,now.value),label:`老板${String(member.number).padStart(2,'0')}`})))
let timer
onMounted(()=>{timer=setInterval(()=>now.value=Date.now(),30000)})
onUnmounted(()=>clearInterval(timer))
watch(()=>props.members,()=>{now.value=Date.now();if(!props.members.length)expanded.value=false})
</script>

<template>
  <section class="card-boss-progress" aria-label="老板挂机进度">
    <template v-if="rows.length">
      <div class="card-progress-heading"><span>挂机进度</span><button type="button" :aria-expanded="expanded" :aria-controls="`card-progress-${cardId}`" @click="expanded=!expanded">{{expanded?'收起时间明细':'展开时间明细'}}<ChevronDown :size="13" :class="{rotated:expanded}"/></button></div>
      <div class="card-progress-summary">
        <span v-for="member in rows" :key="member.number" class="card-progress-percent" :class="member.tone"><span>{{member.label}}</span><strong :aria-label="`${member.label} 已挂进度 ${member.percent===null?'待安排':member.percent+'%'}`">{{member.percent===null?'—':member.percent+'%'}}</strong></span>
      </div>
      <div v-if="expanded" :id="`card-progress-${cardId}`" class="card-progress-details">
        <div v-for="member in rows" :key="member.number" class="card-progress-member" :class="member.tone">
          <div class="card-progress-row"><strong>{{member.label}}</strong><span class="card-progress-remaining">{{member.remaining}}</span></div>
          <div v-if="member.percent!==null" class="card-progress-track" role="progressbar" :aria-label="`${member.label} 已挂时长进度`" :aria-valuenow="member.percent" aria-valuemin="0" aria-valuemax="100"><div :style="{width:member.percent+'%'}"></div></div>
          <div class="card-progress-row card-progress-time"><span>已挂 {{member.elapsed}}</span><span>本次时长 {{member.total}}</span></div>
          <div class="card-progress-time">{{timelineTime(member.boarded_at)}} 上车 → {{member.expected_end_at?timelineTime(member.expected_end_at):'待安排'}} 结束</div>
        </div>
        <p class="card-progress-note">北京时间 · 100% 表示约定时长已到，由打手结束挂机后释放名额。</p>
      </div>
    </template>
    <span v-else class="card-progress-empty">暂无老板上车</span>
  </section>
</template>

<style scoped>
.card-boss-progress{margin:10px 0 14px;font-size:11px;color:var(--muted)}
.card-progress-heading,.card-progress-row{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
.card-progress-heading button{display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--muted);min-height:32px;padding:4px 0}
.card-progress-heading button:hover{color:var(--text)}
.card-progress-heading svg{transition:transform .15s}.card-progress-heading .rotated{transform:rotate(180deg)}
.card-progress-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;padding-top:2px;font-variant-numeric:tabular-nums}
.card-progress-percent{display:flex;gap:5px;flex-wrap:wrap;align-items:baseline}
.card-progress-percent strong{color:var(--text);font-weight:550}
.card-progress-percent.soon strong,.soon .card-progress-remaining{color:var(--warning)}
.card-progress-percent.overdue strong,.overdue .card-progress-remaining{color:var(--danger)}
.card-progress-details{background:var(--panel2);border-radius:8px;padding:13px;margin-top:12px}
.card-progress-member+.card-progress-member{margin-top:15px}
.card-progress-row strong{color:var(--text);font-size:11px;font-weight:550}
.card-progress-remaining{color:var(--text)}
.card-progress-track{height:4px;border-radius:4px;overflow:hidden;margin:7px 0;background:var(--line)}
.card-progress-track>div{height:100%;border-radius:4px;background:var(--success)}
.soon .card-progress-track>div{background:var(--warning)}.overdue .card-progress-track>div{background:var(--danger)}
.card-progress-time{font-size:11px;line-height:1.7;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.card-progress-note{font-size:11px;margin-top:12px;line-height:1.6}
@media(pointer:coarse){.card-progress-heading button{min-height:44px}}
</style>
