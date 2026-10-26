<script setup>
import {useId} from 'vue'
import {beijingTime,sixHoursLater} from '../form-time'
defineProps({start:String,end:String})
const emit=defineEmits(['update:start','update:end'])
const id=useId()
function setStart(value){emit('update:start',value);const end=sixHoursLater(value);if(end)emit('update:end',end)}
</script>
<template>
  <div class="form-grid time-range">
    <div class="time-field"><div class="time-field-heading"><label :for="id+'-start'">开始时间</label><button type="button" class="time-now" @click="setStart(beijingTime())">此时</button></div><input :id="id+'-start'" type="time" :value="start" @input="setStart($event.target.value)" required></div>
    <label>结束时间<input type="time" :value="end" @input="emit('update:end',$event.target.value)" required></label>
  </div>
</template>
