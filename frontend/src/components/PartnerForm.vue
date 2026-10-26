<script setup>
import {ref,watch} from 'vue'
import {ArrowRight,ChevronDown,LoaderCircle} from 'lucide-vue-next'
import {api} from '../api'
import OcrInput from './OcrInput.vue'
import MapInput from './MapInput.vue'
import TimeRange from './TimeRange.vue'
import AccountContact from './AccountContact.vue'
import HumanCheck from './HumanCheck.vue'
const props=defineProps({initial:Object,characters:{type:Array,default:()=>[]},preset:{type:String,default:'recruit'}})
const emit=defineEmits(['saved','kind-change'])
const busy=ref(false),contactBusy=ref(false),error=ref(''),human=ref(null)
const f=ref({kind:props.preset,role:props.preset==='job'?'priest':'fighter',target_role:props.preset==='job'?'any':'fighter',target_job:'',game_id:'',level:70,job:'',map_name:'',flower:props.preset==='job'?'active':'any',hourly_rate:null,price_currency:props.preset==='job'?'rmb':null,level_min:1,level_max:300,start_time:'20:00',end_time:'02:00',notes:'',duration_hours:24,contact:{wechat:'',qr:''},public_contact:false,version:null,challenge_id:'',answer:'',website:''})
if(props.initial){for(const k of Object.keys(f.value))if(props.initial[k]!==undefined)f.value[k]=props.initial[k];f.value.contact={wechat:'',qr:'',...props.initial.contact};f.value.public_contact=Boolean(props.initial.public_contact)}
function character(id){const c=props.characters.find(c=>c.id===Number(id));if(c){f.value.game_id=c.name;f.value.level=c.level;f.value.job=c.job||''}}
if(!props.initial&&props.characters.length)character(props.characters[0].id)
watch(()=>f.value.kind,kind=>{emit('kind-change',kind);if(props.initial)return;if(kind==='job'){f.value.role='priest';f.value.target_role='any';f.value.flower='active';f.value.price_currency='rmb'}else{f.value.target_role='fighter';f.value.flower='any';f.value.hourly_rate=null;f.value.price_currency=null}})
watch(()=>f.value.target_role,v=>{if(f.value.kind==='recruit'&&v==='fighter')f.value.flower='any';if(v!=='fighter')f.value.target_job=''})
async function submit(){if(busy.value||contactBusy.value)return;busy.value=true;error.value='';try{const row=await api('/partners/cards'+(props.initial?'/'+props.initial.id:''),{method:props.initial?'PUT':'POST',data:f.value});emit('saved',row)}catch(e){error.value=e.fields?.length?e.fields.map(x=>x.message.replace('Value error, ','')).join('；'):e.message;human.value?.refresh()}finally{busy.value=false}}
function expandInvalid(e){const details=e.target.closest('details');if(details)details.open=true}
</script>
<template><form class="stack compact-card-form" @submit.prevent="submit" @invalid.capture="expandInvalid">
  <div class="segmented"><button type="button" :disabled="!!initial" :class="{selected:f.kind==='recruit'}" @click="f.kind='recruit'">招募队友</button><button type="button" :disabled="!!initial" :class="{selected:f.kind==='job'}" @click="f.kind='job'">祭司求职</button></div>
  <p class="hint">{{f.kind==='job'?'展示你的花类型和时薪，让合适的队长邀请你。':'打手、祭司都可以当队长，寻找一起组队的伙伴。'}}</p>
  <OcrInput include-map @apply="d=>{if(d.game_id)f.game_id=d.game_id;if(d.level)f.level=d.level;if(d.job)f.job=d.job;if(d.map_name)f.map_name=d.map_name}"/>
  <div class="form-section"><div class="section-label"><span>01</span>角色与需求</div>
    <div v-if="f.kind==='recruit'" class="form-grid"><label>我的身份<select v-model="f.role" :disabled="!!initial"><option value="fighter">打手队长</option><option value="priest">祭司队长</option></select></label><label>想找谁<select v-model="f.target_role" :disabled="!!initial"><option value="fighter">打手队友</option><option value="priest">祭司队友</option></select></label></div>
    <label v-if="f.kind==='recruit'&&f.target_role==='fighter'">打手职业<select v-model="f.target_job" :disabled="!!initial"><option value="">不限职业</option><option value="龙骑士">龙骑士</option></select></label><label v-if="characters.length">已保存角色<select @change="character($event.target.value)"><option value="">选择角色快速填写</option><option v-for="c in characters" :value="c.id">{{c.name}} · Lv.{{c.level}}</option></select></label>
    <div class="form-grid"><label>游戏 ID<input v-model="f.game_id" required maxlength="40" placeholder="你的角色名"></label><label>角色等级<input type="number" v-model.number="f.level" min="1" max="300" required></label></div>
    <label v-if="f.kind==='job'||f.target_role==='priest'">{{f.kind==='job'?'我的花类型':'需要的花类型'}}<select v-model="f.flower"><option v-if="f.kind==='recruit'" value="any">活花 / 死花均可</option><option value="active">活花</option><option value="afk">死花</option></select></label>
    <div v-if="f.kind==='recruit'" class="form-grid"><label>{{f.target_role==='priest'?'祭司':'打手'}}最低等级<input type="number" v-model.number="f.level_min" min="1" :max="f.level_max||300" step="1" required></label><label>{{f.target_role==='priest'?'祭司':'打手'}}最高等级<input type="number" v-model.number="f.level_max" :min="f.level_min||1" max="300" step="1" required></label></div>
    <div v-if="f.kind==='job'" class="form-grid"><label>收费币种<select v-model="f.price_currency"><option value="rmb">人民币 RMB</option><option value="meso">游戏币</option></select></label><label>{{f.price_currency==='rmb'?'每小时（元）':'每小时（游戏币）'}}<input type="number" v-model="f.hourly_rate" :min="f.price_currency==='rmb'?'0.01':'1'" max="1000000000000" :step="f.price_currency==='rmb'?'0.01':'1'" required placeholder="填写每小时收费"></label></div>
    <MapInput v-model="f.map_name" optional/>
    <TimeRange v-model:start="f.start_time" v-model:end="f.end_time"/><p class="hint">北京时间 · {{f.end_time<=f.start_time?'跨午夜，结束时间为次日':'当天时段'}}</p>
  </div>
  <div class="form-section"><div class="section-label"><span>02</span>联系方式</div><AccountContact v-model="f.contact" @validating="contactBusy=$event"/><p class="hint">默认仅在同意意向后双方可见。加微信谈妥后，由队长在页面确认入队。</p></div>
  <details class="form-more"><summary><span>更多要求</span><small>选填</small><ChevronDown :size="16"/></summary><div class="stack"><label>职业<input v-model="f.job" maxlength="30" placeholder="如龙骑士、祭司"></label><div v-if="f.kind==='job'" class="form-grid"><label>对方最低等级<input type="number" v-model.number="f.level_min" min="1" max="300" required></label><label>对方最高等级<input type="number" v-model.number="f.level_max" min="1" max="300" required></label></div><label>补充说明<textarea v-model="f.notes" rows="2" maxlength="600" placeholder="分成、经验要求或补药安排，可留空"></textarea></label><label v-if="!initial">有效期<select v-model.number="f.duration_hours"><option :value="6">6 小时</option><option :value="24">24 小时</option><option :value="72">3 天</option><option :value="168">7 天</option></select></label><label class="check-label"><input type="checkbox" v-model="f.public_contact">主动公开联系方式</label><p v-if="f.public_contact" class="warning">所有访客都可查看，可能带来骚扰。</p></div></details>
  <HumanCheck v-if="!initial" ref="human" v-model="f"/>
  <p class="hint">费用由双方协商，平台不收款、不担保。请勿提供游戏账号密码或验证码。</p>
  <p v-if="error" class="error" role="alert">{{error}}</p><button class="button primary full" :disabled="busy||contactBusy"><LoaderCircle v-if="busy" class="spin" :size="17"/>{{busy?'正在保存…':initial?'保存修改':f.kind==='job'?'发布祭司求职':'发布队友招募'}}<ArrowRight :size="16"/></button>
</form></template>
