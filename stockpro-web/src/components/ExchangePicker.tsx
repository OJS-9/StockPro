const EXCHANGES = [
  { value: 'US', label: 'US' },
  { value: 'TASE', label: 'TASE' },
] as const

export type Exchange = typeof EXCHANGES[number]['value']

export function appendExchangeSuffix(symbol: string, exchange: Exchange): string {
  const clean = symbol.replace(/\.TA$/i, '').toUpperCase()
  return exchange === 'TASE' ? `${clean}.TA` : clean
}

export default function ExchangePicker({
  value,
  onChange,
}: {
  value: Exchange
  onChange: (v: Exchange) => void
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value as Exchange)}
      style={{
        background: '#1c1917',
        border: '1px solid #292524',
        borderRadius: 8,
        padding: '8px 12px',
        color: '#fafaf9',
        fontSize: 14,
        fontFamily: 'Inter, sans-serif',
        cursor: 'pointer',
        minWidth: 72,
      }}
    >
      {EXCHANGES.map(ex => (
        <option key={ex.value} value={ex.value}>{ex.label}</option>
      ))}
    </select>
  )
}
