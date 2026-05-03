import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Input,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import {
  type InitOverviewResponse,
  type StockResolveResponse,
  getInitOverview,
  resolveStockInput,
} from '../lib/api';

function formatIsoShort(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
  } catch {
    return iso;
  }
}

function formatRange(start: string | null | undefined, end: string | null | undefined): string {
  if (!start || !end) return '—';
  return `${start} ~ ${end}`;
}

export function HomeSearchPage() {
  const navigate = useNavigate();

  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [resolveResult, setResolveResult] = useState<StockResolveResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [overview, setOverview] = useState<InitOverviewResponse | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(true);

  useEffect(() => {
    getInitOverview()
      .then(setOverview)
      .catch(() => setOverview(null))
      .finally(() => setOverviewLoading(false));
  }, []);

  const handleSearch = async () => {
    const q = query.trim().toUpperCase();
    if (!q) {
      setSearchError('请输入股票代码或拼音简称');
      return;
    }
    setSearchError(null);
    setResolveResult(null);
    setSearching(true);
    try {
      const result = await resolveStockInput(q);
      if (result.status === 'ok' && result.stock_code) {
        navigate(`/stocks/${result.stock_code}`);
        return;
      }
      setResolveResult(result);
    } catch {
      setSearchError('服务暂不可用，请稍后重试');
    } finally {
      setSearching(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') void handleSearch();
  };

  const initReady = overview?.init_completed;

  return (
    <div
      style={{
        minHeight: '70vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px 16px',
        gap: 32,
      }}
    >
      {/* Brand */}
      <Space direction="vertical" align="center" size={4}>
        <Typography.Title level={1} style={{ margin: 0, letterSpacing: 2 }}>
          AlphaPredator
        </Typography.Title>
        <Typography.Text type="secondary">A 股智能选股助手</Typography.Text>
      </Space>

      {/* Search */}
      <Space.Compact style={{ width: '100%', maxWidth: 520 }}>
        <Input
          size="large"
          placeholder="输入股票代码或拼音简称，按 Enter 搜索"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSearchError(null);
            setResolveResult(null);
          }}
          onKeyDown={handleKeyDown}
          allowClear
          prefix={<SearchOutlined />}
        />
        <Button
          size="large"
          type="primary"
          loading={searching}
          onClick={() => void handleSearch()}
          icon={<SearchOutlined />}
        >
          搜索
        </Button>
      </Space.Compact>

      {/* Search result messages */}
      {searchError && (
        <Alert
          type="warning"
          showIcon
          message={searchError}
          style={{ width: '100%', maxWidth: 520 }}
        />
      )}
      {resolveResult && resolveResult.status === 'not_found' && (
        <Alert
          type="info"
          showIcon
          message="未找到匹配股票"
          description={resolveResult.message}
          style={{ width: '100%', maxWidth: 520 }}
        />
      )}
      {resolveResult && resolveResult.status === 'ambiguous' && (
        <Alert
          type="warning"
          showIcon
          message="匹配到多只股票，请输入更完整代码/简称"
          description={
            resolveResult.candidates && resolveResult.candidates.length > 0 ? (
              <Space wrap size={4} style={{ marginTop: 4 }}>
                {resolveResult.candidates.map((c) => (
                  <Tag
                    key={c.stock_code}
                    color="blue"
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/stocks/${c.stock_code}`)}
                  >
                    {c.stock_code} {c.stock_name}
                  </Tag>
                ))}
              </Space>
            ) : undefined
          }
          style={{ width: '100%', maxWidth: 520 }}
        />
      )}

      {/* Init status panel */}
      <Card
        style={{ width: '100%', maxWidth: 520 }}
        size="small"
        title={
          <Space>
            <DatabaseOutlined />
            <span>数据初始化状态</span>
          </Space>
        }
        extra={
          <Link to="/initialize">
            <Button size="small" icon={<SettingOutlined />}>
              去初始化
            </Button>
          </Link>
        }
      >
        {overviewLoading ? (
          <Space>
            <Spin size="small" />
            <Typography.Text type="secondary">检查初始化状态…</Typography.Text>
          </Space>
        ) : overview === null ? (
          <Typography.Text type="secondary">无法获取初始化状态，请检查后端服务</Typography.Text>
        ) : (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            {/* Overall init status */}
            <Space>
              <Typography.Text>初始化状态：</Typography.Text>
              {initReady ? (
                <Tag color="success" icon={<CheckCircleOutlined />}>
                  已完成
                </Tag>
              ) : (
                <Tag color="warning" icon={<CloseCircleOutlined />}>
                  未完成
                </Tag>
              )}
            </Space>

            {/* Token */}
            <Space wrap>
              <Tag color={overview.token_configured ? 'blue' : 'default'}>
                {overview.token_configured ? '✓ Token 已配置' : '✗ Token 未配置'}
              </Tag>
            </Space>

            {/* Board counts */}
            {Object.keys(overview.board_counts).length > 0 && (
              <Space wrap size={4}>
                {Object.entries(overview.board_counts).map(([board, count]) => (
                  <Tag key={board} color="processing">
                    {board}: {count} 支
                  </Tag>
                ))}
              </Space>
            )}

            {/* Timestamps */}
            <Space direction="vertical" size={2}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                已有每日行情区间：{formatRange(overview.market_data_start_date, overview.market_data_end_date)}
                {overview.market_data_trading_day_count > 0 ? `（${overview.market_data_trading_day_count} 个交易日）` : ''}
              </Typography.Text>
            </Space>

            {/* Prompt to init when not ready */}
            {!initReady && (
              <Alert
                type="info"
                showIcon
                message="数据尚未初始化，搜索功能可能不可用"
                description={
                  <Link to="/initialize">点击前往初始化页面完成设置</Link>
                }
                style={{ marginTop: 4 }}
              />
            )}
          </Space>
        )}
      </Card>
    </div>
  );
}
