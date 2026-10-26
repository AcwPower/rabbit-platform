export function reconcileNotifications(data, previous) {
  const watermarks={application:0,partner_application:0,...previous}
  const fresh=[]
  for(const item of data.latest||[]) {
    if(item.id>(previous?.[item.kind]||0))fresh.push(item)
    watermarks[item.kind]=Math.max(watermarks[item.kind]||0,item.id)
  }
  return {watermarks,fresh,initial:previous==null}
}
export const badgeNumber=n=>n>99?'99+':String(n)
