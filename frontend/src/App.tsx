import { BarChartOutlined, SettingOutlined, StarOutlined } from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import { Link, Route, Routes, useLocation } from 'react-router-dom'
import SearchBar from './components/SearchBar'
import SettingsPage from './pages/SettingsPage'
import StockDetailPage from './pages/StockDetailPage'
import WatchlistPage from './pages/WatchlistPage'

export default function App() {
  const location = useLocation()
  const selected = location.pathname.startsWith('/settings') ? '/settings' : '/'
  return <Layout className="app-shell">
    <Layout.Header className="topbar">
      <Link to="/" className="brand"><BarChartOutlined /><span>AlphaPredator</span></Link>
      <SearchBar />
      <Menu mode="horizontal" selectedKeys={[selected]} items={[
        { key: '/', icon: <StarOutlined />, label: <Link to="/">自选股</Link> },
        { key: '/settings', icon: <SettingOutlined />, label: <Link to="/settings">数据设置</Link> },
      ]} />
    </Layout.Header>
    <Layout.Content className="page-wrap">
      <Routes>
        <Route path="/" element={<WatchlistPage />} />
        <Route path="/stocks/:symbol" element={<StockDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </Layout.Content>
    <Layout.Footer className="footer"><Typography.Text type="secondary">仅供个人研究，不构成投资建议</Typography.Text></Layout.Footer>
  </Layout>
}
