<script setup>
import {ref,onBeforeUnmount} from 'vue'
import {ArrowRight,LoaderCircle,ImagePlus,LockKeyhole,X} from 'lucide-vue-next'
import {api,auth} from '../api'
import HumanCheck from './HumanCheck.vue'
const emit=defineEmits(['done'])
const mode=ref('login'),busy=ref(false),error=ref(''),human=ref(null),picker=ref(null)
const screenshot=ref(null),preview=ref(''),imageError=ref(''),reading=ref(false)
const f=ref({username:'',password:'',challenge_id:'',answer:'',website:''})
let sequence=0
function resetImage(){sequence++;if(preview.value)URL.revokeObjectURL(preview.value);preview.value='';screenshot.value=null;reading.value=false;imageError.value=''}
async function choose(file){
  if(!file||busy.value)return
  resetImage();const attempt=sequence
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)){imageError.value='请上传 PNG/JPEG/WebP 角色截图';return}
  if(file.size>5*1024*1024){imageError.value='角色截图不能超过 5 MB';return}
  reading.value=true;const url=URL.createObjectURL(file)
  try{
    const img=new Image();img.src=url;await img.decode()
    if(img.naturalWidth*img.naturalHeight>12000000||Math.min(img.naturalWidth,img.naturalHeight)<160)throw new Error('图片尺寸不合适，请截取清晰完整的角色能力窗口（至少 160 × 160，不超过 1200 万像素）')
    if(attempt!==sequence){URL.revokeObjectURL(url);return}
    screenshot.value=file;preview.value=url;error.value=''
  }catch(e){URL.revokeObjectURL(url);if(attempt===sequence)imageError.value=e.message?.startsWith('图片尺寸')?e.message:'无法读取图片，请重新截图后上传'}
  finally{if(attempt===sequence)reading.value=false}
}
function paste(event){
  if(mode.value!=='register')return
  const item=Array.from(event.clipboardData?.items||[]).find(item=>item.kind==='file'&&item.type.startsWith('image/'))
  if(item){event.preventDefault();event.stopPropagation();choose(item.getAsFile())}
}
function drop(event){if(!busy.value)choose(event.dataTransfer?.files?.[0])}
async function submit(){
  if(busy.value||reading.value)return
  if(mode.value==='register'&&!screenshot.value){imageError.value='请先上传个人角色截图';return}
  busy.value=true;error.value=''
  try{
    let options={method:'POST',data:f.value}
    if(mode.value==='register'){
      const form=new FormData();form.append('credentials',JSON.stringify(f.value));form.append('screenshot',screenshot.value)
      options={method:'POST',form}
    }
    Object.assign(auth,await api('/auth/'+mode.value,options));emit('done')
  }catch(e){error.value=e.message;human.value?.refresh()}
  finally{busy.value=false}
}
onBeforeUnmount(resetImage)
</script>
<template>
  <form class="stack" @submit.prevent="submit" @paste="paste" :aria-busy="busy">
    <p class="muted">打手发布队伍、接单需要登录。老板浏览队伍、发布求带和申请上车无需注册。</p>
    <div class="segmented"><button type="button" :disabled="busy" :class="{selected:mode==='login'}" @click="mode='login';error=''">登录</button><button type="button" :disabled="busy" :class="{selected:mode==='register'}" @click="mode='register';error=''">创建账号</button></div>
    <label>用户名<input v-model="f.username" :disabled="busy" minlength="3" maxlength="32" required autocomplete="username" placeholder="3–32 位中文、字母、数字或下划线"></label>
    <label>密码<input v-model="f.password" :disabled="busy" type="password" minlength="10" maxlength="128" required :autocomplete="mode==='login'?'current-password':'new-password'" placeholder="至少 10 位"></label>
    <section v-if="mode==='register'" class="registration-upload stack" aria-labelledby="registration-image-label">
      <div class="registration-label"><strong id="registration-image-label">个人角色截图 <span class="required-text">必填</span></strong><span class="hint">自动审核</span></div>
      <p class="hint">必须包含左侧完整的「角色能力」窗口：名字、职业、等级和属性信息。仅「个人情报」资料卡无法通过。</p>
      <div class="registration-drop" tabindex="0" role="group" aria-label="角色截图上传或粘贴区域" @dragover.prevent @drop.prevent="drop">
        <template v-if="preview"><img class="registration-preview" :src="preview" alt="待审核的个人角色截图"><div class="button-row"><button type="button" class="button small" :disabled="busy" @click="picker.click()">更换截图</button><button type="button" class="icon-button" :disabled="busy" aria-label="移除角色截图" @click="resetImage"><X :size="16"/></button></div><p class="hint">提交时审核，通过后与账号一起保存</p></template>
        <template v-else><ImagePlus :size="26" stroke-width="1.5"/><button type="button" class="button small" :disabled="busy||reading" @click="picker.click()">{{reading?'正在读取…':'上传角色截图'}}</button><p class="hint">可拖入图片，或点击此处后 Ctrl / ⌘ + V 粘贴<br>PNG / JPEG / WebP · 不超过 5 MB</p></template>
      </div>
      <input ref="picker" hidden type="file" accept="image/png,image/jpeg,image/webp" @change="choose($event.target.files[0]);$event.target.value=''">
      <p v-if="imageError" class="error" role="alert">{{imageError}}</p>
      <p class="hint registration-private"><LockKeyhole :size="14"/>截图加密保存，仅本人和管理员可查看。</p>
    </section>
    <HumanCheck ref="human" v-model="f"/>
    <p v-if="error" class="error" role="alert">{{error}}</p>
    <p v-if="mode==='register'" class="hint">识别出的角色会自动保存，发布前请核对角色名。截图校验不代表角色归属认证。创建账号表示同意隐私政策与防骗须知，请使用独立密码。</p>
    <p v-if="busy&&mode==='register'" class="hint" role="status">正在审核截图并创建账号，通常需要几秒钟，请勿重复提交。</p>
    <button class="button primary full" :disabled="busy||reading||(mode==='register'&&!screenshot)"><LoaderCircle v-if="busy" :size="18" class="spin"/>{{busy&&mode==='register'?'正在审核截图…':mode==='login'?'登录':'审核截图并创建账号'}}<ArrowRight v-if="!busy" :size="17"/></button>
  </form>
</template>

