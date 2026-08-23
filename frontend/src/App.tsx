import { Layout, Typography } from 'antd'
import { Route, Routes } from 'react-router-dom'
import SearchBar from './components/SearchBar'
import TagSidebar from './components/TagSidebar'
import SettingsPage from './pages/SettingsPage'
import StockDetailPage from './pages/StockDetailPage'
import TaskDetailPage from './pages/TaskDetailPage'
import TasksPage from './pages/TasksPage'
import WatchlistPage from './pages/WatchlistPage'

export default function App() {
  return <Layout className="app-shell">
    <TagSidebar />
    <Layout className="main-shell">
    <Layout.Header className="topbar">
      <SearchBar />
    </Layout.Header>
    <Layout.Content className="page-wrap">
      <Routes>
        <Route path="/" element={<WatchlistPage />} />
        <Route path="/stocks/:symbol" element={<StockDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
      </Routes>
    </Layout.Content>
    <Layout.Footer className="footer"><Typography.Text type="secondary">仅供个人研究，不构成投资建议</Typography.Text></Layout.Footer>
    </Layout>
  </Layout>
}
