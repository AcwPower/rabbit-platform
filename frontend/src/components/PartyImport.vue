<script setup>
import {ref,computed,onUnmounted} from 'vue'
import {ImagePlus,LoaderCircle,Users,Check} from 'lucide-vue-next'
import {api} from '../api'
import {endInput,endTimestamp,timelineTime} from '../boarding-schedule'
import {retryableSubmission} from '../retryable-submission'
const props=defineProps({team:Object});const emit=defineEmits(['saved'])
const picker=ref(null),busy=ref(false),saving=ref(false),error=ref(''),preview=ref(''),review=ref(null),members=ref([]),roster=ref([]),uncertain=ref(false),done=ref('')
const bulkStart=ref(endInput(new Date())),bulkHours=ref(6),selected=computed(()=>members.value.filter(m=>m.selected)),confirmed=ref(false)
const send=retryableSubmission(options=>api(options.path,options))
const key=s=>(s||'').normalize('NFKC').trim().toLowerCase()
function existing(m){return roster.value.find(r=>key(r.game_id)===key(m.game_id)&&['pending','contacted','boarded','disputed'].includes(r.status))}
function blocked(m){return key(m.game_id)===key(props.team.game_id)||['boarded','disputed'].includes(existing(m)?.status)}
function label(m){if(key(m.game_id)===key(props.team.game_id))return '主力打手';const row=existing(m);return row?(['boarded','disputed'].includes(row.status)?'已在挂机清单':'已有申请，将沿用原记录'):'未录入'}
function applyTimes(){for(const m of selected.value){m.started_at=bulkStart.value;m.hours=bulkHours.value}}
function end(m){const n=Date.parse(m.started_at+'+08:00')+Number(m.hours)*3600000;return Number.isFinite(n)?timelineTime(n):'请填写时间'}
async function choose(file){if(!file||busy.value||saving.value||uncertain.value)return;error.value='';done.value='';review.value=null;members.value=[];confirmed.value=false
 if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>5*1024*1024){error.value='请上传 5 MB 以内的 PNG/JPEG/WebP 队伍截图';return}
 if(preview.value)URL.revokeObjectURL(preview.value);preview.value=URL.createObjectURL(file);busy.value=true
 try{const form=new FormData();form.append('file',file);const result=await api('/captain/teams/'+props.team.id+'/roster/recognize',{method:'POST',form});const teams=await api('/captain/teams');roster.value=teams.teams.find(t=>t.card.id===props.team.id)?.members||[];review.value=result;members.value=result.members.map((m,index)=>({...m,index,selected:false,started_at:bulkStart.value,hours:bulkHours.value}))}catch(e){error.value=e.message}finally{busy.value=false}}
function paste(e){const f=Array.from(e.clipboardData?.items||[]).find(i=>i.type.startsWith('image/'));if(f){e.preventDefault();e.stopPropagation();choose(f.getAsFile())}}
async function save(){if(saving.value)return;if(!uncertain.value&&selected.value.some(blocked)){error.value='已上车成员或主力打手不能重复录入，请取消对应勾选';return}error.value='';saving.value=true
 try{const result=await send({path:'/captain/teams/'+props.team.id+'/roster/import',method:'POST',data:{review_token:review.value.review_token,version:review.value.team.version,members:selected.value.map(m=>({index:m.index,game_id:m.game_id,started_at:endTimestamp(m.started_at),duration_hours:Number(m.hours)}))}});uncertain.value=false;done.value=`已录入 ${result.imported} 位老板，队伍剩余 ${result.team.remaining} 个老板位。`;review.value=null;members.value=[];emit('saved',result.team)}catch(e){uncertain.value=Boolean(e.uncertain);error.value=e.message}finally{saving.value=false}}
onUnmounted(()=>{if(preview.value)URL.revokeObjectURL(preview.value)})
</script>
<template><div class="party-import stack" @paste="paste"><p class="hint">支持“在线队员”列表和姓名＋血条的队伍面板。识别后请核对名字，勾选已上车的老板；截图不用于自动判断角色身份。</p>
<div class="party-import-upload" tabindex="0" role="group" aria-label="上传或粘贴队伍截图" @dragover.prevent @drop.prevent.stop="choose($event.dataTransfer.files[0])"><ImagePlus :size="24"/><button type="button" class="button" :disabled="busy||saving||uncertain" @click="picker.click()">{{busy?'正在识别…':preview?'更换队伍截图':'上传队伍截图'}}</button><small>也可拖入图片，或 Ctrl / ⌘ + V 粘贴</small><input hidden ref="picker" type="file" accept="image/png,image/jpeg,image/webp" @change="choose($event.target.files[0]);$event.target.value=''"/></div>
<img v-if="preview" :src="preview" class="party-import-preview" alt="待核对的队伍截图"/>
<p v-if="busy" class="hint" role="status"><LoaderCircle :size="16" class="spin"/>正在检查截图类型并识别成员，请稍候。</p>
<form v-if="review" class="stack" @submit.prevent="save"><fieldset class="submission-fields stack" :disabled="saving||uncertain"><div class="party-import-heading"><strong><Users :size="17"/>识别到 {{members.length}} 位成员</strong><span>已选 {{selected.length}} 位老板 · 剩余 {{review.team.remaining}} 位</span></div><p class="hint">没有勾选的成员不会占老板位。文字可能有误，请对照原图修正；血条截图不包含等级。</p>
<div class="party-bulk"><label>统一上车时间（北京时间）<input v-model="bulkStart" type="datetime-local"/></label><label>挂机小时<input v-model.number="bulkHours" type="number" min="0.25" max="168" step="0.25"/></label><button type="button" class="button small" :disabled="!selected.length" @click="applyTimes">应用到已选老板</button></div>
<div v-for="m in members" :key="m.index" class="party-member" :class="{selected:m.selected}"><div class="party-member-line"><label class="check-label"><input type="checkbox" v-model="m.selected" :disabled="blocked(m)&&!m.selected"/>已上车老板</label><span class="tag">{{label(m)}}</span><small v-if="m.level">Lv.{{m.level}} · {{m.job}}</small><small v-else>等级未知</small></div><label>游戏 ID<input v-model="m.game_id" :required="m.selected" maxlength="40" placeholder="未识别清楚，请对照截图填写" @input="confirmed=false"/></label><div v-if="m.selected" class="form-grid"><label>上车时间<input type="datetime-local" v-model="m.started_at" required/></label><label>挂机时长（小时）<input type="number" min="0.25" max="168" step="0.25" v-model.number="m.hours" required/></label></div><p v-if="m.selected" class="hint">预计结束：{{end(m)}}；到时仍由打手手动结束。</p></div>
<label class="check-label"><input type="checkbox" v-model="confirmed" required/>已核对角色名、老板身份和时段，确认录入后占用老板位</label></fieldset><p v-if="selected.length>review.team.remaining" class="warning">选择人数超过剩余老板位，请减少选择，或先调整队伍老板人数再重新识别。</p><button class="button primary full" :disabled="saving||(!uncertain&&(!selected.length||!confirmed||selected.length>review.team.remaining))"><LoaderCircle v-if="saving" :size="16" class="spin"/>{{saving?'正在录入…':uncertain?'核对上次录入结果':`确认录入 ${selected.length} 位老板`}}</button></form>
<p v-if="error" class="error" role="alert">{{error}}</p><p v-if="done" class="success-text" role="status"><Check :size="18"/>{{done}}</p><p class="hint">名单和个人时段仅在你的管理清单显示。公开挂绳卡片只更新老板位数量；新录入成员没有网站账号或微信授权，不会虚构联系方式。</p></div></template>
