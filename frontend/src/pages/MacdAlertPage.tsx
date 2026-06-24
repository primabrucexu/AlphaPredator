import {AlertOutlined, DownloadOutlined, HistoryOutlined, ReloadOutlined, SearchOutlined} from '@ant-design/icons';
import {Alert, Badge, Button, Card, Col, Empty, Form, Input, InputNumber, List, Progress, Row, Space, Statistic, Table, Tabs, Tag, Typography, message} from 'antd';
import type {ColumnsType} from 'antd/es/table';
import {useEffect, useMemo, useState} from 'react';
import {Link} from 'react-router-dom';
import {
  getInitTask,
  getTaskItems,
  listInitTasks,
  listMacdAlertBacktestSamples,
  listMacdAlertResults,
  scanMacdAlerts,
  terminateInitTask,
  trackMacdAlerts,
  validateStockMacdAlert,
  type MacdAlertBacktestSampleRow,
  type MacdAlertResultRow,
  type MacdStockValidateResponse,
  type MacdAlertTrackResponse,
  type TaskItemsResponse,
  type TaskResponse,
} from '../lib/api';

interface ScanFormValues {
  trade_date: string;
  green_shrink_days: number;
}

interface TrackFormValues {
  trade_date: string;
  source_trade_date: string;
}

interface StockValidateFormValues {
  stock_code: string;
  end_date: string;
  lookback_days: number;
  green_shrink_days: number;
}

const zoneText: Record<string, string> = {
  underwater: '水下',
  above_zero: '水上',
  mixed: '零轴附近',
};

const heatColor: Record<string, string> = {
  strong: 'red',
  medium: 'orange',
  weak: 'blue',
  none: 'default',
};

const trackColor: Record<string, string> = {
  pending: 'default',
  cross_confirmed: 'green',
  trend_kept: 'blue',
  trend_weakened: 'orange',
  data_missing: 'default',
};

const t1StatusText: Record<string, string> = {
  t1_cross_confirmed: 'T+1 已形成金叉',
  t1_trend_kept: 'T+1 趋势维持',
  t1_trend_weakened: 'T+1 趋势走弱',
  t1_data_missing: 'T+1 数据缺失',
};

const sellReasonText: Record<string, string> = {
  red_shrink: '不符合形态',
  timeout: '持有超时',
};

const sampleStatusText: Record<string, string> = {
  pending_cross: '等待金叉',
  cross_failed: '金叉失败',
  cross_success: '已金叉未卖出',
  sold_by_red_shrink: '红柱缩短卖出',
  sold_by_timeout: '超时卖出',
  insufficient_data: '数据不足',
};

const statusColor: Record<string, string> = {
  PENDING: 'blue',
  RUNNING: 'processing',
  SUCCESS: 'green',
  FAILED: 'red',
  TERMINATED: 'default',
};

const statusLabel: Record<string, string> = {
  PENDING: '等待中',
  RUNNING: '运行中',
  SUCCESS: '成功',
  FAILED: '失败',
  TERMINATED: '已终止',
};

function fmtPrice(value: number | null | undefined): string {
  return value == null ? '-' : value.toFixed(2);
}

function fmtPct(value: number | null | undefined): string {
  return value == null ? '-' : `${(value * 100).toFixed(2)}%`;
}

function taskDate(task: TaskResponse): string {
  const d = task.start_date;
  if (d.length === 8) return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
  return d;
}

function formatSampleSentence(row: MacdAlertBacktestSampleRow): string {
  const stock = `${row.stock_code} ${row.stock_name}`.trim();
  const alert = `${stock}${row.alert_date}符合 MACD 预警形态。`;
  if (!row.buy_date || row.buy_price == null) {
    return `${alert} 次日数据不足，未形成可回测买入。`;
  }

  const buy = `${row.buy_date}（T+1日）开盘价${fmtPrice(row.buy_price)}元买入`;
  if (!row.sell_date || row.sell_price == null) {
    return `${alert} ${buy}，尚未触发卖出，期间收益率${fmtPct(row.return_pct)}。`;
  }

  const reason = sellReasonText[row.sell_reason ?? ''] ?? '触发卖出';
  return `${alert} ${buy}，${row.sell_date}${reason}${fmtPrice(row.sell_price)}元卖出，期间收益率${fmtPct(row.return_pct)}。`;
}

