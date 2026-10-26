import {reactive} from 'vue'
export const auth=reactive({user:null,csrf:null})
export const features=reactive({teammate_recruitment:false})
export const labels={active:'招募中',full:'已满员',expired:'已过期',closed:'已下架',hidden:'已隐藏',matched:'已被认领',pending:'待处理',accepted:'已同意',joined:'已入队',rejected:'已拒绝',cancelled:'已取消',contacted:'待联系',boarded:'已上车',completed:'已完成',disputed:'有争议'}
export const flowers={active:'活花',afk:'死花',none:'无花',any:'花不限'}
export function token(){return Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('')}
export async function api(path,{method='GET',data,manage='',key,form,notify=true}={}){
  const headers={}
  if(auth.csrf)headers['X-CSRF-Token']=auth.csrf
  if(manage)headers['X-Manage-Token']=manage
  if(method!=='GET')headers['X-Idempotency-Key']=key||crypto.randomUUID()
  if(data)headers['Content-Type']='application/json'
  let result
  try{result=await fetch('/party/api'+path,{method,headers,credentials:'same-origin',body:form|| (data?JSON.stringify(data):undefined)})}
  catch{const error=new Error('连接中断，提交结果尚未确认。请恢复网络后核对上次提交结果。');error.uncertain=true;throw error}
  const json=await result.json().catch(()=>({}))
  if(!result.ok){const error=new Error(json.error?.message||'请求失败，请稍后重试');error.fields=json.error?.fields;error.code=json.error?.code;error.uncertain=result.status>=500||error.code==='REQUEST_PENDING';throw error}
  if(method!=='GET'&&notify)window.dispatchEvent(new Event('rabbit:data-changed'))
  return json
}
export async function loadSession(){Object.assign(auth,await api('/auth/session'))}
export function saved(){try{return JSON.parse(localStorage.getItem('rabbit-managed')||'[]')}catch{return []}}
export function saveManaged(type,id,manage,title){const rows=saved().filter(r=>!(r.type===type&&r.id===id));rows.unshift({type,id,manage,title});localStorage.setItem('rabbit-managed',JSON.stringify(rows.slice(0,100)));window.dispatchEvent(new Event('rabbit:managed-changed'))}
export function manageLink(type,id,manage){return `${location.origin}/party/#manage/${type}/${id}/${manage}`}
export function number(n){return new Intl.NumberFormat('zh-CN',{maximumFractionDigits:1}).format(n/10000)}
export function date(s){return new Intl.DateTimeFormat('zh-CN',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Shanghai',hour12:false}).format(new Date(s))}
export function age(s){const m=Math.max(0,Math.floor((Date.now()-new Date(s))/60000));return m<1?'刚刚发布':m<60?`${m} 分钟前`:m<1440?`${Math.floor(m/60)} 小时前`:`${Math.floor(m/1440)} 天前`}
