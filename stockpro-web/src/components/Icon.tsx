import type { CSSProperties } from 'react'

interface IconProps {
  name: string
  filled?: boolean
  size?: number
  className?: string
  style?: CSSProperties
}

// Material Symbols whose visual meaning is directional ("forward", "back",
// "next", "previous", "send"). These get horizontally mirrored under dir="rtl"
// via a CSS class so they keep pointing the right way in Hebrew layouts.
// Symmetric icons (search, close, notifications, dashboard, etc.) and icons
// whose direction encodes a value rather than navigation (trending_up/down,
// play_arrow as media play) are intentionally NOT in this list.
const DIRECTIONAL = new Set([
  'arrow_back',
  'arrow_forward',
  'arrow_back_ios',
  'arrow_forward_ios',
  'chevron_left',
  'chevron_right',
  'keyboard_arrow_left',
  'keyboard_arrow_right',
  'navigate_before',
  'navigate_next',
  'first_page',
  'last_page',
  'send',
  'reply',
  'logout',
  'login',
  'east',
  'west',
])

export default function Icon({ name, filled = false, size = 24, className = '', style }: IconProps) {
  const fillVal = filled ? 1 : 0
  const directional = DIRECTIONAL.has(name) ? 'icon-directional' : ''
  return (
    <span
      className={`material-symbols-outlined ${directional} ${className}`.trim()}
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
