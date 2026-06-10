import {
    AreaChartOutlined,
    CalendarOutlined,
    DatabaseOutlined,
    FireOutlined,
    HomeOutlined,
    RadarChartOutlined,
    SettingOutlined,
} from '@ant-design/icons';
import {Breadcrumb, Layout, Menu, Typography} from 'antd';
import type {PropsWithChildren} from 'react';
import {useLocation, useNavigate} from 'react-router-dom';
import {StockSearchBar} from '../StockSearchBar';

const { Header, Content, Sider } = Layout;

const menuItems = [
  { key: '/', icon: <HomeOutlined />, label: '首页搜索' },
  { key: '/market', icon: <AreaChartOutlined />, label: '市场总览' },
    {key: '/sentiment', icon: <FireOutlined/>, label: '短线情绪'},
  { key: '/results', icon: <RadarChartOutlined />, label: 'AI 选股结果' },
  { key: '/trade-review', icon: <CalendarOutlined />, label: '交易复盘' },
  { key: '/initialize', icon: <SettingOutlined />, label: '数据初始化' },
];

export function AppShell({ children }: PropsWithChildren) {
  const location = useLocation();
  const navigate = useNavigate();

  const selectedKey =
    menuItems.find((item) => location.pathname === item.key || location.pathname.startsWith(`${item.key}/`))?.key ?? '/';

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="light" width={240} style={{ borderRight: '1px solid #f0f0f0' }}>
        <div style={{ padding: 24, display: 'flex', gap: 12, alignItems: 'center' }}>
          <DatabaseOutlined style={{ fontSize: 24, color: '#1677ff' }} />
          <div>
            <Typography.Title level={4} style={{ margin: 0 }}>
              AlphaPredator
            </Typography.Title>
            <Typography.Text type="secondary">A 股智能选股工作台</Typography.Text>
          </div>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            alignItems: 'center',
              justifyContent: 'space-between',
            paddingInline: 24,
          }}
        >
          <Breadcrumb
            items={[
              { title: 'AlphaPredator' },
              { title: menuItems.find((item) => item.key === selectedKey)?.label ?? '工作台' },
            ]}
          />
            <StockSearchBar inputSize="middle" style={{width: 280}}/>
        </Header>
        <Content style={{ padding: 24 }}>{children}</Content>
      </Layout>
    </Layout>
  );
}
