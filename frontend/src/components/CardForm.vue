<script setup>
import {ref,computed,watch} from 'vue'
import {ArrowRight,Info,LoaderCircle,ChevronDown} from 'lucide-vue-next'
import {api,token,auth,features,saveManaged} from '../api'
import {priceToInput,priceFromInput} from '../card-pricing'
import {retryableSubmission} from '../retryable-submission'
import HumanCheck from './HumanCheck.vue'
import AccountContact from './AccountContact.vue'
import OcrInput from './OcrInput.vue'
import MapInput from './MapInput.vue'
import TimeRange from './TimeRange.vue'
import PartyImport from './PartyImport.vue'
import Sheet from './Sheet.vue'
const props=defineProps({kind:String,initial:Object,manage:String,maps:Array,characters:Array})
const emit=defineEmits(['saved','roster-updated']);const busy=ref(false),contactBusy=ref(false),error=ref(''),human=ref(null)
const importing=ref(false),importedCount=ref(props.initial?.confirmed_boss_count||0)
function rosterSaved(team){f.value.version=team.version;importedCount.value=team.confirmed_boss_count;if(bossSlots.value<importedCount.value)bossSlots.value=importedCount.value;emit('roster-updated')}
const uncertain=ref(false),guestManage=token()
const send=retryableSubmission(options=>api(options.path,options))
const f=ref({game_id:'',level:null,map_name:'',capacity:6,fighter_count:1,priest_count:0,flower:props.kind==='boss'?'any':'none',price_mode:props.kind==='boss'?'any':'',price_currency:'rmb',price:null,night_price:null,level_min:20,level_max:60,exp_min:100000,exp_max:250000,start_time:'20:00',end_time:'02:00',notes:'',duration_hours:24,contact:{wechat:'',qr:''},public_contact:false,challenge_id:'',answer:'',website:'',version:null})
if(props.initial){for(const k of Object.keys(f.value))if(props.initial[k]!==undefined&&props.initial[k]!==null)f.value[k]=props.initial[k];f.value.contact={wechat:'',qr:'',...props.initial.contact};f.value.public_contact=Boolean(props.initial.public_contact)}
const selectedCharacter=ref(props.characters?.find(c=>c.name===f.value.game_id&&c.level===f.value.level)?.id||'')
const expLow=ref((props.initial?.exp_min??100000)/10000),expHigh=ref((props.initial?.exp_max??250000)/10000)
const teammateNeed=ref(props.initial?.teammate_need||'none')
const teammateLevelMin=ref(props.initial?.teammate_level_min??1),teammateLevelMax=ref(props.initial?.teammate_level_max??300)
const bossSlots=ref(props.initial?.boss_slots??(props.initial?props.initial.capacity-props.initial.fighter_count-props.initial.priest_count:4))
const minBossSlots=computed(()=>Math.max(1,importedCount.value))
const maxBossSlots=computed(()=>6-f.value.fighter_count-f.value.priest_count-(teammateNeed.value==='none'?0:1))
const gameCoins=computed(()=>f.value.price_mode==='hour'&&f.value.price_currency==='meso')
const priceInput=computed({get:()=>priceToInput(f.value.price,gameCoins.value),set:v=>f.value.price=priceFromInput(v,gameCoins.value)})
const nightInput=computed({get:()=>priceToInput(f.value.night_price,gameCoins.value),set:v=>f.value.night_price=priceFromInput(v,gameCoins.value)})
watch(()=>f.value.price_currency,()=>{f.value.price=null;f.value.night_price=null})
watch(()=>f.value.price_mode,mode=>{f.value.price=null;f.value.night_price=null;if(mode!=='hour')f.value.price_currency='rmb'})
watch(maxBossSlots,max=>{if(bossSlots.value>max&&max>=minBossSlots.value)bossSlots.value=max})
function expandInvalid(e){const details=e.target.closest('details');if(details)details.open=true}
function fillOcr(data){if(data.game_id)f.value.game_id=data.game_id;if(data.level)f.value.level=data.level;if(data.map_name)f.value.map_name=data.map_name}
function character(id){selectedCharacter.value=id;const c=props.characters?.find(x=>x.id===Number(id));if(c){f.value.game_id=c.name;f.value.level=c.level}}
// Registration saves the first character; later additions must not replace the default.
if(!props.initial&&props.characters?.length)character([...props.characters].sort((a,b)=>a.id-b.id)[0].id)
watch(()=>[f.value.game_id,f.value.level],()=>{const c=props.characters?.find(x=>x.id===Number(selectedCharacter.value));if(c&&(c.name!==f.value.game_id||c.level!==f.value.level))selectedCharacter.value=''})
async function submit(){if(busy.value||contactBusy.value)return;if(!uncertain.value&&!f.value.contact.wechat?.trim()&&!f.value.contact.qr){error.value='填写微信号或上传微信二维码，任选一种即可。';return}busy.value=true;error.value='';const manage=props.manage||(!auth.user?guestManage:'');try{
  f.value.exp_min=Math.round(Number(expLow.value)*10000);f.value.exp_max=Math.round(Number(expHigh.value)*10000)
  const data={...f.value,price:f.value.price===''?null:f.value.price,night_price:f.value.night_price===''?null:f.value.night_price}
  if(props.kind==='team'){data.boss_slots=bossSlots.value;if(features.teammate_recruitment){data.teammate_need=teammateNeed.value;if(teammateNeed.value!=='none'){data.teammate_level_min=teammateLevelMin.value;data.teammate_level_max=teammateLevelMax.value}}}
  const result=await send({path:`/${props.kind}-cards${props.initial?'/'+props.initial.id:''}`,method:props.initial?'PUT':'POST',data,manage})
  if(manage)saveManaged(props.kind,result.id,manage,result.map_name)
  emit('saved',{...result,manage})
}catch(e){uncertain.value=Boolean(e.uncertain);error.value=e.fields?.length?e.fields.map(x=>`${x.field}: ${x.message}`).join('；'):e.message;if(!e.uncertain)human.value?.refresh()}finally{busy.value=false}}
</script>
<template>
  <form @submit.prevent="submit" @invalid.capture="expandInvalid" class="stack compact-card-form"><fieldset class="submission-fields stack" :disabled="busy||uncertain">
    <div v-if="initial&&kind==='team'" class="party-import-entry"><div><strong>录入已上车老板</strong><p class="hint">上传游戏队伍截图，核对成员及挂机时段，同步剩余老板位。</p></div><button type="button" class="button" @click="importing=true">识图录入成员</button></div>
    <OcrInput include-map @apply="fillOcr"/>
    <div class="form-section">
      <div class="section-label"><span>01</span> {{kind==='boss'?'角色与地图':'角色与队伍'}}</div>
      <label v-if="characters?.length">已保存角色<select :value="selectedCharacter" @change="character($event.target.value)"><option value="">手动填写</option><option v-for="c in characters" :key="c.id" :value="c.id">{{c.name}} · Lv.{{c.level}}</option></select></label>
      <div class="form-grid">
        <label>游戏 ID<input v-model="f.game_id" required maxlength="40" placeholder="你的游戏角色名"></label>
        <label>角色等级<input type="number" v-model.number="f.level" required min="1" max="300"></label>
      </div>
      <MapInput v-model="f.map_name" :options="maps" required/>
      <div v-if="kind==='team'" class="form-grid">
        <label :class="{'full-row':!features.teammate_recruitment}">需要几位老板<select v-model.number="bossSlots" required><option v-for="n in Math.max(0,maxBossSlots)" :key="n" :value="n" :disabled="n<minBossSlots">{{n}} 位老板</option></select></label>
        <label v-if="features.teammate_recruitment">队友配置<select v-model="teammateNeed"><option value="dragon_knight">需要龙骑</option><option value="priest">需要祭司</option><option value="none">无需招募</option></select></label>
      </div>
      <div v-if="features.teammate_recruitment&&kind==='team'&&teammateNeed!=='none'" class="form-grid">
        <label>{{teammateNeed==='priest'?'祭司':'龙骑'}}最低等级<input type="number" v-model.number="teammateLevelMin" min="1" :max="teammateLevelMax||300" step="1" required></label>
        <label>{{teammateNeed==='priest'?'祭司':'龙骑'}}最高等级<input type="number" v-model.number="teammateLevelMax" :min="teammateLevelMin||1" max="300" step="1" required></label>
      </div>
      <p v-if="features.teammate_recruitment&&kind==='team'&&teammateNeed!=='none'" class="hint">发布时同步招募一位{{teammateNeed==='priest'?'祭司':'龙骑'}}队友，加微信谈妥后由你确认入队。</p>
    </div>
    <div class="form-section">
      <div class="section-label"><span>02</span> {{kind==='boss'?'想要挂机的时段':'经验、收费与时段'}}</div>
      <details v-if="kind==='boss'" class="form-more"><summary>经验和收费偏好 <small>{{expLow}}–{{expHigh}} 万 / 小时 · {{f.price_mode==='any'?'自由协商':f.price_mode==='hour'?'按小时':'包经验'}}</small><ChevronDown :size="16"/></summary>
      <div class="form-grid">
        <label>最低经验 / 小时（万）<input type="number" v-model.number="expLow" min="0" max="10000" step="1" required></label>
        <label>最高经验 / 小时（万）<input type="number" v-model.number="expHigh" min="0.1" max="10000" step="0.1" required></label>
      </div>
      <div class="form-grid">
        <label :class="{'full-row':!f.price_mode||f.price_mode==='any'}">收费{{kind==='boss'?'偏好':'模式'}}<select v-model="f.price_mode" required><option value="" disabled>{{kind==='boss'?'按小时 / 包经验 / 自由协商':'按小时 / 包经验'}}</option><option value="hour">按小时</option><option value="experience">包经验</option><option v-if="kind==='boss'" value="any">自由协商</option></select></label>
        <div v-if="f.price_mode&&f.price_mode!=='any'" class="price-field">
          <div class="price-field-heading"><label for="card-price">{{f.price_mode==='hour'?(kind==='boss'?'每小时预算':'每小时收费'):'1 元对应经验'}}</label><select v-if="f.price_mode==='hour'" v-model="f.price_currency" aria-label="收费币种"><option value="rmb">人民币</option><option value="meso">游戏币</option></select></div>
          <span class="input-with-unit" :class="{'game-coin-input':gameCoins}"><input id="card-price" type="number" v-model="priceInput" :min="gameCoins?0.0001:0.01" :max="gameCoins?100000000:999999" :step="gameCoins?0.0001:0.01" :required="kind==='team'" :placeholder="gameCoins?'填写数量（万）':f.price_mode==='hour'?'填写金额':'填写经验'" :aria-label="gameCoins?'每小时收费（万游戏币）':f.price_mode==='hour'?'每小时收费（元）':'1 元对应经验（万）'"><span class="input-unit" aria-hidden="true">{{gameCoins?'万':f.price_mode==='hour'?'元':'万'}}</span></span>
        </div>
      </div>
      </details>
      <template v-else>
      <div class="form-grid">
        <label>最低经验 / 小时（万）<input type="number" v-model.number="expLow" min="0" max="10000" step="1" required></label>
        <label>最高经验 / 小时（万）<input type="number" v-model.number="expHigh" min="0.1" max="10000" step="0.1" required></label>
      </div>
      <div class="form-grid">
        <label :class="{'full-row':!f.price_mode||f.price_mode==='any'}">收费{{kind==='boss'?'偏好':'模式'}}<select v-model="f.price_mode" required><option value="" disabled>{{kind==='boss'?'按小时 / 包经验 / 自由协商':'按小时 / 包经验'}}</option><option value="hour">按小时</option><option value="experience">包经验</option><option v-if="kind==='boss'" value="any">自由协商</option></select></label>
        <div v-if="f.price_mode&&f.price_mode!=='any'" class="price-field">
          <div class="price-field-heading"><label for="card-price">{{f.price_mode==='hour'?(kind==='boss'?'每小时预算':'每小时收费'):'1 元对应经验'}}</label><select v-if="f.price_mode==='hour'" v-model="f.price_currency" aria-label="收费币种"><option value="rmb">人民币</option><option value="meso">游戏币</option></select></div>
          <span class="input-with-unit" :class="{'game-coin-input':gameCoins}"><input id="card-price" type="number" v-model="priceInput" :min="gameCoins?0.0001:0.01" :max="gameCoins?100000000:999999" :step="gameCoins?0.0001:0.01" :required="kind==='team'" :placeholder="gameCoins?'填写数量（万）':f.price_mode==='hour'?'填写金额':'填写经验'" :aria-label="gameCoins?'每小时收费（万游戏币）':f.price_mode==='hour'?'每小时收费（元）':'1 元对应经验（万）'"><span class="input-unit" aria-hidden="true">{{gameCoins?'万':f.price_mode==='hour'?'元':'万'}}</span></span>
        </div>
      </div>
      </template>
      <TimeRange v-model:start="f.start_time" v-model:end="f.end_time"/>
      <p class="hint">北京时间 · {{f.end_time<=f.start_time?'结束时间为次日':'当天时段'}} · 经验为预估值</p>
    </div>
    <div class="form-section">
      <div class="section-label"><span>03</span> 联系方式</div>
      <AccountContact v-model="f.contact" @validating="contactBusy=$event"/><p v-if="kind==='boss'" class="hint">发布后，首位成功认领的打手即可查看你的微信，系统会通知你，无需再次同意。微信不会公开展示。</p>
      <p v-if="kind==='team'&&f.public_contact" class="warning">联系方式已公开，所有访客可见。可在“更多设置”中关闭。</p>
    </div>
    <details class="form-more">
      <summary><span>更多设置</span><small>选填</small><ChevronDown :size="16"/></summary>
      <div class="stack">
        <template v-if="kind==='team'">
          <div class="form-grid"><label>老板最低等级<input type="number" v-model.number="f.level_min" min="1" max="300" required></label><label>老板最高等级<input type="number" v-model.number="f.level_max" min="1" max="300" required></label></div>
          <label v-if="f.price_mode==='hour'">包夜价（{{gameCoins?'万游戏币':'元'}}）<input type="number" v-model="nightInput" :min="gameCoins?0.0001:0.01" :max="gameCoins?100000000:999999" :step="gameCoins?0.0001:0.01" placeholder="不提供可留空"></label>
        </template>
        <label v-if="!initial">需求展示时长（不是挂机时长）<select v-model.number="f.duration_hours"><option :value="6">6 小时</option><option :value="12">12 小时</option><option :value="24">24 小时</option><option :value="72">3 天</option><option :value="168">7 天</option></select></label>
        <label>补充说明<textarea v-model="f.notes" maxlength="600" rows="2" placeholder="职业、路线或补药安排，可留空"></textarea></label>
        <label v-if="kind==='team'" class="check-label"><input type="checkbox" v-model="f.public_contact">主动公开联系入口</label>
        <p v-if="kind==='team'&&f.public_contact" class="warning">公开联系方式可能带来骚扰或被采集。</p>
      </div>
    </details>
    <HumanCheck v-if="!initial" ref="human" v-model="f"/>
    <p class="disclaimer"><Info :size="15"/> 平台仅撮合，不收款、不担保。请遵守游戏条款，谨慎交易。</p>
    <p v-if="!auth.user" class="hint">记录会自动保存在当前浏览器的“我的记录”。建议额外备份管理链接，避免清除浏览器数据后丢失。</p>
    </fieldset><p v-if="uncertain" class="hint">核对成功后会自动保存记录，无需重新填写。请暂时不要关闭本页。</p><p v-if="error" class="error" role="alert">{{error}}</p>
    <button class="button primary full" :disabled="busy||contactBusy"><LoaderCircle v-if="busy" :size="18" class="spin"/>{{busy?'正在保存…':uncertain?'核对上次提交结果':initial?'保存修改':kind==='team'?'发布队伍':'发布求带'}}<ArrowRight v-if="!busy" :size="17"/></button>
  </form>
  <Sheet v-if="importing" title="识图录入已上车老板" wide @close="importing=false"><PartyImport :team="initial" @saved="rosterSaved"/></Sheet>
</template>
