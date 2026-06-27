import type { ReactNode } from 'react'

interface PageContainerProps {
  children: ReactNode
  narrow?: boolean
}

export function PageContainer({ children, narrow = false }: PageContainerProps) {
  return (
    <div className={narrow ? 'mx-auto w-full max-w-4xl' : 'w-full max-w-6xl'}>{children}</div>
  )
}
