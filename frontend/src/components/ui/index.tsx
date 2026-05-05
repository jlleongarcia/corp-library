import { type ReactNode } from 'react'
import { cn } from '../../lib/utils'

// ── Spinner ───────────────────────────────────────────────────────────────────
export function Spinner({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'inline-block h-6 w-6 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600',
        className,
      )}
      role="status"
      aria-label="Loading"
    />
  )
}

// ── Badge ─────────────────────────────────────────────────────────────────────
interface BadgeProps {
  children: ReactNode
  className?: string
  variant?: 'default' | 'blue' | 'green' | 'red' | 'gray'
}

const BADGE_VARIANTS: Record<string, string> = {
  default: 'bg-blue-100 text-blue-700',
  blue:    'bg-blue-100 text-blue-700',
  green:   'bg-green-100 text-green-700',
  red:     'bg-red-100 text-red-700',
  gray:    'bg-gray-100 text-gray-600',
}

export function Badge({ children, className, variant = 'default' }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium',
        BADGE_VARIANTS[variant],
        className,
      )}
    >
      {children}
    </span>
  )
}

// ── Button ────────────────────────────────────────────────────────────────────
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
}

const BTN_VARIANTS: Record<string, string> = {
  primary:
    'bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed',
  secondary:
    'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 disabled:opacity-50',
  ghost:
    'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
  danger:
    'bg-red-600 text-white hover:bg-red-700 disabled:opacity-50',
}

const BTN_SIZES: Record<string, string> = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-sm',
}

export function Button({
  variant = 'primary',
  size = 'md',
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-1',
        BTN_VARIANTS[variant],
        BTN_SIZES[size],
        className,
      )}
    >
      {children}
    </button>
  )
}

// ── EmptyState ────────────────────────────────────────────────────────────────
interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {icon && <div className="mb-4 text-gray-300">{icon}</div>}
      <h3 className="text-lg font-semibold text-gray-700">{title}</h3>
      {description && <p className="mt-1 text-sm text-gray-500 max-w-sm">{description}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}
