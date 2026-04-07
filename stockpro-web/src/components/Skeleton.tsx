interface SkeletonProps {
  width?: string | number
  height?: string | number
  borderRadius?: number
  className?: string
}

export default function Skeleton({ width = '100%', height = 20, borderRadius = 8, className = '' }: SkeletonProps) {
  return (
    <div
      className={className}
      style={{
        width,
        height,
        borderRadius,
        background: '#1c1917',
        animation: 'pulse 1.5s ease-in-out infinite',
      }}
    />
  )
}
