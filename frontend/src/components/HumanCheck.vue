<script setup>
import {ref,onMounted} from 'vue'
import {RefreshCw,ShieldCheck} from 'lucide-vue-next'
import {api} from '../api'
const model=defineModel();const prompt=ref('');const error=ref('')
async function refresh(){try{const c=await api('/challenge');model.value.challenge_id=c.id;model.value.answer='';prompt.value=c.question;error.value=''}catch(e){error.value=e.message}}
defineExpose({refresh});onMounted(refresh)
</script>
<template><div class="human-check"><label><span><ShieldCheck :size="15"/> 简单验证 <strong>{{prompt}}</strong></span><input v-model="model.answer" inputmode="numeric" placeholder="填写答案" required autocomplete="off" aria-label="人机验证答案"></label><button type="button" class="icon-button" aria-label="刷新验证" @click="refresh"><RefreshCw :size="16"/></button><span class="error" v-if="error">{{error}}</span><input class="honeypot" tabindex="-1" aria-hidden="true" v-model="model.website" autocomplete="off" name="website"></div></template>
