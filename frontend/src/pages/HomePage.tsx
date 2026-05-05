import { useQuery } from '@tanstack/react-query'
import { Folder, FileText, ChevronRight, TrendingUp } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import api from '../lib/api'
import SearchBar from '../components/search/SearchBar'
import { Spinner } from '../components/ui'
import { useAuth } from '../hooks/useAuth'
import type { Category } from '../types'

function CategoryCard({ cat }: { cat: Category }) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate(`/catalog/${cat.id}`)}
      className="bg-white rounded-xl border border-gray-200 p-5 text-left
                 hover:shadow-md hover:border-blue-200 transition-all group w-full"
    >
      <div className="flex items-center gap-3 mb-3">
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ backgroundColor: cat.color + '20' }}
        >
          <Folder className="w-5 h-5" style={{ color: cat.color }} />
        </div>
        <h3 className="font-semibold text-gray-900 group-hover:text-blue-700 transition-colors truncate">
          {cat.name}
        </h3>
      </div>
      {cat.description && (
        <p className="text-xs text-gray-500 line-clamp-2 mb-3">{cat.description}</p>
      )}
      <div className="flex items-center justify-between text-xs text-gray-400">
        <span className="flex items-center gap-1">
          <FileText className="w-3 h-3" />
          {cat.document_count} document{cat.document_count !== 1 ? 's' : ''}
        </span>
        {cat.children_count > 0 && (
          <span>{cat.children_count} sub-folder{cat.children_count !== 1 ? 's' : ''}</span>
        )}
        <ChevronRight className="w-4 h-4 group-hover:text-blue-500 transition-colors" />
      </div>
    </button>
  )
}

export default function HomePage() {
  const { user } = useAuth()
  const { data: categories = [], isLoading } = useQuery<Category[]>({
    queryKey: ['catalog', 'categories', null],
    queryFn: () => api.get('/catalog/categories').then((r) => r.data),
    staleTime: 60_000,
  })

  const firstName = user?.display_name?.split(' ')[0] ?? user?.username ?? 'there'

  return (
    <div className="max-w-5xl mx-auto space-y-10">
      {/* Hero search */}
      <section className="bg-gradient-to-br from-corp-navy to-blue-800 rounded-2xl p-8 md:p-12 text-white">
        <h1 className="text-2xl md:text-3xl font-bold mb-1">
          Welcome, {firstName}
        </h1>
        <p className="text-blue-200 text-sm mb-6">
          Find any corporate document, form, or resource — instantly.
        </p>
        <SearchBar size="hero" />
        <p className="mt-3 text-blue-300 text-xs">
          Tip: you can search by document name, department, tags, or keywords in the description.
        </p>
      </section>

      {/* Quick how-to for new users */}
      <section className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          {
            icon: '🔍',
            title: 'Search',
            text: 'Type anything in the search bar — the system finds relevant documents automatically.',
          },
          {
            icon: '📂',
            title: 'Browse',
            text: 'Use the categories on the left sidebar to navigate by department or topic.',
          },
          {
            icon: '📋',
            title: 'Copy & Open',
            text: 'Click a document to see its details, then copy the network path to open it directly.',
          },
        ].map((tip) => (
          <div key={tip.title} className="bg-white rounded-xl border border-gray-200 p-4 flex gap-3">
            <span className="text-2xl flex-shrink-0">{tip.icon}</span>
            <div>
              <p className="font-semibold text-sm text-gray-800">{tip.title}</p>
              <p className="text-xs text-gray-500 mt-0.5">{tip.text}</p>
            </div>
          </div>
        ))}
      </section>

      {/* Categories grid */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-5 h-5 text-blue-600" />
          <h2 className="text-lg font-bold text-gray-900">Browse by Category</h2>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner />
          </div>
        ) : categories.length === 0 ? (
          <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 text-center">
            <Folder className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">No categories yet</p>
            <p className="text-xs text-gray-400 mt-1">
              Ask your admin to configure a scan path to populate the library.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {categories.map((cat) => (
              <CategoryCard key={cat.id} cat={cat} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
