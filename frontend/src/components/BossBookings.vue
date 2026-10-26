<script setup>
import {computed,ref,onMounted,onUnmounted,watch} from 'vue'
import {Clock3,ArrowRight,ArrowUpRight,ChevronDown} from 'lucide-vue-next'
import {labels} from '../api'
import {scheduleClock,scheduleDay,scheduleDuration,scheduleProgress,timelineTime} from '../boarding-schedule'
const props=defineProps({bookings:Array});defineEmits(['open'])
const now=ref(Date.now()),current=computed(()=>props.bookings.filter(b=>b.current)),past=computed(()=>props.bookings.filter(b=>!b.current))
const riding=b=>['boarded','disputed'].includes(b.status)
const overtime=b=>riding(b)&&Date.parse(b.expected_end_at)<=now.value
const status=b=>b.status==='disputed'?'存在争议':overtime(b)?'超时挂机':b.status==='boarded'?'挂机中':b.status==='contacted'?'待上车':b.status==='pending'?'等待打手处理':labels[b.status]
const progress=b=>b.status==='pending'?'等待打手确认申请':scheduleProgress({status:b.status,match:b},now.value)
let timer
onMounted(()=>{timer=setInterval(()=>now.value=Date.now(),30000)})
onUnmounted(()=>clearInterval(timer))
watch(()=>props.bookings,()=>now.value=Date.now())
</script>
<template><section v-if="bookings.length" class="boss-bookings" aria-label="我的挂机安排">
  <div class="boss-bookings-heading"><h2>我的挂机安排 <small v-if="current.length">{{current.length}} 条进行中</small></h2><span>北京时间</span></div>
  <article v-for="booking in current" :key="booking.application_id" class="boss-booking" :class="{overdue:overtime(booking)}">
    <header><div><h3>{{booking.map_name}}</h3><p>{{booking.game_id}} · 打手 {{booking.captain_name}}</p></div><span class="tag">{{status(booking)}}</span></header>
    <div v-if="booking.planned_start_at&&booking.expected_end_at" class="boss-booking-times">
      <div><small>约定上车</small><strong>{{scheduleClock(booking.planned_start_at)}}</strong><span>{{scheduleDay(booking.planned_start_at,now)}}</span></div>
      <div class="boss-booking-duration"><span>{{scheduleDuration(booking.planned_start_at,booking.expected_end_at)}}</span><ArrowRight :size="26" stroke-width="1.3"/></div>
      <div><small>预计结束</small><strong>{{scheduleClock(booking.expected_end_at)}}</strong><span>{{scheduleDay(booking.expected_end_at,now)}}</span></div>
    </div>
    <p v-else class="hint">时段待安排，微信沟通后由打手填写。</p>
    <div class="boss-booking-progress"><Clock3 :size="15"/><strong>{{progress(booking)}}</strong><small v-if="booking.boarded_at">实际确认上车 {{timelineTime(booking.boarded_at)}}</small></div>
    <p class="hint">{{overtime(booking)?'可继续超时挂机，尾款由双方协商。由打手手动结束，无需你确认。':riding(booking)?'你可以离开页面，上车时段由打手调整，结束时会通知你，无需再次确认。':'沟通好安排后，由打手确认上车，你无需在页面操作。'}}</p>
    <footer><span>时间调整会同步到这里</span><button class="button small" @click="$emit('open',booking)">联系与详情<ArrowUpRight :size="14"/></button></footer>
  </article>
  <details v-if="past.length" class="boss-booking-history" :open="!current.length"><summary>已结束的挂机记录 <span>{{past.length}}</span><ChevronDown :size="15"/></summary><button v-for="booking in past" :key="booking.application_id" class="record-row" @click="$emit('open',booking)"><div><strong>{{booking.map_name}} · {{booking.captain_name}}</strong><small>{{booking.boarded_at?'实际上车 '+timelineTime(booking.boarded_at):booking.planned_start_at?'约定上车 '+timelineTime(booking.planned_start_at):'未上车'}}{{booking.finished_at?' · 结束 '+timelineTime(booking.finished_at):''}}</small></div><span class="tag">{{labels[booking.status]}}</span><ArrowUpRight :size="15"/></button></details>
</section></template>
