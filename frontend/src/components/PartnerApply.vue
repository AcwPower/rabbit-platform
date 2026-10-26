<script setup>
import {ref} from 'vue'
import {ArrowRight,LoaderCircle} from 'lucide-vue-next'
import {api} from '../api'
import AccountContact from './AccountContact.vue'
import HumanCheck from './HumanCheck.vue'
const props=defineProps({card:Object,characters:{type:Array,default:()=>[]}}),emit=defineEmits(['saved'])
const busy=ref(false),contactBusy=ref(false),error=ref(''),human=ref(null)
const role=props.card.kind==='job'?'fighter':props.card.target_role
const f=ref({card_id:props.card.id,role,game_id:'',level:Math.max(70,props.card.level_min),job:props.card.target_job||'',flower:role==='priest'?(props.card.flower==='afk'?'afk':'active'):'none',notes:'',contact:{wechat:'',qr:''},challenge_id:'',answer:'',website:''})
function character(id){const c=props.characters.find(c=>c.id===Number(id));if(c){f.value.game_id=c.name;f.value.level=c.level;f.value.job=c.job||''}}
if(props.characters.length)character(props.characters[0].id)
function changeRole(){f.value.flower=f.value.role==='priest'?'active':'none'}
async function submit(){if(busy.value||contactBusy.value)return;busy.value=true;error.value='';try{emit('saved',await api('/partners/applications',{method:'POST',data:f.value}))}catch(e){error.value=e.message;human.value?.refresh()}finally{busy.value=false}}
</script>
<template><form class="stack" @submit.prevent="submit"><div class="selected-card"><small>{{card.kind==='job'?'邀请祭司加入你的队伍':'申请加入对方队伍'}}</small><h3>{{card.game_id}} <span>Lv.{{card.level}}</span></h3></div>
<label v-if="card.kind==='job'">我的队长身份<select v-model="f.role" @change="changeRole"><option value="fighter">打手队长</option><option value="priest">祭司队长</option></select></label><p v-else class="hint">以{{f.role==='fighter'?'打手':'祭司'}}身份申请。对方要求 Lv.{{card.level_min}}–{{card.level_max}}。</p>
<label v-if="characters.length">已保存角色<select @change="character($event.target.value)"><option value="">选择角色快速填写</option><option v-for="c in characters" :value="c.id">{{c.name}} · Lv.{{c.level}}</option></select></label>
<div class="form-grid"><label>游戏 ID<input v-model="f.game_id" maxlength="40" required></label><label>角色等级<input v-model.number="f.level" type="number" min="1" max="300" required></label></div>
<label v-if="card.target_job">职业<input v-model="f.job" required maxlength="30" :placeholder="card.target_job"><small class="hint">对方需要{{card.target_job}}，请选择对应角色。</small></label><label v-if="f.role==='priest'">我的花类型<select v-model="f.flower"><option value="active">活花</option><option value="afk">死花</option></select></label>
<AccountContact v-model="f.contact" @validating="contactBusy=$event"/><label>留言 <span class="optional">选填</span><textarea v-model="f.notes" maxlength="400" rows="2" placeholder="地图、上线时间或其他安排"></textarea></label><HumanCheck ref="human" v-model="f"/>
<p class="hint">同意后开放双方微信。添加微信并确认安排后，由{{card.kind==='job'?'你（邀请方队长）':'发布者队长'}}在页面确认入队。</p><p v-if="error" class="error" role="alert">{{error}}</p><button class="button primary full" :disabled="busy||contactBusy"><LoaderCircle v-if="busy" :size="17" class="spin"/>{{card.kind==='job'?'发送入队邀请':'发送入队请求'}}<ArrowRight :size="16"/></button></form></template>
