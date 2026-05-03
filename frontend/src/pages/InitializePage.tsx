import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Input,
  Progress,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd';
import type { UploadFile } from 'antd/es/upload';
import dayjs from 'dayjs';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  LockOutlined,
  RedoOutlined,
  SyncOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import {
  type StockListUploadResponse,
  type TaskDayItem,
  type TaskResponse,
  type TokenConfigResponse,
  type UpdateResult,
  createInitTask,
  getInitTask,
  getInitTaskDays,
  getTokenConfig,
  reimportDay,
  saveTokenConfig,
  triggerDailyUpdate,
  uploadStockList,
} from '../lib/api';

const POLL_INTERVAL_MS = 2000;
const DEFAULT_START_DATE = '20240101';

function todayYYYYMMDD(): string {
  return dayjs().format('YYYYMMDD');
}

function formatIso(iso: string): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
  } catch {
    return iso;
  }
}

function taskStatusColor(s: string): string {
  switch (s) {
    case 'RUNNING':
      return '#1677ff';
    case 'SUCCESS':
      return '#52c41a';
    case 'FAILED':
      return '#ff4d4f';
    case 'PENDING':
      return '#faad14';
    default:
      return '#8c8c8c';
  }
}

function taskStatusLabel(s: string): string {
  switch (s) {
    case 'RUNNING':
      return '运行中';
    case 'SUCCESS':
      return '已完成';
    case 'FAILED':
      return '失败';
    case 'PENDING':
      return '等待中';
    default:
      return '未知';
  }
}

function dayStatusTag(s: string) {
  const colors: Record<string, string> = {
    SUCCESS: 'success',
    FAILED: 'error',
    SKIPPED_NON_TRADING: 'default',
    FETCHING: 'processing',
    WRITING: 'processing',
    PENDING: 'warning',
  };
  const labels: Record<string, string> = {
    SUCCESS: '成功',
    FAILED: '失败',
    SKIPPED_NON_TRADING: '非交易日',
    FETCHING: '拉取中',
    WRITING: '写入中',
    PENDING: '等待',
  };
  return <Tag color={colors[s] ?? 'default'}>{labels[s] ?? s}</Tag>;
}

