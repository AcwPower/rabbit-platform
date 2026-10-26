// Preserve the exact request and idempotency key until an uncertain result is resolved.
// A replay can recover an anonymous record even if its first response was lost.
export function retryableSubmission(send, makeKey=()=>crypto.randomUUID()) {
  let pending=null
  return async options=>{
    if(!pending)pending={...options,data:JSON.parse(JSON.stringify(options.data)),key:makeKey()}
    try { const result=await send(pending);pending=null;return result }
    catch(error) { if(!error.uncertain)pending=null;throw error }
  }
}
