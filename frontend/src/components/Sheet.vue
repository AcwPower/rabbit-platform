<script>const openSheets=[]</script>
<script setup>
import {ref,onMounted,onUnmounted,nextTick} from 'vue'
import {X} from 'lucide-vue-next'
defineProps({title:String,subtitle:String,wide:Boolean})
const emit=defineEmits(['close']);const panel=ref(null);let previous;const instance={}
function key(e){if(openSheets.at(-1)!==instance)return;if(e.key==='Escape')emit('close');if(e.key==='Tab'){const els=Array.from(panel.value.querySelectorAll('button,input,select,textarea,a[href],[tabindex]')).filter(el=>!el.matches(':disabled')&&el.tabIndex>=0&&el.getClientRects().length);const first=els[0],last=els[els.length-1];if(e.shiftKey&&(document.activeElement===first||document.activeElement===panel.value)){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}}
onMounted(async()=>{previous=document.activeElement;openSheets.push(instance);document.body.style.overflow='hidden';document.addEventListener('keydown',key);await nextTick();panel.value.focus()})
onUnmounted(()=>{openSheets.splice(openSheets.indexOf(instance),1);document.body.style.overflow=openSheets.length?'hidden':'';document.removeEventListener('keydown',key);previous?.focus()})
</script>
<template><Teleport to="body"><div class="sheet-backdrop" @click.self="emit('close')"><section class="sheet" :class="{wide}" ref="panel" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1"><div class="sheet-handle"></div><header class="sheet-head"><div><h2>{{title}}</h2><p v-if="subtitle">{{subtitle}}</p></div><button class="icon-button" aria-label="关闭" @click="emit('close')"><X :size="20"/></button></header><div class="sheet-body"><slot/></div></section></div></Teleport></template>
