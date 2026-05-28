/**
 * 交易复盘主页
 * - Tab1：个股复盘（列表 + 详情 + 新建/编辑）
 * - Tab2：月度复盘（统计 + AI 总结入口）
 */
import {
  CalendarOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import {
  Badge,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  message,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Timeline,
  Tabs,
  Typography,
} from 'antd';
import dayjs from 'dayjs';
import {useCallback, useEffect, useState} from 'react';
import {
  deleteTradeReview,
  getMonthlyStats,
  getTradeReview,
  listTradeReviews,
  type MonthlyStatsResponse,
  type TradeReviewDetail,
  type TradeReviewSessionItem,
} from '../lib/api';
import {TradeReviewEditorDrawer} from './TradeReviewEditorDrawer';

const {Text, Title} = Typography;

const OP_TYPE_LABELS: Record<string, string> = {
  buy: '建仓', add: '加仓', sell: '清仓',
  reduce: '减仓', t_buy: 'T+买', t_sell: 'T+卖',
};
const OP_TYPE_COLORS: Record<string, string> = {
  buy: 'green', add: 'cyan', sell: 'red',
  reduce: 'orange', t_buy: 'geekblue', t_sell: 'volcano',
};

function PnlTag({value}: {value?: number}) {
  if (value == null) return <Text type="secondary">—</Text>;
  const color = value >= 0 ? '#cf1322' : '#389e0d';
  const prefix = value >= 0 ? '+' : '';
  return <span style={{color, fontWeight: 600}}>{prefix}{value.toFixed(2)}</span>;
}

function RateTag({value}: {value?: number}) {
  if (value == null) return <Text type="secondary">—</Text>;
  const pct = (value * 100).toFixed(2);
  const color = value >= 0 ? '#cf1322' : '#389e0d';
  const prefix = value >= 0 ? '+' : '';
  return <span style={{color}}>{prefix}{pct}%</span>;
}

// ---------------------------------------------------------------------------
// 个股复盘 Tab
// ---------------------------------------------------------------------------
function StockReviewTab() {
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<TradeReviewSessionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  // 筛选
  const [filterMonth, setFilterMonth] = useState<string | undefined>(
    dayjs().format('YYYY-MM'),
  );
  const [filterStatus, setFilterStatus] = useState<string | undefined>();

  // 详情
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<TradeReviewDetail | null>(null);

  // 编辑器
  const [editorOpen, setEditorOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<TradeReviewDetail | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await listTradeReviews({
        month: filterMonth,
        status: filterStatus,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      });
      setItems(r.items);
      setTotal(r.total);
    } finally {
      setLoading(false);
    }
  }, [filterMonth, filterStatus, page]);

  useEffect(() => {load();}, [load]);

  const openDetail = async (id: string) => {
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      const d = await getTradeReview(id);
      setDetail(d);
    } finally {
      setDetailLoading(false);
    }
  };

  const openEditor = async (item?: TradeReviewSessionItem) => {
    if (item) {
      const d = await getTradeReview(item.id);
      setEditTarget(d);
    } else {
      setEditTarget(null);
    }
    setEditorOpen(true);
  };

  const handleDelete = async (id: string) => {
    await deleteTradeReview(id);
    message.success('已删除');
    load();
  };

  const columns = [
    {
      title: '股票',
      dataIndex: 'stock_name',
      render: (_: string, r: TradeReviewSessionItem) => (
        <Space direction="vertical" size={0}>
          <Text strong>{r.stock_name}</Text>
          <Text type="secondary" style={{fontSize: 12}}>{r.stock_code}</Text>
        </Space>
      ),
    },
    {
      title: '交易周期',
      render: (_: unknown, r: TradeReviewSessionItem) => (
        <Text style={{fontSize: 12}}>
          {r.start_date}
          {r.end_date ? ` → ${r.end_date}` : (
            <Tag color="processing" style={{marginLeft: 4}}>持仓中</Tag>
          )}
        </Text>
      ),
    },
    {
      title: '盈亏',
      render: (_: unknown, r: TradeReviewSessionItem) => (
        <Space direction="vertical" size={0}>
          <PnlTag value={r.realized_pnl} />
          <RateTag value={r.return_rate} />
        </Space>
      ),
    },
    {
      title: 'AI',
      dataIndex: 'ai_status',
      width: 80,
      render: (v: string) => {
        const map: Record<string, string> = {pending: 'default', done: 'success', failed: 'error'};
        const labelMap: Record<string, string> = {pending: '待分析', done: '已分析', failed: '失败'};
        return <Badge status={map[v] as 'default' | 'success' | 'error'} text={labelMap[v] ?? v} />;
      },
    },
    {
      title: '操作',
      width: 120,
      render: (_: unknown, r: TradeReviewSessionItem) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => openDetail(r.id)} />
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditor(r)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{marginBottom: 16, justifyContent: 'space-between', width: '100%'}}>
        <Space>
          <DatePicker.MonthPicker
            value={filterMonth ? dayjs(filterMonth) : null}
            onChange={d => {setFilterMonth(d ? d.format('YYYY-MM') : undefined); setPage(1);}}
            placeholder="筛选月份"
            allowClear
          />
          <Select
            allowClear
            placeholder="状态"
            style={{width: 110}}
            value={filterStatus}
            onChange={v => {setFilterStatus(v); setPage(1);}}
            options={[
              {value: 'open', label: '持仓中'},
              {value: 'closed', label: '已清仓'},
            ]}
          />
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor()}>
          新建复盘
        </Button>
      </Space>

      <Table
        rowKey="id"
        dataSource={items}
        columns={columns}
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          onChange: setPage,
          showTotal: t => `共 ${t} 条`,
        }}
      />

      {/* 详情 Drawer */}
      <Drawer
        title={detail ? `${detail.stock_name}（${detail.stock_code ?? '—'}）复盘详情` : '复盘详情'}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={680}
        loading={detailLoading}
      >
        {detail && <ReviewDetailContent detail={detail} />}
      </Drawer>

      {/* 编辑 Drawer */}
      <TradeReviewEditorDrawer
        open={editorOpen}
        editTarget={editTarget}
        onClose={() => setEditorOpen(false)}
        onSaved={load}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// 单标的详情内容
