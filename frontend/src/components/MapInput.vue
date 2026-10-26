<script setup>
import {ref,computed,useId,nextTick} from 'vue'
import {ChevronDown,MapPin,Check} from 'lucide-vue-next'
import catalog from '../data/popular-maps.json'
import {mapKey,mapOptions} from '../map-options'
const props=defineProps({modelValue:{type:String,default:''},options:{type:Array,default:()=>[]},required:Boolean,optional:Boolean})
const emit=defineEmits(['update:modelValue'])
const id=useId(),input=ref(null),open=ref(false),typed=ref(false),active=ref(-1)
const maps=computed(()=>mapOptions(catalog,props.options))
const matches=computed(()=>{const q=typed.value?mapKey(props.modelValue):'';return q?maps.value.filter(m=>mapKey(m).includes(q)):maps.value})
function update(e){emit('update:modelValue',e.target.value);typed.value=true;open.value=true;active.value=-1}
function show(){typed.value=false;active.value=-1;open.value=true}
function choose(value){emit('update:modelValue',value);input.value.focus();open.value=false;active.value=-1}
function toggle(){const was=open.value;input.value.focus();open.value=!was;typed.value=false;active.value=-1}
async function move(delta){if(!matches.value.length){active.value=-1;open.value=true;return}if(!open.value){show();active.value=delta>0?0:matches.value.length-1}else active.value=(active.value+delta+matches.value.length)%matches.value.length;await nextTick();document.getElementById(id+'-option-'+active.value)?.scrollIntoView({block:'nearest'})}
function enter(e){if(!open.value)return;e.preventDefault();if(active.value>=0&&matches.value[active.value])choose(matches.value[active.value]);else open.value=false}
function blur(e){if(!e.currentTarget.contains(e.relatedTarget))open.value=false}
</script>
<template><div class="map-combobox" @focusout="blur"><label :for="id">挂机地图 <span v-if="optional" class="optional">选填</span></label><div class="map-input-wrap"><input :id="id" ref="input" :value="modelValue" :required="required" maxlength="60" placeholder="可识图填写，或选择热门地图" role="combobox" autocomplete="off" aria-autocomplete="list" :aria-expanded="open" :aria-controls="id+'-list'" :aria-activedescendant="open&&active>=0?id+'-option-'+active:undefined" @input="update" @focus="show" @click="show" @keydown.down.prevent="move(1)" @keydown.up.prevent="move(-1)" @keydown.enter="enter" @keydown.esc.stop.prevent="open=false"><button type="button" class="map-toggle" aria-label="展开热门地图" :aria-expanded="open" @mousedown.prevent @click="toggle"><ChevronDown :size="17" :class="{rotated:open}"/></button></div><div v-if="open" class="map-options-panel"><div class="map-options-heading"><span><MapPin :size="12"/>{{typed&&modelValue?'匹配地图':'热门地图'}}</span><small>{{matches.length}} 个可选</small></div><div :id="id+'-list'" role="listbox" aria-label="热门地图" class="map-options"><button v-for="(m,i) in matches" :id="id+'-option-'+i" :key="m" type="button" role="option" :aria-selected="modelValue===m" tabindex="-1" :class="{highlight:i===active}" @mousedown.prevent @click="choose(m)"><span>{{m}}</span><Check v-if="modelValue===m" :size="14"/></button><p v-if="!matches.length" class="hint map-no-results">没有匹配的热门地图，可直接使用你输入的名称。</p></div><p class="map-options-footer">可手动输入，也可识图填写 · 地图名称参考枫记排行</p></div><p v-if="optional" class="hint">留空表示地图可商量</p></div></template>
