import { Layout, Typography } from 'antd'
import { Route, Routes } from 'react-router-dom'
import SearchBar from './components/SearchBar'
import TagSidebar from './components/TagSidebar'
import ModeScreeningPage from './pages/ModeScreeningPage'
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
        <Route path="/screening" element={<ModeScreeningPage />} />
        <Route path="/screening/tasks/:taskId" element={<TaskDetailPage section="screening" />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/tasks/:taskId" element={<TaskDetailPage section="tasks" />} />
      </Routes>
    </Layout.Content>
    <Layout.Footer className="footer"><Typography.Text type="secondary">仅供个人研究，不构成投资建议</Typography.Text></Layout.Footer>
    </Layout>
  </Layout>
}