function renderSampleDetail(row: MacdAlertBacktestSampleRow) {
  const detailItems = [
    ['预警日收盘价', `${fmtPrice(row.alert_close_price)}元`],
    ['预警类型', zoneText[row.alert_cross_zone] ?? row.alert_cross_zone],
    ['T+1 状态', row.t1_track_status ? (t1StatusText[row.t1_track_status] ?? row.t1_track_status) : '-'],
    ['T+1 收盘价', row.t1_close_price == null ? '-' : `${fmtPrice(row.t1_close_price)}元`],
    ['金叉价', `${fmtPrice(row.next_cross_trigger_price)}元（距离${fmtPct(row.cross_trigger_distance_pct)}）`],
    ['趋势维持价', `${fmtPrice(row.next_trend_keep_price)}元（距离${fmtPct(row.trend_keep_distance_pct)}）`],
    ['实际金叉日', row.cross_date ?? '-'],
    ['实际金叉类型', row.cross_type ? (zoneText[row.cross_type] ?? row.cross_type) : '-'],
    ['卖出原因', row.sell_reason ? (sellReasonText[row.sell_reason] ?? row.sell_reason) : '-'],
    ['持有天数', row.holding_days == null ? '-' : `${row.holding_days}个交易日`],
    ['样本状态', sampleStatusText[row.status] ?? row.status],
  ];

  return (
    <Space direction="vertical" size={8} style={{display: 'flex'}}>
      <Typography.Paragraph style={{margin: 0}}>{formatSampleSentence(row)}</Typography.Paragraph>
      <Row gutter={[16, 8]}>
        {detailItems.map(([label, value]) => (
          <Col xs={24} sm={12} lg={8} key={label}>
            <Typography.Text type="secondary">{label}：</Typography.Text>
            <Typography.Text>{value}</Typography.Text>
          </Col>
        ))}
      </Row>
    </Space>
  );
}

