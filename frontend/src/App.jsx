import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { LoadingState } from './components/ui/index.js'
import DashboardLayout from './layouts/DashboardLayout.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import AssistantPage from './pages/assistant/AssistantPage.jsx'
import StripeExplorerPage from './pages/explorer/StripeExplorerPage.jsx'
import IdentifyPage from './pages/identify/IdentifyPage.jsx'
import PlaceholderPage from './pages/PlaceholderPage.jsx'
import SightingDetailPage from './pages/sightings/SightingDetailPage.jsx'
import SightingsPage from './pages/sightings/SightingsPage.jsx'
import ZebraGalleryPage from './pages/zebras/ZebraGalleryPage.jsx'
import ZebraProfilePage from './pages/zebras/ZebraProfilePage.jsx'

// Lazy-load Three.js 3D Hide Viewer so initial bundle stays lean.
const HideViewerPage = lazy(() => import('./pages/hide/HideViewerPage.jsx'))
// Component reference page: development builds only (removed from production bundles).
const DesignSystemPage = import.meta.env.DEV ? lazy(() => import('./pages/DesignSystemPage.jsx')) : null

export default function App() {
  return (
    <Routes>
      <Route element={<DashboardLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="identify" element={<IdentifyPage />} />
        <Route path="identify/runs/:runId" element={<IdentifyPage />} />
        <Route path="zebras" element={<ZebraGalleryPage />} />
        <Route path="zebras/:zebraId" element={<ZebraProfilePage />} />
        <Route path="sightings" element={<SightingsPage />} />
        <Route path="sightings/:sightingId" element={<SightingDetailPage />} />
        <Route path="stripes" element={<StripeExplorerPage />} />
        <Route
          path="hide-viewer"
          element={
            <Suspense fallback={<LoadingState />}>
              <HideViewerPage />
            </Suspense>
          }
        />
        <Route path="assistant" element={<AssistantPage />} />
        {/* Kept from Phase 1; not in the sidebar. */}
        <Route path="reports" element={<PlaceholderPage />} />
        {DesignSystemPage && (
          <Route
            path="ui"
            element={
              <Suspense fallback={<LoadingState />}>
                <DesignSystemPage />
              </Suspense>
            }
          />
        )}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
