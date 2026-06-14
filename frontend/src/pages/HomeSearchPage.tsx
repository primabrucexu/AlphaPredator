import {type ReactNode, useEffect, useRef, useState} from 'react';
import {Alert, AutoComplete, Button, Card, Input, Space, Spin, Tag, Typography,} from 'antd';
import {
    CheckCircleOutlined,
    CloseCircleOutlined,
    DatabaseOutlined,
    FireOutlined,
    SearchOutlined,
    SettingOutlined,
} from '@ant-design/icons';
import {Link, useNavigate} from 'react-router-dom';
import {getInitOverview, type InitOverviewResponse, searchStocks, type StockCandidate,} from '../lib/api';

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
  const [options, setOptions] = useState<{ value: string; label: ReactNode }[]>([]);
  const [lastCandidates, setLastCandidates] = useState<StockCandidate[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [overview, setOverview] = useState<InitOverviewResponse | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(true);

  useEffect(() => {
    getInitOverview()
      .then(setOverview)
      .catch(() => setOverview(null))
      .finally(() => setOverviewLoading(false));
  }, []);

  const triggerSearch = (value: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const q = value.trim();
    if (!q) {
      setOptions([]);
      setLastCandidates([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const candidates = await searchStocks(q.toUpperCase(), 10);
        setLastCandidates(candidates);
        setOptions(
          candidates.map((c) => ({
            value: c.stock_code,
            label: (
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ fontWeight: 500 }}>{c.stock_name}</span>
                <span style={{ color: '#8c8c8c', fontVariantNumeric: 'tabular-nums' }}>
                  {c.stock_code}
                </span>
              </div>
            ),
          })),
        );
      } catch {
        setOptions([]);
      } finally {
        setSearching(false);
      }
    }, 250);
  };

  const handleSelect = (stockCode: string) => {
    navigate(`/stocks/${stockCode}`);
  };

  const handleEnter = () => {
    const q = query.trim();
    if (!q) return;
    if (lastCandidates.length === 1) {
      navigate(`/stocks/${lastCandidates[0].stock_code}`);
    }
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
      <AutoComplete
        style={{ width: '100%', maxWidth: 520 }}
        options={options}
        value={query}
        onChange={(val) => {
          setQuery(val);
          triggerSearch(val);
        }}
        onSelect={handleSelect}
        notFoundContent={searching ? <Spin size="small" /> : null}
      >
        <Input
          size="large"
          placeholder="输入股票代码或拼音简称搜索"
          prefix={searching ? <Spin size="small" /> : <SearchOutlined />}
          suffix={
            <Button
              type="primary"
              size="small"
              icon={<SearchOutlined />}
              onClick={handleEnter}
            >
              搜索
            </Button>
          }
          onPressEnter={handleEnter}
          allowClear
        />
      </AutoComplete>

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
            <Space>
                <Link to="/sentiment">
                    <Button size="small" icon={<FireOutlined/>}>
                        热点复盘
                    </Button>
                </Link>
                <Link to="/initialize">
                    <Button size="small" icon={<SettingOutlined/>}>
                        去初始化
                    </Button>
                </Link>
            </Space>
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

              {/* Market data credential */}
            <Space wrap>
                <Tag color={overview.market_data_configured ? 'blue' : 'default'}>
                    {overview.market_data_configured ? '✓ 行情数据源已配置' : '✗ 行情数据源未配置'}
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
                上一次行情同步：{formatRange(
                  overview.market_data_last_sync_start_date,
                  overview.market_data_last_sync_end_date,
                )}
                {overview.market_data_last_sync_finished_at
                  ? `，完成于 ${formatIsoShort(overview.market_data_last_sync_finished_at)}`
                  : ''}
              </Typography.Text>
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
