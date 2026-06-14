import {BarChartOutlined, ThunderboltOutlined} from '@ant-design/icons';
import {Alert, Button, Card, Form, Input, InputNumber, Radio, Space, Table, Tag, Typography, message} from 'antd';
import {useEffect, useMemo, useState} from 'react';
import {
  createStockLinkageBacktest,
  getStockLinkageBacktest,
  getStockLinkageBacktestResults,
  type StockLinkageASelectMode,
  type StockLinkageBacktestJobResponse,
  type StockLinkageBacktestResultRow,
} from '../lib/api';

const triggerTypeText: Record<string, string> = {
  single_bar_return: '单根5分钟',
  intraday_return_from_pre_close: '相对昨收',
};

const observationTypeText: Record<string, string> = {
  t_day_high: 'T日最高',
  t_day_close: 'T日收盘',
  next_day_high: 'T+1最高',
  next_day_close: 'T+1收盘',
};

const confidenceColor: Record<string, string> = {
  high: 'green',
  medium: 'blue',
  low: 'orange',
  insufficient: 'default',
};

function toPercent(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

interface FormValues {
  a_select_mode: StockLinkageASelectMode;
  manual_a_full_code?: string;
  hot_top_n?: number;
  start_date: string;
  end_date: string;
  min_sample_count: number;
}

export function StockLinkagePage() {
  const [form] = Form.useForm<FormValues>();
  const [loading, setLoading] = useState(false);
  const [job, setJob] = useState<StockLinkageBacktestJobResponse | null>(null);
  const [polling, setPolling] = useState(false);
  const [rows, setRows] = useState<StockLinkageBacktestResultRow[]>([]);
  const mode = Form.useWatch('a_select_mode', form) ?? 'manual_single';

  useEffect(() => {
    if (!job || !['pending', 'running'].includes(job.status)) return undefined;

    let cancelled = false;
    async function refreshJob() {
      if (!job) return;
      setPolling(true);
      try {
        const latest = await getStockLinkageBacktest(job.job_id);
        if (cancelled) return;
        setJob(latest);
        if (latest.status === 'success') {
          const resultRows = await getStockLinkageBacktestResults(latest.job_id, 200);
          if (cancelled) return;
          setRows(resultRows);
          message.success('回测完成');
        } else if (latest.status === 'failed') {
          message.error(latest.error_message || '回测失败');
        }
      } catch (error) {
        if (!cancelled) {
          message.error(error instanceof Error ? error.message : '任务状态查询失败');
        }
      } finally {
        if (!cancelled) setPolling(false);
      }
    }

    refreshJob();
    const timer = window.setInterval(refreshJob, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job?.job_id, job?.status]);

  const columns = useMemo(
    () => [
      {
        title: 'A股票',
        dataIndex: 'a_full_code',
        width: 120,
        fixed: 'left' as const,
      },
      {
        title: 'B股票',
        dataIndex: 'b_full_code',
        width: 120,
        fixed: 'left' as const,
      },
      {
        title: 'A触发',
        key: 'trigger',
        width: 170,
        render: (_: unknown, row: StockLinkageBacktestResultRow) => (
          <Space size={4}>
            <span>{triggerTypeText[row.trigger_type] ?? row.trigger_type}</span>
            <Tag>{toPercent(row.trigger_threshold)}</Tag>
          </Space>
        ),
      },
      {
        title: 'B观察',
        key: 'observation',
        width: 150,
        render: (_: unknown, row: StockLinkageBacktestResultRow) => (
          <Space size={4}>
            <span>{observationTypeText[row.observation_type] ?? row.observation_type}</span>
            <Tag>{toPercent(row.target_threshold)}</Tag>
          </Space>
        ),
      },
      {
        title: '条件概率',
        dataIndex: 'condition_probability',
        width: 120,
        render: (value: number) => toPercent(value),
        sorter: (a: StockLinkageBacktestResultRow, b: StockLinkageBacktestResultRow) =>
          a.condition_probability - b.condition_probability,
      },
      {
        title: 'B基准',
        dataIndex: 'baseline_probability',
        width: 120,
        render: (value: number) => toPercent(value),
      },
      {
        title: '概率提升',
        dataIndex: 'probability_lift',
        width: 120,
        render: (value: number) => toPercent(value),
        sorter: (a: StockLinkageBacktestResultRow, b: StockLinkageBacktestResultRow) =>
          a.probability_lift - b.probability_lift,
      },
      {
        title: '提升倍数',
        dataIndex: 'lift_multiple',
        width: 110,
        render: (value: number | null) => (value == null ? '-' : `${value.toFixed(2)}x`),
      },
      {
        title: '样本',
        dataIndex: 'sample_count',
        width: 90,
        sorter: (a: StockLinkageBacktestResultRow, b: StockLinkageBacktestResultRow) =>
          a.sample_count - b.sample_count,
      },
      {
        title: '覆盖率',
        dataIndex: 'trigger_coverage_rate',
        width: 110,
        render: (value: number) => toPercent(value),
      },
      {
        title: '可信度',
        dataIndex: 'confidence_level',
        width: 110,
        render: (value: string) => <Tag color={confidenceColor[value] ?? 'default'}>{value}</Tag>,
      },
      {
        title: '综合分',
        dataIndex: 'score',
        width: 110,
        render: (value: number) => value.toFixed(4),
        sorter: (a: StockLinkageBacktestResultRow, b: StockLinkageBacktestResultRow) => a.score - b.score,
        defaultSortOrder: 'descend' as const,
      },
    ],
    [],
  );

  async function handleFinish(values: FormValues) {
    setLoading(true);
    setJob(null);
    setRows([]);
    try {
      const result = await createStockLinkageBacktest({
        a_select_mode: values.a_select_mode,
        manual_a_full_code: values.a_select_mode === 'manual_single' ? values.manual_a_full_code?.trim() : null,
        hot_top_n: values.a_select_mode === 'hot_limit_top' ? values.hot_top_n : null,
        start_date: values.start_date,
        end_date: values.end_date,
        min_sample_count: values.min_sample_count,
      });
      setJob(result);
      message.success('回测任务已提交');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '回测失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 16}}>
      <div>
        <Typography.Title level={3} style={{marginTop: 0, marginBottom: 4}}>
          股票联动套利分析
        </Typography.Title>
        <Typography.Text type="secondary">
          基于5分钟K线，统计A股票异动后B股票当日与次日的上涨概率。
        </Typography.Text>
      </div>

      <Card>
        <Form<FormValues>
          form={form}
          layout="inline"
          initialValues={{
            a_select_mode: 'manual_single',
            start_date: '2025-01-01',
            min_sample_count: 30,
            hot_top_n: 20,
          }}
          onFinish={handleFinish}
        >
          <Form.Item name="a_select_mode" label="A范围">
            <Radio.Group optionType="button" buttonStyle="solid">
              <Radio.Button value="manual_single">指定股票</Radio.Button>
              <Radio.Button value="hot_limit_top">涨停Top N</Radio.Button>
            </Radio.Group>
          </Form.Item>

          {mode === 'manual_single' ? (
            <Form.Item
              name="manual_a_full_code"
              label="A股票"
              rules={[{required: true, message: '请输入完整股票代码'}]}
            >
              <Input placeholder="000001.SZ" style={{width: 140}} />
            </Form.Item>
          ) : (
            <Form.Item name="hot_top_n" label="Top N" rules={[{required: true}]}>
              <InputNumber min={1} max={200} style={{width: 100}} />
            </Form.Item>
          )}

          <Form.Item name="start_date" label="开始" rules={[{required: true}]}>
            <Input type="date" style={{width: 150}} />
          </Form.Item>
          <Form.Item name="end_date" label="结束" rules={[{required: true}]}>
            <Input type="date" style={{width: 150}} />
          </Form.Item>
          <Form.Item name="min_sample_count" label="样本门槛" rules={[{required: true}]}>
            <InputNumber min={1} max={10000} style={{width: 110}} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} icon={<ThunderboltOutlined />}>
              开始回测
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {job ? (
        <Alert
          type={job.status === 'failed' ? 'error' : job.status === 'success' ? 'success' : 'info'}
          showIcon
          icon={<BarChartOutlined />}
          message={`任务 ${job.job_id}`}
          description={
            job.status === 'failed'
              ? job.error_message || '任务执行失败'
              : `当前状态：${job.status}。任务完成后会自动加载结果。`
          }
        />
      ) : null}

      <Card bodyStyle={{padding: 0}}>
        <Table<StockLinkageBacktestResultRow>
          rowKey={(row) =>
            `${row.a_full_code}-${row.b_full_code}-${row.trigger_type}-${row.trigger_threshold}-${row.observation_type}-${row.target_threshold}`
          }
          columns={columns}
          dataSource={rows}
          loading={loading || polling || job?.status === 'pending' || job?.status === 'running'}
          scroll={{x: 1500}}
          pagination={{pageSize: 20, showSizeChanger: true}}
        />
      </Card>
    </div>
  );
}
