import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import LoginPage from './pages/LoginPage'
import SearchPage from './pages/SearchPage'
import BrowsePage from './pages/BrowsePage'
import DocumentPage from './pages/DocumentPage'
import AdminPage from './pages/admin/AdminPage'

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <SearchPage /> },
      { path: 'browse', element: <BrowsePage /> },
      { path: 'browse/:folderId', element: <BrowsePage /> },
      { path: 'documents/:fileId', element: <DocumentPage /> },
      { path: 'admin', element: <AdminPage /> },
      { path: 'admin/:tab', element: <AdminPage /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])

export default function App() {
  return <RouterProvider router={router} />
}
