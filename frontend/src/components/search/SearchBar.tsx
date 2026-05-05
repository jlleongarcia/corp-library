import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { cn } from '../../lib/utils'

interface SearchBarProps {
  initialValue?: string
  size?: 'default' | 'hero'
  className?: string
}

export default function SearchBar({
  initialValue = '',
  size = 'default',
  className,
}: SearchBarProps) {
  const [q, setQ] = useState(initialValue)
  const navigate = useNavigate()

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = q.trim()
    if (trimmed) navigate(`/search?q=${encodeURIComponent(trimmed)}`)
  }

  const isHero = size === 'hero'

  return (
    <form onSubmit={handleSubmit} className={cn('w-full', className)}>
      <div className="relative">
        <Search
          className={cn(
            'absolute top-1/2 -translate-y-1/2 pointer-events-none text-gray-400',
            isHero ? 'left-5 w-6 h-6' : 'left-3 w-4 h-4',
          )}
        />
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={
            isHero
              ? 'What are you looking for? (e.g. "HR onboarding form", "Q3 budget")'
              : 'Search documents…'
          }
          className={cn(
            'w-full rounded-xl border border-gray-300 bg-white text-gray-900 placeholder-gray-400',
            'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'transition-shadow hover:shadow-sm',
            isHero
              ? 'pl-14 pr-36 py-4 text-base shadow-md'
              : 'pl-9 pr-24 py-2 text-sm',
          )}
        />
        <button
          type="submit"
          className={cn(
            'absolute top-1/2 -translate-y-1/2 right-2 bg-blue-600 text-white font-semibold',
            'rounded-lg hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400',
            isHero ? 'px-6 py-2.5 text-sm' : 'px-3 py-1.5 text-xs',
          )}
        >
          Search
        </button>
      </div>
    </form>
  )
}
