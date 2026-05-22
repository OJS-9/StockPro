export function formatCurrency(amount: number | null | undefined, currency = 'USD', locale = 'en-US'): string {
  if (amount == null) return '---'
  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(amount)
}

export function formatCompact(amount: number, currency = 'USD'): string {
  const sym = currency === 'ILS' ? '₪' : '$'
  if (amount >= 1_000_000) return `${sym}${(amount / 1_000_000).toFixed(1)}M`
  if (amount >= 1_000) return `${sym}${(amount / 1_000).toFixed(1)}K`
  return `${sym}${amount.toFixed(0)}`
}
