<script setup>
import {ref,onMounted} from 'vue'
import {LockKeyhole,Settings2} from 'lucide-vue-next'
import {api,auth} from '../api'
import ContactInput from './ContactInput.vue'
import ProfileContactEditor from './ProfileContactEditor.vue'
import Sheet from './Sheet.vue'
const contact=defineModel(),emit=defineEmits(['validating'])
const profile=ref(null),loading=ref(Boolean(auth.user)),error=ref(''),editing=ref(false)
async function load(){if(!auth.user)return;loading.value=true;emit('validating',true);try{applyProfile(await api('/profile'))}catch(e){error.value=e.message}finally{loading.value=false;emit('validating',Boolean(error.value))}}
function applyProfile(value){profile.value=value;if(value.contact)contact.value={...value.contact};error.value=''}
function saved(value){applyProfile(value);editing.value=false}
onMounted(load)
</script>
<template><div v-if="loading" class="hint">正在带入微信资料…</div><div v-else-if="error" class="error">{{error}} <button class="text-button" type="button" @click="load">重新加载</button></div><div v-else-if="auth.user&&profile?.contact" class="account-contact-summary"><div><LockKeyhole :size="17"/><strong>使用账号微信资料</strong><button type="button" class="text-button" @click="editing=true"><Settings2 :size="14"/>查看 / 修改</button></div><p>{{profile.contact.wechat||'已保存微信二维码'}}</p><p class="hint">匹配成功后按授权展示，无需重复填写。</p></div><template v-else><ContactInput v-model="contact" @validating="emit('validating',$event)"/><p v-if="auth.user" class="hint">首次提交会保存为账号微信资料，之后每 7 天最多修改一次。</p></template><Sheet v-if="editing" title="微信资料" @close="editing=false"><ProfileContactEditor @saved="saved"/></Sheet></template>
