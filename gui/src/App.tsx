import { Routes, Route } from 'react-router-dom'
import { MainLayout } from '@/components/layout/MainLayout.tsx'
import { ProjectPage } from '@/features/project/ProjectPage.tsx'
import { ParametersPage } from '@/features/parameters/ParametersPage.tsx'
import { TiltSeriesPage } from '@/features/tilt-series/TiltSeriesPage.tsx'
import { WorkflowPage } from '@/features/workflow/WorkflowPage.tsx'
import { JobsPage } from '@/features/jobs/JobsPage.tsx'
import { ResultsPage } from '@/features/results/ResultsPage.tsx'
import { UtilitiesPage } from '@/features/utilities/UtilitiesPage.tsx'

function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/" element={<ProjectPage />} />
        <Route path="/parameters" element={<ParametersPage />} />
        <Route path="/tilt-series" element={<TiltSeriesPage />} />
        <Route path="/workflow" element={<WorkflowPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/results" element={<ResultsPage />} />
        <Route path="/utilities" element={<UtilitiesPage />} />
      </Route>
    </Routes>
  )
}

export default App
