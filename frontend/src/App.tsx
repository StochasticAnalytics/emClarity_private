import { Routes, Route, Navigate } from 'react-router-dom'
import { MainLayout } from '@/components/layout/MainLayout.tsx'
import { ProjectLayout } from '@/components/layout/ProjectLayout.tsx'
import { ProjectPage } from '@/features/project/ProjectPage.tsx'
import { OverviewPage } from '@/features/overview/OverviewPage.tsx'
import { AssetsPage } from '@/features/assets/AssetsPage.tsx'
import { WorkflowPage } from '@/features/workflow/WorkflowPage.tsx'
import { ActionsPage } from '@/features/actions/ActionsPage.tsx'
import { ResultsPage } from '@/features/results/ResultsPage.tsx'
import { ParametersPage } from '@/features/parameters/ParametersPage.tsx'
import { JobsPage } from '@/features/jobs/JobsPage.tsx'
import { ExpertPage } from '@/features/expert/ExpertPage.tsx'

function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        {/* Landing: create or open a project */}
        <Route path="/" element={<ProjectPage />} />

        {/* Project-scoped routes – all nested under /project/:projectId */}
        <Route path="/project/:projectId" element={<ProjectLayout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="assets" element={<AssetsPage />} />
          <Route path="actions" element={<ActionsPage />} />
          <Route path="workflow" element={<WorkflowPage />} />
          <Route path="results" element={<ResultsPage />} />
          <Route path="settings" element={<ParametersPage />} />
          <Route path="jobs" element={<JobsPage />} />
          <Route path="expert" element={<ExpertPage />} />
        </Route>
      </Route>
    </Routes>
  )
}

export default App
