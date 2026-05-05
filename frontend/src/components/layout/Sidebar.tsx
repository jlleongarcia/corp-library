import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Folder, FolderOpen, LayoutGrid } from 'lucide-react'
import { NavLink, useParams } from 'react-router-dom'
import api from '../../lib/api'
import type { Category } from '../../types'

function CategoryItem({ cat, depth = 0 }: { cat: Category; depth?: number }) {
  const params = useParams<{ categoryId?: string }>()
  const isActive = params.categoryId === String(cat.id)

  return (
    <li>
      <NavLink
        to={`/catalog/${cat.id}`}
        className={({ isActive: navActive }) =>
          `flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors
           ${navActive || isActive
             ? 'bg-blue-50 text-blue-700 font-medium'
             : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
           }`
        }
        style={{ paddingLeft: `${12 + depth * 14}px` }}
      >
        {isActive
          ? <FolderOpen className="w-4 h-4 flex-shrink-0" style={{ color: cat.color }} />
          : <Folder className="w-4 h-4 flex-shrink-0" style={{ color: cat.color }} />
        }
        <span className="truncate flex-1">{cat.name}</span>
        {cat.children_count > 0 && (
          <ChevronRight className="w-3 h-3 flex-shrink-0 text-gray-400" />
        )}
      </NavLink>
      {cat.children && cat.children.length > 0 && (
        <ul>
          {cat.children.map((child) => (
            <CategoryItem key={child.id} cat={child} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  )
}

export default function Sidebar() {
  const { data: tree = [] } = useQuery<Category[]>({
    queryKey: ['catalog', 'tree'],
    queryFn: () => api.get('/catalog/tree').then((r) => r.data),
    staleTime: 60_000,
  })

  return (
    <aside className="w-60 flex-shrink-0 bg-white border-r border-gray-200 overflow-y-auto hidden md:flex flex-col">
      <div className="p-4 border-b border-gray-100">
        <NavLink
          to="/catalog"
          className={({ isActive }) =>
            `flex items-center gap-2 text-sm font-semibold transition-colors
             ${isActive ? 'text-blue-700' : 'text-gray-700 hover:text-blue-600'}`
          }
        >
          <LayoutGrid className="w-4 h-4" />
          All Categories
        </NavLink>
      </div>
      <nav className="flex-1 p-2">
        <ul className="space-y-0.5">
          {tree.map((cat) => (
            <CategoryItem key={cat.id} cat={cat} />
          ))}
        </ul>
      </nav>
    </aside>
  )
}
