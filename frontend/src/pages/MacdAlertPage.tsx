import {AlertOutlined, ReloadOutlined, SearchOutlined} from '@ant-design/icons';
import {Alert, Button, Card, Col, Empty, Form, Input, InputNumber, Progress, Row, Space, Statistic, Table, Tabs, Tag, Typography, message} from 'antd';
import type {ColumnsType} from 'antd/es/table';
import {useEffect, useMemo, useState} from 'react';
import {Link} from 'react-router-dom';
import {
  getInitTask,
  getTaskItems,
  listMacdAlertBacktestSamples,
  listMacdAlertResults,
  scanMacdAlerts,
  terminateInitTask,
  trackMacdAlerts,
  type MacdAlertBacktestSampleRow,
  type MacdAlertResultRow,
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

function fmtPrice(value: number | null | undefined): string {
  return value == null ? '-' : value.toFixed(2);
}

function fmtPct(value: number | null | undefined): string {
  return value == null ? '-' : `${(value * 100).toFixed(2)}%`;
}

export function MacdAlertPage() {
  const [scanForm] = Form.useForm<ScanFormValues>();
  const [trackForm] = Form.useForm<TrackFormValues>();
  const [loading, setLoading] = useState(false);
  const [tracking, setTracking] = useState(false);
  const [scanTask, setScanTask] = useState<TaskResponse | null>(null);
  const [scanTaskItems, setScanTaskItems] = useState<TaskItemsResponse | null>(null);
  const [scanTradeDate, setScanTradeDate] = useState<string>('');
  const [trackSummary, setTrackSummary] = useState<MacdAlertTrackResponse | null>(null);
  const [rows, setRows] = useState<MacdAlertResultRow[]>([]);
  const [samples, setSamples] = useState<MacdAlertBacktestSampleRow[]>([]);
  const [selectedAlert, setSelectedAlert] = useState<MacdAlertResultRow | null>(null);

  async function refreshResults(tradeDate: string) {
    const resultRows = await listMacdAlertResults({trade_date: tradeDate, limit: 100});
    setRows(resultRows);
  }

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
          if (scanTradeDate) await refreshResults(scanTradeDate);
          if (!cancelled) message.success('MACD 扫描任务完成');
        } else if (latest.status === 'FAILED') {
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

  async function handleTrack(values: TrackFormValues) {
    setTracking(true);
    try {
      const result = await trackMacdAlerts(values.trade_date, values.source_trade_date);
      setTrackSummary(result);
      await refreshResults(values.source_trade_date);
      message.success(`跟踪完成，处理 ${result.tracked_count} 只`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'MACD 跟踪失败');
    } finally {
      setTracking(false);
    }
  }

  async function handleLoadSamples(row: MacdAlertResultRow) {
    setSelectedAlert(row);
    setSamples([]);
    try {
      const sampleRows = await listMacdAlertBacktestSamples(row.id, 100);
      setSamples(sampleRows);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '历史样本加载失败');
    }
  }

  const alertColumns: ColumnsType<MacdAlertResultRow> = useMemo(
    () => [
      {
        title: '股票',
        fixed: 'left',
        width: 150,
        render: (_, row) => <Link to={`/stocks/${row.stock_code}`}>{row.stock_name || row.stock_code}</Link>,
      },
      {title: '代码', dataIndex: 'stock_code', width: 90},
      {
        title: '类型',
        dataIndex: 'cross_zone',
        width: 90,
        render: (value: string) => <Tag color={value === 'underwater' ? 'blue' : 'green'}>{zoneText[value] ?? value}</Tag>,
      },
      {title: '收盘价', dataIndex: 'close_price', width: 90, render: fmtPrice},
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
      {title: '金叉距离', dataIndex: 'cross_trigger_distance_pct', width: 105, render: fmtPct},
      {title: '维持价', dataIndex: 'next_trend_keep_price', width: 95, render: fmtPrice},
      {title: '维持距离', dataIndex: 'trend_keep_distance_pct', width: 105, render: fmtPct},
      {
        title: '题材',
        width: 150,
        render: (_, row) => row.last_limit_up_theme ? (
          <Space size={4}>
            <span>{row.last_limit_up_theme}</span>
            <Tag color={heatColor[row.theme_heat_level] ?? 'default'}>{row.theme_heat_level}</Tag>
          </Space>
        ) : '近120日无题材',
      },
      {
        title: '跟踪',
        dataIndex: 'track_status',
        width: 120,
        render: (value: string) => <Tag color={trackColor[value] ?? 'default'}>{value}</Tag>,
      },
      {title: '样本', dataIndex: 'backtest_sample_count', width: 80},
      {title: '金叉率', dataIndex: 'backtest_cross_success_rate', width: 95, render: fmtPct},
      {title: '胜率', dataIndex: 'backtest_win_rate', width: 95, render: fmtPct},
      {title: '均收益', dataIndex: 'backtest_avg_return_pct', width: 95, render: fmtPct},
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
    {title: '预警日', dataIndex: 'alert_date', width: 110},
    {title: 'T+1 状态', dataIndex: 't1_track_status', width: 150, render: (value: string | null) => value ?? '-'},
    {title: '金叉日', dataIndex: 'cross_date', width: 110, render: (value: string | null) => value ?? '-'},
    {title: '金叉类型', dataIndex: 'cross_type', width: 110, render: (value: string | null) => value ?? '-'},
    {title: '卖出日', dataIndex: 'sell_date', width: 110, render: (value: string | null) => value ?? '-'},
    {title: '卖出原因', dataIndex: 'sell_reason', width: 110, render: (value: string | null) => value ?? '-'},
    {title: '收益率', dataIndex: 'return_pct', width: 100, render: fmtPct},
    {title: '持有天数', dataIndex: 'holding_days', width: 95, render: (value: number | null) => value ?? '-'},
    {title: '状态', dataIndex: 'status', width: 150},
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

      <Tabs
        items={[
          {
            key: 'alerts',
            label: '今日预警与跟踪',
            children: (
              <Card bodyStyle={{padding: 0}}>
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
                  locale={{emptyText: <Empty description="暂无 MACD 预警结果" />}}
                />
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
                  scroll={{x: 1000}}
                  pagination={{pageSize: 20}}
                  locale={{emptyText: <Empty description="请先在预警列表中选择一条结果" />}}
                />
              </Card>
            ),
          },
        ]}
      />

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
