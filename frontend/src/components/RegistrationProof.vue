<script setup>
import {ref} from 'vue'
import {Image,LoaderCircle} from 'lucide-vue-next'
import {api,date} from '../api'
const props=defineProps({userId:{type:Number,required:true}})
const open=ref(false),proof=ref(null),error=ref(''),busy=ref(false)
async function toggle(){
  if(open.value){open.value=false;proof.value=null;return}
  busy.value=true;error.value=''
  try{proof.value=await api(`/users/${props.userId}/registration-proof`);open.value=true}
  catch(e){error.value=e.message}finally{busy.value=false}
}
</script>
<template><div class="registration-proof"><button type="button" class="button small" :disabled="busy" @click="toggle"><LoaderCircle v-if="busy" :size="15" class="spin"/><Image v-else :size="15"/>{{open?'收起注册截图':'查看注册截图'}}</button><p v-if="error" class="error" role="alert">{{error}}</p><div v-if="open&&proof" class="proof-detail stack"><div><strong>{{proof.game_id}}</strong><p class="hint">Lv.{{proof.level}} · {{proof.job}} · {{date(proof.created_at)}}</p></div><img :src="proof.image" alt="与此账号关联的注册角色截图"><p class="hint">角色名为 OCR 识别结果，请结合截图核对。注册时自动格式校验通过，仅本人和管理员可查看。此记录不代表角色归属认证。</p></div></div></template>
