interface IconProps {
  name: string
  filled?: boolean
  size?: number
  className?: string
}

export default function Icon({ name, filled = false, size = 24, className = '' }: IconProps) {
  const fillVal = filled ? 1 : 0
  return (
    <span
      className={`material-symbols-outlined ${className}`}
      style={{
        fontVariationSettings: `'FILL' ${fillVal}, 'wght' 300, 'GRAD' 0, 'opsz' ${size}`,
        verticalAlign: 'middle',
        lineHeight: 1,
        fontSize: size,
      }}
    >
      {name}
    </span>
  )
}
