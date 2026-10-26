<script setup>
import {ref,onMounted,computed} from 'vue'
import {LockKeyhole,LoaderCircle,Check} from 'lucide-vue-next'
import {api,date} from '../api'
import ContactInput from './ContactInput.vue'
const emit=defineEmits(['saved'])
const profile=ref(null),contact=ref({wechat:'',qr:''}),busy=ref(false),validating=ref(false),error=ref(''),saved=ref(false)
const canEdit=computed(()=>profile.value&&(!profile.value.contact_next_change_at||new Date(profile.value.contact_next_change_at)<=new Date()))
async function load(){try{profile.value=await api('/profile');contact.value={wechat:'',qr:'',...profile.value.contact}}catch(e){error.value=e.message}}
async function save(){if(busy.value||validating.value)return;busy.value=true;error.value='';saved.value=false;try{profile.value=await api('/profile/contact',{method:'PUT',data:contact.value});contact.value={...profile.value.contact};saved.value=true;emit('saved',profile.value)}catch(e){error.value=e.fields?.map(x=>x.message.replace('Value error, ','')).join('；')||e.message}finally{busy.value=false}}
onMounted(load)
</script>
<template><form class="stack profile-contact-editor" @submit.prevent="save"><div class="profile-section-heading"><div><h3>微信资料</h3><p>保存后自动带入发布与申请，无需重复填写。</p></div><span class="tag">每 7 天可修改一次</span></div><template v-if="profile"><ContactInput v-if="canEdit" v-model="contact" @validating="validating=$event"/><div v-else class="profile-contact-saved"><p v-if="contact.wechat"><strong>{{contact.wechat}}</strong></p><img v-if="contact.qr" :src="contact.qr" class="qr-preview" alt="已保存的微信二维码"><p class="hint"><LockKeyhole :size="14"/>下次可修改：{{date(profile.contact_next_change_at)}}（北京时间）</p></div><p class="hint">修改将同步到仍有效的发布和申请，原有联系方式的可见范围保持不变。</p><button v-if="canEdit" class="button primary" :disabled="busy||validating"><LoaderCircle v-if="busy" :size="16" class="spin"/>{{busy?'保存中…':profile.contact?'保存微信资料':'保存微信资料并绑定账号'}}</button><p v-if="saved" class="profile-success" role="status"><Check :size="16"/>已保存，下次可修改时间：{{date(profile.contact_next_change_at)}}</p></template><p v-else-if="!error" class="hint">正在读取微信资料…</p><p v-if="error" class="error" role="alert">{{error}}</p></form></template>
