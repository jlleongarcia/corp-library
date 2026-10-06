import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import LoginPage from './pages/LoginPage'
import WelcomePage from './pages/WelcomePage'
import AdminPage from './pages/admin/AdminPage'
import { useAuth } from './hooks/useAuth'

function Home() {
  const { user } = useAuth()
  // Phase 0 has no end-user features yet: admins land on the console.
  return user?.is_admin ? <Navigate to="/admin" replace /> : <WelcomePage />
}

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'admin', element: <AdminPage /> },
      { path: 'admin/:tab', element: <AdminPage /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])

export default function App() {
  return <RouterProvider router={router} />
}
