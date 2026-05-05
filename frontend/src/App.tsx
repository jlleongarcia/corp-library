import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import LoginPage from './pages/LoginPage'
import HomePage from './pages/HomePage'
import SearchPage from './pages/SearchPage'
import CatalogPage from './pages/CatalogPage'
import DocumentPage from './pages/DocumentPage'
import AdminPage from './pages/AdminPage'

const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'search', element: <SearchPage /> },
      { path: 'catalog', element: <CatalogPage /> },
      { path: 'catalog/:categoryId', element: <CatalogPage /> },
      { path: 'documents/:documentId', element: <DocumentPage /> },
      { path: 'admin', element: <AdminPage /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])

export default function App() {
  return <RouterProvider router={router} />
}
