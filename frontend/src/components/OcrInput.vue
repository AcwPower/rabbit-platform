<script setup>
import {ref,computed,onMounted,onUnmounted,nextTick,useId} from 'vue'
import {ScanLine,ImagePlus,LoaderCircle,Check,RotateCcw,MousePointer2,ChevronDown} from 'lucide-vue-next'
import {api} from '../api'
import {point,drawBox,moveBox,resizeBox,validBox} from '../ocrGeometry'
const props=defineProps({includeMap:Boolean})
const emit=defineEmits(['apply'])
const expanded=ref(false),toggle=ref(null),panelId='ocr-'+useId()
const preview=ref(''),busy=ref(false),error=ref(''),result=ref(null),input=ref(null),canvas=ref(null)
const boxes=ref({}),selected=ref('character'),changed=ref(false),drag=ref(null)
const kinds=computed(()=>props.includeMap?['character','map']:['character'])
const names={character:'角色能力',map:'小地图地址'}
let file=null,sequence=0
const canRecognize=computed(()=>kinds.value.every(kind=>validBox(boxes.value[kind])))
function style(box){return {left:box.x*100+'%',top:box.y*100+'%',width:box.w*100+'%',height:box.h*100+'%'}}
async function recognize(auto=false){
  if(!file || (!auto&&!canRecognize.value))return
  const request=++sequence
  busy.value=true;error.value='';result.value=null
  try{
    const form=new FormData();form.append('file',file)
    if(!auto)form.append('regions',JSON.stringify(Object.fromEntries(kinds.value.map(k=>[k,boxes.value[k]]))))
    const response=await api('/ocr/character',{method:'POST',form})
    if(request!==sequence)return
    result.value=response
    if(response.regions)boxes.value=response.regions
    changed.value=false
  }catch(e){if(request===sequence)error.value=e.message}
  finally{if(request===sequence)busy.value=false}
}
function process(next){
  if(!next)return
  if(next.size>5*1024*1024){error.value='图片不能超过 5 MB';return}
  if(!['image/png','image/jpeg','image/webp'].includes(next.type)){error.value='请选择 PNG、JPEG 或 WebP 图片';return}
  sequence++;file=next
  if(preview.value)URL.revokeObjectURL(preview.value)
  preview.value=URL.createObjectURL(next);boxes.value={};changed.value=false
  recognize(true)
}
function paste(e){if(!expanded.value)return;const image=Array.from(e.clipboardData?.items||[]).find(x=>x.type.startsWith('image/'));if(image){e.preventDefault();process(image.getAsFile())}}
function start(e,kind=selected.value,mode='draw'){
  if(busy.value || e.button>0)return
  e.preventDefault();selected.value=kind
  const p=point(e.clientX,e.clientY,canvas.value.getBoundingClientRect())
  drag.value={pointer:e.pointerId,start:p,kind,mode,before:boxes.value[kind]?{...boxes.value[kind]}:null}
  canvas.value.setPointerCapture(e.pointerId)
  if(mode==='draw')boxes.value={...boxes.value,[kind]:drawBox(p,p)}
}
function move(e){
  if(!drag.value || drag.value.pointer!==e.pointerId)return
  const p=point(e.clientX,e.clientY,canvas.value.getBoundingClientRect()),d=drag.value
  const dx=p.x-d.start.x,dy=p.y-d.start.y
  const box=d.mode==='draw'?drawBox(d.start,p):d.mode==='move'?moveBox(d.before,dx,dy):resizeBox(d.before,dx,dy)
  boxes.value={...boxes.value,[d.kind]:box};changed.value=true
}
function end(e){
  const d=drag.value;if(!d || d.pointer!==e.pointerId)return
  if(!validBox(boxes.value[d.kind])){
    if(d.before)boxes.value[d.kind]=d.before
    else delete boxes.value[d.kind]
  }
  drag.value=null
  if(canvas.value.hasPointerCapture(e.pointerId))canvas.value.releasePointerCapture(e.pointerId)
}
function keyBox(e,kind){
  if(busy.value || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return
  e.preventDefault()
  const dx=e.key==='ArrowLeft'?-.005:e.key==='ArrowRight'?.005:0
  const dy=e.key==='ArrowUp'?-.005:e.key==='ArrowDown'?.005:0
  boxes.value[kind]=(e.shiftKey?resizeBox:moveBox)(boxes.value[kind],dx,dy);changed.value=true
}
function apply(){
  if(!result.value || changed.value)return
  emit('apply',{game_id:result.value.game_id,level:result.value.level,map_name:props.includeMap?result.value.map_name:undefined,job:result.value.job})
  result.value=null;expanded.value=false
  nextTick(()=>toggle.value?.focus())
}
onMounted(()=>document.addEventListener('paste',paste))
onUnmounted(()=>{sequence++;document.removeEventListener('paste',paste);if(preview.value)URL.revokeObjectURL(preview.value)})
</script>
<template>
  <section class="ocr-box ocr-collapsible" @dragover.prevent @drop.prevent="expanded&&process($event.dataTransfer.files[0])">
    <button ref="toggle" class="ocr-toggle" type="button" :aria-expanded="expanded" :aria-controls="panelId" @click="expanded=!expanded">
      <ScanLine :size="18"/><span>截图识别</span><small>{{busy?'识别中…':preview?'已添加截图':'选用'}}</small><ChevronDown :size="16" :class="{rotated:expanded}"/>
    </button>
    <fieldset :id="panelId" v-show="expanded" :disabled="!expanded" class="ocr-content">
    <div class="ocr-intro">
      <span class="ocr-icon"><ScanLine :size="22"/></span>
      <div><strong>{{includeMap?'识别角色能力 + 小地图地址':'粘贴角色截图，少填一点'}}</strong><p>Ctrl / ⌘ + V 粘贴 · 也可拖入图片</p></div>
      <button class="icon-button" type="button" aria-label="选择角色截图" @click="input.click()"><ImagePlus :size="20"/></button>
      <input ref="input" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="process($event.target.files[0]);$event.target.value=''">
    </div>
    <template v-if="preview">
      <div class="ocr-selectors">
        <button v-for="kind in kinds" :key="kind" class="ocr-selector" :class="[kind,{selected:selected===kind}]" type="button" :aria-pressed="selected===kind" :disabled="busy" @click="selected=kind"><i/>{{names[kind]}}</button>
        <button class="icon-button" type="button" aria-label="重新自动定位识别框" :disabled="busy" @click="recognize(true)"><RotateCcw :size="15"/></button>
      </div>
      <div ref="canvas" class="ocr-canvas" :class="{busy}" aria-label="截图识别区域" @pointerdown="start($event)" @pointermove="move" @pointerup="end" @pointercancel="end">
        <img :src="preview" alt="角色与小地图截图预览" draggable="false">
        <template v-for="kind in kinds" :key="kind">
          <div v-if="boxes[kind]" class="ocr-region" :class="[kind,{selected:selected===kind}]" :style="style(boxes[kind])" role="group" :aria-label="names[kind]+'识别框'" tabindex="0" @pointerdown.stop="start($event,kind,'move')" @keydown="keyBox($event,kind)">
            <span class="ocr-region-label">{{names[kind]}}</span>
            <span class="ocr-resize" :aria-label="'调整'+names[kind]+'框大小'" @pointerdown.stop="start($event,kind,'resize')"/>
          </div>
        </template>
        <div v-if="busy" class="ocr-progress" role="status"><LoaderCircle class="spin" :size="18"/>正在识别{{includeMap?'两个区域':'角色信息'}}…</div>
      </div>
      <p class="hint ocr-instructions"><MousePointer2 :size="14"/>选择上方区域后拖画；拖动框移动，右下角调大小。只框住文字，地名不要包含下方小地图图像。</p>
      <button type="button" class="button small full" :disabled="busy||!canRecognize" @click="recognize(false)"><ScanLine :size="15"/>按{{includeMap?'两个框':'角色框'}}重新识别</button>
      <p v-if="changed" class="warning">框选已调整，请重新识别后再确认。</p>
      <p v-if="error" class="error" role="alert">{{error}}；仍可在下方表单手动填写。</p>
      <div v-if="result" class="ocr-fields">
        <p class="hint">拍屏和模糊字体可能识别有误，请核对后确认。{{!result.game_id||!result.level?'未识别到的字段可手动补充。':''}}</p>
        <p v-if="result.uncertain_fields?.length" class="warning">{{result.uncertain_fields.map(k=>({game_id:'角色名',level:'等级',map_name:'地图地址'}[k])).join('、')}}识别把握较低，请对照原图修改。</p>
        <div class="form-grid">
          <label>识别的游戏 ID<input v-model="result.game_id" maxlength="40" placeholder="未识别到，可手动填写"></label>
          <label>识别的等级<input v-model.number="result.level" type="number" min="1" max="300" placeholder="手动填写"></label>
        </div>
        <label v-if="includeMap">识别的地图地址<input v-model="result.map_name" maxlength="60" placeholder="未识别到，可手动填写"><small v-if="result.map_region">区域：{{result.map_region}}</small></label>
        <p v-if="result.job" class="hint">识别职业：{{result.job}}</p>
        <button class="button small full" type="button" :disabled="changed||busy" @click="apply"><Check :size="15"/>确认并填入</button>
        <details><summary>查看区域识别文字</summary><pre>{{result.text||'未识别到文字，请手动填写。'}}</pre></details>
      </div>
    </template>
    <p v-else-if="error" class="error" role="alert">{{error}}</p>
    </fieldset>
  </section>
</template>