export function MacdAlertPage() {
  const [scanForm] = Form.useForm<ScanFormValues>();
  const [trackForm] = Form.useForm<TrackFormValues>();
  const [stockValidateForm] = Form.useForm<StockValidateFormValues>();
  const [loading, setLoading] = useState(false);
  const [tracking, setTracking] = useState(false);
  const [stockValidating, setStockValidating] = useState(false);
  const [stockValidateResult, setStockValidateResult] = useState<MacdStockValidateResponse | null>(null);
  const [scanTask, setScanTask] = useState<TaskResponse | null>(null);
  const [scanTaskItems, setScanTaskItems] = useState<TaskItemsResponse | null>(null);
  const [scanTradeDate, setScanTradeDate] = useState<string>('');
  const [trackSummary, setTrackSummary] = useState<MacdAlertTrackResponse | null>(null);
  const [rows, setRows] = useState<MacdAlertResultRow[]>([]);
  const [samples, setSamples] = useState<MacdAlertBacktestSampleRow[]>([]);
  const [selectedAlert, setSelectedAlert] = useState<MacdAlertResultRow | null>(null);
  const [taskHistory, setTaskHistory] = useState<TaskResponse[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [activeTradeDate, setActiveTradeDate] = useState<string>('');
  const [activeTab, setActiveTab] = useState<string>('alerts');
  const [greenShrinkDays, setGreenShrinkDays] = useState<number>(0);
  const [exporting, setExporting] = useState(false);

  async function refreshTaskHistory() {
    setHistoryLoading(true);
    try {
      const all = await listInitTasks(100);
      const macdTasks = all.filter(t => t.task_type === 'MACD_ALERT_SCAN');
      setTaskHistory(macdTasks);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '任务历史加载失败');
    } finally {
      setHistoryLoading(false);
    }
  }

  async function refreshResults(tradeDate: string) {
    const resultRows = await listMacdAlertResults({trade_date: tradeDate, limit: 2000});
    setRows(resultRows);
    if (resultRows.length > 0) {
      setGreenShrinkDays(resultRows[0].green_shrink_days);
    }
  }

  useEffect(() => {
    async function init() {
      await refreshTaskHistory();
    }
    init();
  }, []);

  useEffect(() => {
    if (taskHistory.length > 0 && !activeTaskId) {
      const latest = taskHistory.find(t => t.status === 'SUCCESS');
      if (latest) {
        handleSelectTask(latest);
      }
    }
  }, [taskHistory]);

  useEffect(() => {
    if (!scanTask || !['PENDING', 'RUNNING'].includes(scanTask.status)) return undefined;

    let cancelled = false;
    async function refreshTask() {
      if (!scanTask) return;
      try {
        const [latest, items] = await Promise.all([
          getInitTask(scanTask.task_id),
          getTaskItems(scanTask.task_id),
        ]);
        if (cancelled) return;
        setScanTask(latest);
        setScanTaskItems(items);
        if (latest.status === 'SUCCESS') {
          if (scanTradeDate) {
            await refreshResults(scanTradeDate);
            setActiveTradeDate(scanTradeDate);
            setActiveTaskId(scanTask.task_id);
          }
          await refreshTaskHistory();
          if (!cancelled) message.success('MACD 扫描任务完成');
        } else if (latest.status === 'FAILED') {
          await refreshTaskHistory();
          message.error(latest.error_message || 'MACD 扫描任务失败');
        }
      } catch (error) {
        if (!cancelled) {
          message.error(error instanceof Error ? error.message : '扫描任务状态查询失败');
        }
      }
    }

    refreshTask();
    const timer = window.setInterval(refreshTask, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [scanTask?.task_id, scanTask?.status, scanTradeDate]);

  async function handleScan(values: ScanFormValues) {
    setLoading(true);
    setSamples([]);
    setSelectedAlert(null);
    try {
      const task = await scanMacdAlerts({
        trade_date: values.trade_date,
        universe_scope: 'market',
        markets: ['主板'],
        exclude_st: true,
        green_shrink_days: values.green_shrink_days,
      });
      setScanTask(task);
      setScanTaskItems(null);
      setScanTradeDate(values.trade_date);
      setRows([]);
      message.success('MACD 扫描任务已提交');
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'MACD 预警扫描失败');
    } finally {
      setLoading(false);
    }
  }

  async function handleTerminateScanTask() {
    if (!scanTask) return;
    try {
      const task = await terminateInitTask(scanTask.task_id);
      setScanTask(task);
      message.success('已终止扫描任务');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '终止扫描任务失败');
    }
  }

  async function handleSelectTask(task: TaskResponse) {
    const tradeDate = taskDate(task);
    setActiveTaskId(task.task_id);
    setActiveTradeDate(tradeDate);
    setRows([]);
    setSamples([]);
    setSelectedAlert(null);
    await refreshResults(tradeDate);
  }

  async function handleTrack(values: TrackFormValues) {
    setTracking(true);
    try {
      const result = await trackMacdAlerts(values.trade_date, values.source_trade_date);
      setTrackSummary(result);
      await refreshResults(values.source_trade_date);
      setActiveTradeDate(values.source_trade_date);
      message.success(`跟踪完成，处理 ${result.tracked_count} 只`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'MACD 跟踪失败');
    } finally {
      setTracking(false);
    }
  }

  async function handleExport() {
    if (!activeTradeDate) return;
    setExporting(true);
    try {
      const resp = await fetch(`/api/macd-alerts/results/export?trade_date=${encodeURIComponent(activeTradeDate)}`);
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(detail || '导出失败');
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `macd-alert-${activeTradeDate}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      message.success('CSV 导出完成');
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'CSV 导出失败');
    } finally {
      setExporting(false);
    }
  }

  async function handleLoadSamples(row: MacdAlertResultRow) {
    setSelectedAlert(row);
    setSamples([]);
    try {
      const sampleRows = await listMacdAlertBacktestSamples(row.id, 100);
      setSamples(sampleRows);
      setActiveTab('samples');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '历史样本加载失败');
    }
  }

  async function handleStockValidate(values: StockValidateFormValues) {
    setStockValidating(true);
    try {
      const result = await validateStockMacdAlert({
        stock_code: values.stock_code.trim(),
        end_date: values.end_date,
        lookback_days: values.lookback_days,
        green_shrink_days: values.green_shrink_days,
        cross_zone: 'all',
      });
      setStockValidateResult(result);
      setActiveTab('stock');
      message.success('个股 MACD 验证完成');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '个股 MACD 验证失败');
    } finally {
      setStockValidating(false);
    }
  }

  const alertColumns: ColumnsType<MacdAlertResultRow> = useMemo(
    () => [
      {
        title: '股票',
        fixed: 'left',
        width: 150,
        render: (_, row) => <Link to={`/stocks/${row.stock_code}`}>{row.stock_name || row.stock_code}</Link>,
        sorter: (a, b) => (a.stock_name || a.stock_code).localeCompare(b.stock_name || b.stock_code, 'zh'),
      },
      {title: '代码', dataIndex: 'stock_code', width: 90, sorter: (a, b) => a.stock_code.localeCompare(b.stock_code)},
      {
        title: '类型',
        dataIndex: 'cross_zone',
        width: 90,
        render: (value: string) => <Tag color={value === 'underwater' ? 'blue' : 'green'}>{zoneText[value] ?? value}</Tag>,
        sorter: (a, b) => a.cross_zone.localeCompare(b.cross_zone),
      },
      {title: '收盘价', dataIndex: 'close_price', width: 90, render: fmtPrice, sorter: (a, b) => a.close_price - b.close_price},
      {
        title: '金叉价',
        width: 120,
        render: (_, row) => (
          <Space size={4}>
            <span>{fmtPrice(row.next_cross_trigger_price)}</span>
            {!row.cross_trigger_reachable ? <Tag color="volcano">不可达</Tag> : null}
          </Space>
        ),
        sorter: (a, b) => a.cross_trigger_distance_pct - b.cross_trigger_distance_pct,
      },
      {title: '金叉距离', dataIndex: 'cross_trigger_distance_pct', width: 105, render: fmtPct, sorter: (a, b) => a.cross_trigger_distance_pct - b.cross_trigger_distance_pct},
      {title: '维持价', dataIndex: 'next_trend_keep_price', width: 95, render: fmtPrice, sorter: (a, b) => a.next_trend_keep_price - b.next_trend_keep_price},
      {title: '维持距离', dataIndex: 'trend_keep_distance_pct', width: 105, render: fmtPct, sorter: (a, b) => a.trend_keep_distance_pct - b.trend_keep_distance_pct},
      {
        title: '题材',
        width: 150,
        render: (_, row) => row.last_limit_up_theme ? (
          <Space size={4}>
            <span>{row.last_limit_up_theme}</span>
            <Tag color={heatColor[row.theme_heat_level] ?? 'default'}>{row.theme_heat_level}</Tag>
          </Space>
        ) : '近120日无题材',
        sorter: (a, b) => (a.last_limit_up_theme || '').localeCompare(b.last_limit_up_theme || '', 'zh'),
      },
      {
        title: '跟踪',
        dataIndex: 'track_status',
        width: 120,
        render: (value: string) => <Tag color={trackColor[value] ?? 'default'}>{value}</Tag>,
        sorter: (a, b) => a.track_status.localeCompare(b.track_status),
      },
      {title: '样本', dataIndex: 'backtest_sample_count', width: 80, sorter: (a, b) => a.backtest_sample_count - b.backtest_sample_count},
      {title: '金叉率', dataIndex: 'backtest_cross_success_rate', width: 95, render: fmtPct, sorter: (a, b) => (a.backtest_cross_success_rate ?? 0) - (b.backtest_cross_success_rate ?? 0)},
      {title: '胜率', dataIndex: 'backtest_win_rate', width: 95, render: fmtPct, sorter: (a, b) => (a.backtest_win_rate ?? 0) - (b.backtest_win_rate ?? 0)},
      {title: '均收益', dataIndex: 'backtest_avg_return_pct', width: 95, render: fmtPct, sorter: (a, b) => (a.backtest_avg_return_pct ?? 0) - (b.backtest_avg_return_pct ?? 0)},
      {
        title: '操作',
        fixed: 'right',
        width: 100,
        render: (_, row) => (
          <Button type="link" size="small" onClick={() => handleLoadSamples(row)}>
            样本
          </Button>
        ),
      },
    ],
    [],
  );

  const sampleColumns: ColumnsType<MacdAlertBacktestSampleRow> = [
    {
      title: '样本说明',
      render: (_, row) => <Typography.Text>{formatSampleSentence(row)}</Typography.Text>,
      sorter: (a, b) => a.alert_date.localeCompare(b.alert_date),
    },
    {title: '收益率', dataIndex: 'return_pct', width: 100, render: fmtPct, sorter: (a, b) => (a.return_pct ?? 0) - (b.return_pct ?? 0)},
    {title: '持有天数', dataIndex: 'holding_days', width: 95, render: (value: number | null) => value ?? '-', sorter: (a, b) => (a.holding_days ?? 0) - (b.holding_days ?? 0)},
    {title: '状态', dataIndex: 'status', width: 130, render: (value: string) => sampleStatusText[value] ?? value, sorter: (a, b) => a.status.localeCompare(b.status)},
  ];
  const scanProgress = scanTaskItems?.progress_percent ?? scanTask?.progress_percent ?? 0;
  const scanRunning = !!scanTask && ['PENDING', 'RUNNING'].includes(scanTask.status);

  return (
    <Space direction="vertical" size={16} style={{display: 'flex'}}>
      <div>
        <Typography.Title level={2} style={{marginTop: 0, marginBottom: 4}}>
          MACD 形态预警
        </Typography.Title>
        <Typography.Text type="secondary">技术形态观察结果，不构成买卖建议。</Typography.Text>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card title="收盘扫描">
            <Form<ScanFormValues>
              form={scanForm}
              layout="inline"
              initialValues={{green_shrink_days: 2}}
              onFinish={handleScan}
            >
              <Form.Item name="trade_date" label="交易日" rules={[{required: true, message: '请选择交易日'}]}>
                <Input type="date" style={{width: 150}} />
              </Form.Item>
              <Form.Item name="green_shrink_days" label="绿柱缩短" rules={[{required: true}]}>
                <InputNumber min={1} max={10} style={{width: 90}} />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit" loading={loading} icon={<SearchOutlined />}>
                  扫描
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card title="T+1 跟踪">
            <Form<TrackFormValues> form={trackForm} layout="inline" onFinish={handleTrack}>
              <Form.Item name="source_trade_date" label="来源日" rules={[{required: true}]}>
                <Input type="date" style={{width: 150}} />
              </Form.Item>
              <Form.Item name="trade_date" label="跟踪日" rules={[{required: true}]}>
                <Input type="date" style={{width: 150}} />
              </Form.Item>
              <Form.Item>
                <Button htmlType="submit" loading={tracking} icon={<ReloadOutlined />}>
                  跟踪
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </Col>
      </Row>

      {scanTask ? (
        <Card
          title={`扫描任务 ${scanTask.task_id}`}
          extra={
            scanRunning ? (
              <Button danger size="small" onClick={handleTerminateScanTask}>
                终止
              </Button>
            ) : null
          }
        >
          <Space direction="vertical" size={12} style={{display: 'flex'}}>
            <Space wrap>
              <Tag color={scanTask.status === 'SUCCESS' ? 'green' : scanTask.status === 'FAILED' ? 'red' : 'blue'}>
                {scanTask.status}
              </Tag>
              <Typography.Text type="secondary">
                当前处理：{scanTaskItems?.current_label || scanTask.current_label || '-'}
              </Typography.Text>
              <Typography.Text type="secondary">
                {scanTaskItems?.processed_items ?? scanTask.processed_items} / {scanTaskItems?.total_items ?? scanTask.total_items}
              </Typography.Text>
            </Space>
            <Progress percent={scanProgress} status={scanTask.status === 'FAILED' ? 'exception' : undefined} />
            {scanTask.error_message ? <Alert type="error" showIcon message={scanTask.error_message} /> : null}
          </Space>
        </Card>
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="扫描股票" value={scanTaskItems?.total_items ?? scanTask?.total_items ?? 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="新增预警" value={rows.length} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="已金叉" value={trackSummary?.cross_confirmed_count ?? 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="趋势维持" value={trackSummary?.trend_kept_count ?? 0} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={6}>
          <Card
            title={<><HistoryOutlined /> 扫描历史</>}
            size="small"
            bodyStyle={{padding: 0, maxHeight: '60vh', overflow: 'auto'}}
            extra={
              <Button type="link" size="small" loading={historyLoading} onClick={refreshTaskHistory}>
                刷新
              </Button>
            }
          >
            <List
              loading={historyLoading}
              dataSource={taskHistory}
              locale={{emptyText: <Empty description="暂无扫描记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />}}
              renderItem={(task) => (
                <List.Item
                  onClick={() => handleSelectTask(task)}
                  style={{
                    cursor: 'pointer',
                    padding: '8px 16px',
                    backgroundColor: activeTaskId === task.task_id ? '#e6f4ff' : undefined,
                    borderLeft: activeTaskId === task.task_id ? '3px solid #1677ff' : '3px solid transparent',
                  }}
                >
                  <List.Item.Meta
                    title={
                      <Space size={4}>
                        <span>{taskDate(task)}</span>
                        <Badge status={statusColor[task.status] as any} text={statusLabel[task.status] || task.status} />
                      </Space>
                    }
                    description={
                      <Space size={8}>
                        <Typography.Text type="secondary" style={{fontSize: 12}}>
                          {task.task_start_date?.slice(0, 16) || '-'}
                        </Typography.Text>
                        {activeTaskId === task.task_id && rows.length > 0 ? (
                          <Typography.Text type="secondary" style={{fontSize: 12}}>
                            绿柱≥{greenShrinkDays || 2}天 · {rows.length}条
                          </Typography.Text>
                        ) : null}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} md={18}>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: 'alerts',
                label: activeTradeDate
                  ? `${activeTradeDate} 预警结果（绿柱缩短≥${greenShrinkDays || 2}天，共 ${rows.length} 条）`
                  : '预警结果',
                children: (
                  <Card
                    bodyStyle={{padding: 0}}
                    extra={
                      rows.length > 0 ? (
                        <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
                          导出CSV
                        </Button>
                      ) : null
                    }
                  >
                    <Table<MacdAlertResultRow>
                      rowKey="id"
                      columns={alertColumns}
                      dataSource={rows}
                      loading={loading || tracking}
                      scroll={{x: 1600}}
                      pagination={{pageSize: 20, showSizeChanger: true}}
                      expandable={{
                        expandedRowRender: (row) => (
                          <Typography.Paragraph style={{margin: 0}}>{row.summary}</Typography.Paragraph>
                        ),
                      }}
                      locale={{emptyText: <Empty description={activeTradeDate ? `${activeTradeDate} 暂无预警结果` : '请从左侧选择扫描记录'} />}}
                    />
                  </Card>
                ),
              },
              {
                key: 'stock',
                label: '个股验证',
                children: (
                  <Card>
                    <Space direction="vertical" size={16} style={{display: 'flex'}}>
                      <Form<StockValidateFormValues>
                        form={stockValidateForm}
                        layout="inline"
                        initialValues={{lookback_days: 720, green_shrink_days: 2}}
                        onFinish={handleStockValidate}
                      >
                        <Form.Item
                          name="stock_code"
                          label="股票代码"
                          rules={[
                            {required: true, message: '请输入股票代码'},
                            {len: 6, message: '股票代码需为6位'},
                          ]}
                        >
                          <Input placeholder="如 600545" style={{width: 130}} />
                        </Form.Item>
                        <Form.Item name="end_date" label="截止日" rules={[{required: true, message: '请选择截止日'}]}>
                          <Input type="date" style={{width: 150}} />
                        </Form.Item>
                        <Form.Item name="lookback_days" label="回看">
                          <InputNumber min={30} max={3000} style={{width: 90}} />
                        </Form.Item>
                        <Form.Item name="green_shrink_days" label="绿柱缩短">
                          <InputNumber min={1} max={10} style={{width: 90}} />
                        </Form.Item>
                        <Form.Item>
                          <Button type="primary" htmlType="submit" loading={stockValidating} icon={<SearchOutlined />}>
                            验证
                          </Button>
                        </Form.Item>
                      </Form>

                      {stockValidateResult ? (
                        <Space direction="vertical" size={16} style={{display: 'flex'}}>
                          <Alert
                            type={stockValidateResult.triggered_on_end_date ? 'success' : 'info'}
                            showIcon
                            message={`${stockValidateResult.stock_code} ${stockValidateResult.stock_name} · ${stockValidateResult.end_date}`}
                            description={
                              stockValidateResult.triggered_on_end_date
                                ? '截止日触发 MACD 金叉临界形态。'
                                : '截止日未触发 MACD 金叉临界形态；下方展示回看区间内最近触发和历史样本，用于核验规则口径。'
                            }
                          />

                          <Row gutter={[16, 16]}>
                            <Col xs={12} md={6}>
                              <Statistic title="历史样本" value={stockValidateResult.summary.backtest_sample_count} />
                            </Col>
                            <Col xs={12} md={6}>
                              <Statistic title="金叉率" value={fmtPct(stockValidateResult.summary.backtest_cross_success_rate)} />
                            </Col>
                            <Col xs={12} md={6}>
                              <Statistic title="胜率" value={fmtPct(stockValidateResult.summary.backtest_win_rate)} />
                            </Col>
                            <Col xs={12} md={6}>
                              <Statistic title="均收益" value={fmtPct(stockValidateResult.summary.backtest_avg_return_pct)} />
                            </Col>
                          </Row>

                          {stockValidateResult.latest_candidate ? (
                            <Alert
                              type="warning"
                              showIcon
                              message={`最近触发：${stockValidateResult.latest_candidate.trade_date} · ${zoneText[stockValidateResult.latest_candidate.cross_zone] ?? stockValidateResult.latest_candidate.cross_zone}`}
                              description={
                                <Space direction="vertical" size={4}>
                                  <Typography.Text>{stockValidateResult.latest_candidate.summary}</Typography.Text>
                                  <Typography.Text type="secondary">
                                    DIF {stockValidateResult.latest_candidate.macd_dif.toFixed(4)} / DEA {stockValidateResult.latest_candidate.macd_dea.toFixed(4)} / MACD柱 {stockValidateResult.latest_candidate.macd_hist.toFixed(4)}
                                  </Typography.Text>
                                </Space>
                              }
                            />
                          ) : (
                            <Empty description="回看区间内未找到 MACD 金叉临界样本" />
                          )}

                          <Table<MacdAlertBacktestSampleRow>
                            rowKey="id"
                            columns={sampleColumns}
                            dataSource={stockValidateResult.samples}
                            scroll={{x: 900}}
                            pagination={{pageSize: 20}}
                            expandable={{expandedRowRender: renderSampleDetail}}
                            locale={{emptyText: <Empty description="暂无历史样本" />}}
                          />
                        </Space>
                      ) : (
                        <Empty description="输入股票代码和截止日后开始验证" />
                      )}
                    </Space>
                  </Card>
                ),
              },
              {
                key: 'samples',
                label: '历史样本明细',
                children: (
                  <Card
                    title={selectedAlert ? `${selectedAlert.stock_code} ${selectedAlert.stock_name} 历史同类样本` : '历史同类样本'}
                    extra={selectedAlert ? <Tag>{selectedAlert.backtest_confidence_level}</Tag> : null}
                    bodyStyle={{padding: 0}}
                  >
                    <Table<MacdAlertBacktestSampleRow>
                      rowKey="id"
                      columns={sampleColumns}
                      dataSource={samples}
                      scroll={{x: 900}}
                      pagination={{pageSize: 20}}
                      expandable={{expandedRowRender: renderSampleDetail}}
                      locale={{emptyText: <Empty description="请先在预警列表中选择一条结果" />}}
                    />
                  </Card>
                ),
              },
            ]}
          />
        </Col>
      </Row>

      <Alert
        type="info"
        showIcon
        icon={<AlertOutlined />}
        message="报告按需生成"
        description="扫描、跟踪和回测只保存结构化结果；HTML/PDF 报告在需要时再生成。"
      />
    </Space>
  );
}
