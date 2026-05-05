import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Folder, Home } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import api from '../lib/api'
import type { Category, Document } from '../types'
import DocumentCard from '../components/catalog/DocumentCard'
import { Spinner, EmptyState } from '../components/ui'

function Breadcrumbs({ category }: { category: Category | undefined }) {
  if (!category) return null
  const parts = category.path ? category.path.split('/').filter(Boolean) : []

  return (
    <nav className="flex items-center gap-1 text-sm text-gray-500 flex-wrap">
      <Link to="/" className="hover:text-blue-600 transition-colors">
        <Home className="w-4 h-4" />
      </Link>
      <ChevronRight className="w-4 h-4 text-gray-300" />
      <Link to="/catalog" className="hover:text-blue-600 transition-colors">
        All Categories
      </Link>
      {parts.map((part, i) => (
        <span key={i} className="flex items-center gap-1">
          <ChevronRight className="w-4 h-4 text-gray-300" />
          <span className={i === parts.length - 1 ? 'text-gray-800 font-medium' : ''}>{part}</span>
        </span>
      ))}
    </nav>
  )
}

export default function CatalogPage() {
  const { categoryId } = useParams<{ categoryId?: string }>()
  const numId = categoryId ? parseInt(categoryId, 10) : undefined

  const { data: category } = useQuery<Category>({
    queryKey: ['catalog', 'category', numId],
    queryFn: () => api.get(`/catalog/categories/${numId}`).then((r) => r.data),
    enabled: numId !== undefined,
  })

  const { data: subCategories = [], isLoading: loadingCats } = useQuery<Category[]>({
    queryKey: ['catalog', 'categories', numId ?? null],
    queryFn: () =>
      api.get('/catalog/categories', { params: { parent_id: numId ?? null } }).then((r) => r.data),
    staleTime: 60_000,
  })

  const { data: documents = [], isLoading: loadingDocs } = useQuery<Document[]>({
    queryKey: ['catalog', 'documents', numId],
    queryFn: () =>
      api.get(`/catalog/categories/${numId}/documents`).then((r) => r.data),
    enabled: numId !== undefined,
    staleTime: 30_000,
  })

  const isLoading = loadingCats || (numId !== undefined && loadingDocs)

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Breadcrumb */}
      <Breadcrumbs category={category} />

      {/* Category header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          {category ? category.name : 'All Categories'}
        </h1>
        {category?.description && (
          <p className="mt-1 text-sm text-gray-500">{category.description}</p>
        )}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <>
          {/* Sub-categories */}
          {subCategories.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
                Sub-folders ({subCategories.length})
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {subCategories.map((cat) => (
                  <Link
                    key={cat.id}
                    to={`/catalog/${cat.id}`}
                    className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-3
                               hover:shadow-md hover:border-blue-200 transition-all group"
                  >
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ backgroundColor: cat.color + '20' }}
                    >
                      <Folder className="w-5 h-5" style={{ color: cat.color }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-sm text-gray-900 group-hover:text-blue-700 truncate transition-colors">
                        {cat.name}
                      </p>
                      <p className="text-xs text-gray-400">
                        {cat.document_count} doc{cat.document_count !== 1 ? 's' : ''}
                        {cat.children_count > 0
                          ? ` · ${cat.children_count} sub-folder${cat.children_count !== 1 ? 's' : ''}`
                          : ''}
                      </p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-gray-300 group-hover:text-blue-500 transition-colors flex-shrink-0" />
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Documents */}
          {numId !== undefined && (
            <section>
              {documents.length > 0 ? (
                <>
                  <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
                    Documents ({documents.length})
                  </h2>
                  <div className="space-y-3">
                    {documents.map((doc) => (
                      <DocumentCard key={doc.id} doc={doc} />
                    ))}
                  </div>
                </>
              ) : (
                subCategories.length === 0 && (
                  <EmptyState
                    icon={<Folder className="w-12 h-12" />}
                    title="This folder is empty"
                    description="No accessible documents were found here. Try browsing another category or use Search."
                  />
                )
              )}
            </section>
          )}

          {/* Top-level empty state */}
          {!numId && subCategories.length === 0 && (
            <EmptyState
              icon={<Folder className="w-12 h-12" />}
              title="No categories yet"
              description="Ask an admin to configure scan paths. Once the first scan completes, categories will appear here."
            />
          )}
        </>
      )}
    </div>
  )
}
