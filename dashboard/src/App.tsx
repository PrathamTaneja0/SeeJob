import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { AgentConsole } from './pages/AgentConsole'
import { ApplicationDetail } from './pages/ApplicationDetail'
import { JobDetail } from './pages/JobDetail'
import { JobQueue } from './pages/JobQueue'
import { PipelineKanban } from './pages/PipelineKanban'
import { ProfileEditor } from './pages/ProfileEditor'
import { Settings } from './pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<PipelineKanban />} />
          <Route path="jobs" element={<JobQueue />} />
          <Route path="jobs/:id" element={<JobDetail />} />
          <Route path="applications/:id" element={<ApplicationDetail />} />
          <Route path="profiles" element={<ProfileEditor />} />
          <Route path="settings" element={<Settings />} />
          <Route path="console" element={<AgentConsole />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