// ---------------------------------------------------------------------------
function ReviewDetailContent({detail}: {detail: TradeReviewDetail}) {
  return (
    <Space direction="vertical" size={16} style={{width: '100%'}}>
      {/* 区块1：基础统计 */}
      <Card size="small" title="交易概况">
        <Row gutter={16}>
          <Col span={8}><Statistic title="总买入" value={detail.total_buy_amount?.toFixed(2) ?? '—'} /></Col>
          <Col span={8}><Statistic title="总卖出" value={detail.total_sell_amount?.toFixed(2) ?? '—'} /></Col>
          <Col span={8}>
            <Statistic
              title="已实现���亏"
              value={detail.realized_pnl?.toFixed(2) ?? '—'}
              valueStyle={{color: (detail.realized_pnl ?? 0) >= 0 ? '#cf1322' : '#389e0d'}}
            />
          </Col>
        </Row>
      </Card>

      {/* 区块2：成交时间线 */}
      <Card size="small" title="成交明细">
        {detail.operations.length === 0 ? (
          <Empty description="暂无成交记录" />
        ) : (
          <Timeline
            items={detail.operations.map(op => ({
              color: OP_TYPE_COLORS[op.operation_type] ?? 'gray',
              children: (
                <Space direction="vertical" size={2}>
                  <Space>
                    <Tag color={OP_TYPE_COLORS[op.operation_type]}>
                      {OP_TYPE_LABELS[op.operation_type] ?? op.operation_type}
                    </Tag>
                    <Text type="secondary" style={{fontSize: 12}}>{op.trade_time}</Text>
                  </Space>
                  <Text>
                    {op.quantity} 股 × ¥{op.price} = ¥{op.amount.toFixed(2)}
                  </Text>
                  {op.note && <Text type="secondary">{op.note}</Text>}
                </Space>
              ),
            }))}
          />
        )}
      </Card>

      {/* 区块3：主观复盘 */}
      <Card size="small" title="主观复盘">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="建仓理由">
            {detail.entry_reason || <Text type="secondary">未填写</Text>}
          </Descriptions.Item>
          <Descriptions.Item label="建仓预期">
            {detail.entry_expectation || <Text type="secondary">未填写</Text>}
          </Descriptions.Item>
          <Descriptions.Item label="做对了什么">
            {detail.reflection_did_well || <Text type="secondary">未填写</Text>}
          </Descriptions.Item>
          <Descriptions.Item label="做错了什么">
            {detail.reflection_did_poorly || <Text type="secondary">未填写</Text>}
          </Descriptions.Item>
          <Descriptions.Item label="如果重来">
            {detail.reflection_redo_plan || <Text type="secondary">未填写</Text>}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 区块4：AI 总结（内嵌，Phase 2 完善） */}
      {detail.ai_result && (
        <Card size="small" title="AI 单标的复盘">
          <Descriptions column={1} size="small">
            {(detail.ai_result.major_issue as string) && (
              <Descriptions.Item label="主要问题">{detail.ai_result.major_issue as string}</Descriptions.Item>
            )}
            {(detail.ai_result.top_improvement as string) && (
              <Descriptions.Item label="最值得改进">{detail.ai_result.top_improvement as string}</Descriptions.Item>
            )}
          </Descriptions>
          {Array.isArray(detail.ai_result.trade_tags) && (
            <Space style={{marginTop: 8}}>
              {(detail.ai_result.trade_tags as string[]).map(t => (
                <Tag key={t}>{t}</Tag>
              ))}
            </Space>
          )}
        </Card>
      )}
    </Space>
  );
}

