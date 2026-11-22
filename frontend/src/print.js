// Prints a page of this app through a hidden iframe (no popup blockers, no new window).
export function printUrl(url) {
  const f = document.createElement('iframe')
  f.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden'
  f.src = url
  document.body.appendChild(f)
  setTimeout(() => f.remove(), 120000)
}

export function printBill(id, size, duplicate = false) {
  printUrl(`/print/bill/${id}?size=${size || '80'}${duplicate ? '&dup=1' : ''}`)
}

export function printKot(kot) {
  try { localStorage.setItem('mfr_kot', JSON.stringify(kot)) } catch { /* ignore */ }
  printUrl('/print/kot')
}
