import type { CSSProperties } from 'react'

interface IconProps {
  name: string
  filled?: boolean
  size?: number
  className?: string
  style?: CSSProperties
}

export default function Icon({ name, filled = false, size = 24, className = '', style }: IconProps) {
  const fillVal = filled ? 1 : 0
  return (
    <span
      className={`material-symbols-outlined ${className}`}
      style={{
        fontVariationSettings: `'FILL' ${fillVal}, 'wght' 300, 'GRAD' 0, 'opsz' ${size}`,
        verticalAlign: 'middle',
        lineHeight: 1,
        fontSize: size,
        ...style,
      }}
    >
      {name}
    </span>
  )
}
