export function sixHoursLater(time) {
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(time)) return ''
  const [hours, minutes] = time.split(':').map(Number)
  return `${String((hours + 6) % 24).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
}

export function beijingTime(date = new Date()) {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).format(date)
}
