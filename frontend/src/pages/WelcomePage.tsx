import { Search } from 'lucide-react'
import { EmptyState } from '../components/ui'

export default function WelcomePage() {
  return (
    <EmptyState
      icon={<Search className="w-12 h-12" />}
      title="Document search is on its way"
      description="We're indexing the department shares. Search across everything you have access to will be available here soon."
    />
  )
}