export function InitializePage() {
  // Token
  const [tokenConfig, setTokenConfig] = useState<TokenConfigResponse | null>(null);
  const [tokenInput, setTokenInput] = useState('');
  const [tokenSaving, setTokenSaving] = useState(false);
  const [tokenSuccess, setTokenSuccess] = useState(false);

  // Stock list
  const [uploadFileList, setUploadFileList] = useState<UploadFile[]>([]);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState<StockListUploadResponse | null>(null);

  // Task
  const [startDate, setStartDate] = useState<string>(DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState<string>(todayYYYYMMDD());
  const [startLoading, setStartLoading] = useState(false);
  const [currentTask, setCurrentTask] = useState<TaskResponse | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Day details
  const [showDays, setShowDays] = useState(false);
  const [days, setDays] = useState<TaskDayItem[]>([]);
  const [daysTotal, setDaysTotal] = useState(0);
  const [daysPage, setDaysPage] = useState(1);
  const [daysLoading, setDaysLoading] = useState(false);

  // Reimport
  const [reimportDate, setReimportDate] = useState('');
  const [reimportLoading, setReimportLoading] = useState(false);

  // Daily update
  const [updateLoading, setUpdateLoading] = useState(false);
  const [updateResult, setUpdateResult] = useState<UpdateResult | null>(null);

  // Error
  const [error, setError] = useState<string | null>(null);

  // Initial load
  useEffect(() => {
    getTokenConfig()
      .then(setTokenConfig)
      .catch(() => {});
  }, []);

  // Polling when task is running
  useEffect(() => {
    if (currentTask?.status === 'RUNNING') {
      if (!pollRef.current) {
        pollRef.current = setInterval(async () => {
          if (!currentTask) return;
          try {
            const t = await getInitTask(currentTask.task_id);
            setCurrentTask(t);
          } catch {
            // ignore
          }
        }, POLL_INTERVAL_MS);
      }
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [currentTask?.status, currentTask?.task_id]);

  // Refresh day details when page changes or task updates
  useEffect(() => {
    if (showDays && currentTask) {
      loadDays(currentTask.task_id, daysPage);
    }
  }, [daysPage, currentTask?.processed_days]);

  async function loadDays(taskId: string, page: number) {
    setDaysLoading(true);
    try {
      const res = await getInitTaskDays(taskId, page, 50);
      setDays(res.days);
      setDaysTotal(res.total);
    } catch {
      // ignore
    } finally {
      setDaysLoading(false);
    }
  }

  // Handlers
  const handleSaveToken = async () => {
    if (!tokenInput.trim()) return;
    setTokenSaving(true);
    setTokenSuccess(false);
    try {
      const result = await saveTokenConfig(tokenInput.trim());
      setTokenConfig(result);
      setTokenInput('');
      setTokenSuccess(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存 Token 失败');
    } finally {
      setTokenSaving(false);
    }
  };

  const handleUploadStockList = async () => {
    if (uploadFileList.length === 0) return;
    const file = uploadFileList[0].originFileObj as File;
    setUploadLoading(true);
    setUploadResult(null);
    try {
      const result = await uploadStockList(file);
      setUploadResult(result);
      setUploadFileList([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : '上传股票清单失败');
    } finally {
      setUploadLoading(false);
    }
  };

  const handleStartInit = async () => {
    setError(null);
    setStartLoading(true);
    setCurrentTask(null);
    setShowDays(false);
    try {
      const task = await createInitTask(startDate, endDate, 'RANGE');
      setCurrentTask(task);
    } catch (e) {
      setError(e instanceof Error ? e.message : '启动初始化失败');
    } finally {
      setStartLoading(false);
    }
  };

  const handleToggleDays = async () => {
    if (!currentTask) return;
    if (!showDays) {
      await loadDays(currentTask.task_id, 1);
      setDaysPage(1);
    }
    setShowDays(!showDays);
  };

  const handleReimport = async () => {
    if (!reimportDate || !/^\d{8}$/.test(reimportDate)) {
      setError('请输入有效的交易日（格式 YYYYMMDD）');
      return;
    }
    setError(null);
    setReimportLoading(true);
    try {
      const task = await reimportDay(reimportDate);
      setCurrentTask(task);
      setReimportDate('');
    } catch (e) {
      setError(e instanceof Error ? e.message : '重导失败');
    } finally {
      setReimportLoading(false);
    }
  };

  const handleDailyUpdate = async () => {
    setError(null);
    setUpdateLoading(true);
    setUpdateResult(null);
    try {
      const result = await triggerDailyUpdate();
      setUpdateResult(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : '增量更新失败');
    } finally {
      setUpdateLoading(false);
    }
  };

  const isRunning = currentTask?.status === 'RUNNING';
  const isDone = currentTask?.status === 'SUCCESS';
  const isFailed = currentTask?.status === 'FAILED';

  const progressPercent = currentTask && currentTask.total_days > 0
    ? Math.round(currentTask.progress_percent)
    : 0;

  const dayColumns = [
    {
      title: '日期',
      dataIndex: 'trade_date',
      key: 'trade_date',
      width: 120,
    },
    {
      title: '类型',
      key: 'is_trading_day',
      width: 90,
      render: (_: unknown, r: TaskDayItem) => (
        <Tag color={r.is_trading_day ? 'blue' : 'default'}>
          {r.is_trading_day ? '交易日' : '非交易日'}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (s: string) => dayStatusTag(s),
    },
    {
      title: '行数',
      dataIndex: 'row_count',
      key: 'row_count',
      width: 80,
    },
    {
      title: '错误',
      dataIndex: 'error_message',
      key: 'error_message',
      render: (msg: string) =>
        msg ? <Typography.Text type="danger" style={{ fontSize: 12 }}>{msg}</Typography.Text> : '—',
    },
  ];

  return (
    <Space direction="vertical" size={24} style={{ display: 'flex' }}>
      <Space direction="vertical" size={4}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          市场数据初始化
        </Typography.Title>
        <Typography.Text type="secondary">
          通过 Tushare 接入全市场 A 股历史日线数据，支持按日期区间全量初始化与单日重导。
        </Typography.Text>
      </Space>

      {error && (
        <Alert
          type="error"
          showIcon
          closable
          message="操作失败"
          description={error}
          onClose={() => setError(null)}
        />
      )}

      {updateResult && (
        <Alert
          type="success"
          showIcon
          closable
          message={`增量更新完成：交易日 ${updateResult.trade_date}，更新 ${updateResult.stock_count} 支股票，${updateResult.bar_count} 条记录`}
          onClose={() => setUpdateResult(null)}
        />
      )}

      {/* Token config */}
      <Card
        className="page-card"
        title={
          <Space>
            <LockOutlined />
            Tushare Token 配置
          </Space>
        }
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space>
            <Typography.Text>当前状态：</Typography.Text>
            {tokenConfig === null ? (
              <Tag>检查中…</Tag>
            ) : tokenConfig.is_configured ? (
              <Tag color="success" icon={<CheckCircleOutlined />}>已配置</Tag>
            ) : (
              <Tag color="warning" icon={<CloseCircleOutlined />}>未配置</Tag>
            )}
          </Space>
          <Space wrap>
            <Input.Password
              placeholder="输入 Tushare API Token"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              style={{ width: 320 }}
              onPressEnter={handleSaveToken}
            />
            <Button
              type="primary"
              icon={<LockOutlined />}
              loading={tokenSaving}
              disabled={!tokenInput.trim()}
              onClick={handleSaveToken}
            >
              保存 Token
            </Button>
            {tokenSuccess && <Typography.Text type="success">Token 已保存</Typography.Text>}
          </Space>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Token 保存在服务端，不会在页面上显示。也可以通过环境变量 TUSHARE_TOKEN 配置。
          </Typography.Text>
        </Space>
      </Card>

      {/* Stock list upload */}
      <Card
        className="page-card"
        title={
          <Space>
            <UploadOutlined />
            上传股票清单 CSV
          </Space>
        }
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            请上传包含以下字段的 CSV 文件：
            <code> ts_code, symbol, name, market, list_status, list_date, delist_date</code>
          </Typography.Text>
          <Space wrap>
            <Upload
              accept=".csv"
              beforeUpload={() => false}
              fileList={uploadFileList}
              onChange={({ fileList }) => setUploadFileList(fileList.slice(-1))}
              maxCount={1}
            >
              <Button icon={<UploadOutlined />}>选择 CSV 文件</Button>
            </Upload>
            <Button
              type="primary"
              loading={uploadLoading}
              disabled={uploadFileList.length === 0}
              onClick={handleUploadStockList}
            >
              上传
            </Button>
          </Space>
          {uploadResult && (
            <Alert
              type="success"
              showIcon
              message={`上传成功：共 ${uploadResult.total_stocks} 支股票，当前上市 ${uploadResult.active_stocks} 支`}
              description={
                <Space wrap>
                  {Object.entries(uploadResult.boards).map(([board, count]) => (
                    <Tag key={board} color="blue">{board}: {count}</Tag>
                  ))}
                </Space>
              }
            />
          )}
        </Space>
      </Card>

      {/* V2 Init task creation */}
      <Card
        className="page-card"
        title={
          <Space>
            <DatabaseOutlined />
            全量初始化
          </Space>
        }
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            按日期区间逐日拉取 Tushare 全市场行情，直接写入本地数据库（无 CSV 中转）。
          </Typography.Text>
          <Space wrap>
            <Space direction="vertical" size={4}>
              <Typography.Text>导入区间：</Typography.Text>
              <DatePicker.RangePicker
                format="YYYYMMDD"
                value={[
                  startDate ? dayjs(startDate, 'YYYYMMDD') : null,
                  endDate ? dayjs(endDate, 'YYYYMMDD') : null,
                ]}
                onChange={(dates) => {
                  if (dates?.[0]) setStartDate(dates[0].format('YYYYMMDD'));
                  if (dates?.[1]) setEndDate(dates[1].format('YYYYMMDD'));
                }}
                disabled={isRunning}
                allowClear={false}
              />
            </Space>
            <Button
              type="primary"
              icon={<DatabaseOutlined />}
              loading={startLoading}
              disabled={isRunning}
              onClick={handleStartInit}
              style={{ marginTop: 20 }}
            >
              {isRunning ? '初始化中…' : '开始全量初始化'}
            </Button>
          </Space>
        </Space>
      </Card>

      {/* Task progress */}
      {currentTask && (
        <Card className="page-card" title="任务进度">
          <Row gutter={[16, 16]}>
            <Col xs={24} md={6}>
              <Statistic
                title="任务状态"
                value={taskStatusLabel(currentTask.status)}
                valueStyle={{ color: taskStatusColor(currentTask.status) }}
                prefix={
                  isRunning ? <SyncOutlined spin /> :
                  isDone ? <CheckCircleOutlined /> :
                  isFailed ? <CloseCircleOutlined /> :
                  <DatabaseOutlined />
                }
              />
            </Col>
            <Col xs={24} md={6}>
              <Statistic
                title="总天数"
                value={currentTask.total_days}
                suffix="天"
              />
            </Col>
            <Col xs={24} md={6}>
              <Statistic
                title="交易日"
                value={`${currentTask.done_trading_days} / ${currentTask.trading_days}`}
                suffix="日"
              />
            </Col>
            <Col xs={24} md={6}>
              <Statistic
                title="当前处理"
                value={currentTask.current_date || '—'}
              />
            </Col>
          </Row>

          {(isRunning || isDone) && (
            <div style={{ marginTop: 16 }}>
              <Progress
                percent={progressPercent}
                status={isRunning ? 'active' : isDone ? 'success' : 'exception'}
                format={(pct) =>
                  `${currentTask.processed_days} / ${currentTask.total_days} (${pct}%)`
                }
              />
            </div>
          )}

          <Descriptions style={{ marginTop: 16 }} column={2} size="small">
            <Descriptions.Item label="任务 ID">{currentTask.task_id}</Descriptions.Item>
            <Descriptions.Item label="模式">{currentTask.mode}</Descriptions.Item>
            <Descriptions.Item label="日期区间">
              {currentTask.start_date} — {currentTask.end_date}
            </Descriptions.Item>
            <Descriptions.Item label="开始时间">{formatIso(currentTask.started_at)}</Descriptions.Item>
            {(isDone || isFailed) && (
              <Descriptions.Item label="完成时间">{formatIso(currentTask.finished_at)}</Descriptions.Item>
            )}
            {isFailed && (
              <Descriptions.Item label="错误信息" span={2}>
                <Typography.Text type="danger">{currentTask.error_message}</Typography.Text>
              </Descriptions.Item>
            )}
          </Descriptions>

          <div style={{ marginTop: 12 }}>
            <Button size="small" onClick={handleToggleDays}>
              {showDays ? '收起日明细' : '查看日明细'}
            </Button>
          </div>

          {showDays && (
            <Table
              style={{ marginTop: 12 }}
              size="small"
              rowKey="trade_date"
              loading={daysLoading}
              dataSource={days}
              columns={dayColumns}
              pagination={{
                current: daysPage,
                pageSize: 50,
                total: daysTotal,
                showSizeChanger: false,
                onChange: (page) => setDaysPage(page),
              }}
              scroll={{ x: 600 }}
            />
          )}
        </Card>
      )}

      {/* Reimport day */}
      <Card
        className="page-card"
        title={
          <Space>
            <RedoOutlined />
            单日重导
          </Space>
        }
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            输入某一交易日（YYYYMMDD），系统将覆盖重导该日的全量行情数据。
          </Typography.Text>
          <Space wrap>
            <Input
              placeholder="例如：20240102"
              value={reimportDate}
              onChange={(e) => setReimportDate(e.target.value)}
              style={{ width: 160 }}
              onPressEnter={handleReimport}
              disabled={isRunning || reimportLoading}
            />
            <Button
              icon={<RedoOutlined />}
              loading={reimportLoading}
              disabled={isRunning || !reimportDate}
              onClick={handleReimport}
            >
              覆盖重导
            </Button>
          </Space>
        </Space>
      </Card>

      {/* Daily update */}
      <Card className="page-card" title="当日增量更新">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            仅拉取今日行情并刷新数据库，适合每个交易日收盘后执行，耗时较短。
          </Typography.Text>
          <Button
            icon={<SyncOutlined />}
            loading={updateLoading}
            disabled={isRunning}
            onClick={handleDailyUpdate}
          >
            当日增量更新
          </Button>
        </Space>
      </Card>
    </Space>
  );
}
