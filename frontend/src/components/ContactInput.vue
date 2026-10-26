<script setup>
import {ref,onUnmounted} from 'vue'
import {LockKeyhole,QrCode,X,LoaderCircle} from 'lucide-vue-next'
import {prepareQr} from '../qrImage'
const contact=defineModel(),emit=defineEmits(['validating'])
const error=ref(''),busy=ref(false),input=ref(null)
let sequence=0
function processing(value){busy.value=value;emit('validating',value)}
async function upload(file){
  if(!file)return
  const request=++sequence
  error.value='';processing(true)
  try{const qr=await prepareQr(file);if(request===sequence)contact.value={...contact.value,qr}}
  catch(e){if(request===sequence)error.value=e.message}
  finally{if(request===sequence)processing(false)}
}
function paste(e){
  const image=Array.from(e.clipboardData?.items||[]).find(item=>item.type.startsWith('image/'))
  if(!image)return
  e.preventDefault();e.stopPropagation();upload(image.getAsFile())
}
function remove(){sequence++;contact.value={...contact.value,qr:''};error.value='';processing(false)}
onUnmounted(()=>{sequence++})
</script>
<template>
  <div class="contact-input" @paste="paste">
    <label>联系微信 <input v-model="contact.wechat" maxlength="80" placeholder="填写微信号，或上传二维码" autocomplete="off"></label>
    <div class="qr-upload-area" tabindex="0" role="group" aria-label="二维码上传或粘贴区域" :aria-busy="busy" @dragover.prevent @drop.prevent.stop="upload($event.dataTransfer.files[0])" @click.self="$event.currentTarget.focus()">
      <div class="contact-row">
        <button class="button subtle" type="button" :disabled="busy" @click="input.click()"><LoaderCircle v-if="busy" :size="16" class="spin"/><QrCode v-else :size="16"/>{{busy?'正在检查二维码…':contact.qr?'更换二维码':'上传微信二维码'}}</button>
        <input ref="input" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="upload($event.target.files[0]);$event.target.value=''">
        <button v-if="contact.qr" class="icon-button" type="button" aria-label="移除二维码" @click="remove"><X :size="17"/></button>
      </div>
      <p class="hint" @click="$event.currentTarget.parentElement.focus()">点击此区域后 Ctrl / ⌘ + V 粘贴，也可拖入图片</p>
      <img v-if="contact.qr" :src="contact.qr" class="qr-preview" alt="微信二维码预览">
      <p v-if="error" class="error" role="alert">{{error}}</p>
    </div>
    <p class="hint"><LockKeyhole :size="13"/> 加密保存，默认仅向撮合对象展示。</p>
  </div>
</template>