// ---------------------------------------------------------------------------
// 月度复盘 Tab
// ---------------------------------------------------------------------------
function MonthlyReviewTab() {
  const [monthKey, setMonthKey] = useState(dayjs().format('YYYY-MM'));
  const [stats, setStats] = useState<MonthlyStatsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await getMonthlyStats(monthKey);
      setStats(r);
    } finally {
      setLoading(false);
    }
  }, [monthKey]);

  useEffect(() => {load();}, [load]);

  return (
    <Space direction="vertical" size={16} style={{width: '100%'}}>
      <Space>
        <CalendarOutlined />
        <DatePicker.MonthPicker
          value={dayjs(monthKey)}
          onChange={d => d && setMonthKey(d.format('YYYY-MM'))}
          format="YYYY年MM月"
          allowClear={false}
        />
        <Button onClick={load} loading={loading}>刷新</Button>
      </Space>

      {stats && (
        <>
          {/* 汇总统计 */}
          <Row gutter={16}>
            <Col span={4}><Card size="small"><Statistic title="交易次数" value={stats.trade_count} /></Card></Col>
            <Col span={4}>
              <Card size="small">
                <Statistic
                  title="胜率"
                  value={stats.trade_count > 0 ? ((stats.win_count / stats.trade_count) * 100).toFixed(1) : '—'}
                  suffix={stats.trade_count > 0 ? '%' : ''}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="月度总盈亏"
                  value={stats.realized_pnl.toFixed(2)}
                  valueStyle={{color: stats.realized_pnl >= 0 ? '#cf1322' : '#389e0d'}}
                  prefix={stats.realized_pnl >= 0 ? '+' : ''}
                />
              </Card>
            </Col>
            <Col span={5}>
              <Card size="small">
                <Statistic title="最大盈利" value={stats.max_gain?.toFixed(2) ?? '—'}
                  valueStyle={{color: '#cf1322'}} />
              </Card>
            </Col>
            <Col span={5}>
              <Card size="small">
                <Statistic title="最大亏损" value={stats.max_loss?.toFixed(2) ?? '—'}
                  valueStyle={{color: '#389e0d'}} />
              </Card>
            </Col>
          </Row>

          {/* 本月复盘列表 */}
          <Card size="small" title={`本月复盘记录（${stats.trade_count} 笔）`}>
            {stats.reviews.length === 0 ? (
              <Empty description="本月暂无复盘记录" />
            ) : (
              <Table
                size="small"
                rowKey="id"
                dataSource={stats.reviews as unknown as TradeReviewSessionItem[]}
                pagination={false}
                columns={[
                  {title: '股票', render: (_: unknown, r: TradeReviewSessionItem) => `${r.stock_name}（${r.stock_code}）`},
                  {title: '建仓日期', dataIndex: 'start_date'},
                  {title: '结束日期', dataIndex: 'end_date', render: (v: string) => v || '持仓中'},
                  {title: '盈亏', render: (_: unknown, r: TradeReviewSessionItem) => <PnlTag value={r.realized_pnl} />},
                  {title: '收益率', render: (_: unknown, r: TradeReviewSessionItem) => <RateTag value={r.return_rate} />},
                ]}
              />
            )}
          </Card>

          {/* AI 月度总结（Phase 2 占位） */}
          <Card size="small" title="AI 月度总结" extra={<Button size="small" disabled>生成总结（Phase 2）</Button>}>
            <Empty description="月度 AI 总结功能将在 Phase 2 上线" />
          </Card>
        </>
      )}
    </Space>
  );
}

// ---------------------------------------------------------------------------
// 主页面入口
// ---------------------------------------------------------------------------
export function TradeReviewPage() {
  return (
    <div>
      <Title level={4} style={{marginBottom: 16}}>
        <CalendarOutlined style={{marginRight: 8}} />
        交易复盘
      </Title>
      <Tabs
        defaultActiveKey="stock"
        items={[
          {key: 'stock', label: '个股复盘', children: <StockReviewTab />},
          {key: 'monthly', label: '月度复盘', children: <MonthlyReviewTab />},
        ]}
      />
    </div>
  );
}

