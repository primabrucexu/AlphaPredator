import {useEffect, useRef, useState} from 'react';
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
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import dayjs from 'dayjs';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  DisconnectOutlined,
  LinkOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import {
  clearJygsSession,
  createInitTask,
  getInitTask,
  getInitTaskDays,
  getInitV2Overview,
  getJygsAuthStatus,
  getMairuiLicenceConfig,
  type InitV2OverviewResponse,
  type JygsAuthStatus,
  loginJygsWithPlaywright,
  type MairuiLicenceConfigResponse,
  retryInitTask,
  saveMairuiLicence,
  type TaskDayItem,
  type TaskResponse,
  type TaskType,
  terminateInitTask,
  triggerDailyUpdate,
  type UpdateResult,
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
    case 'TERMINATED':
      return '#fa8c16';
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
    case 'TERMINATED':
      return '已终止';
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
    RUNNING: 'processing',
    FETCHING: 'processing',
    WRITING: 'processing',
    PENDING: 'warning',
  };
  const labels: Record<string, string> = {
    SUCCESS: '成功',
    FAILED: '失败',
    RUNNING: '执行中',
    FETCHING: '拉取中',
    WRITING: '写入中',
    PENDING: '等待',
  };
  return <Tag color={colors[s] ?? 'default'}>{labels[s] ?? s}</Tag>;
}

function taskTypeLabel(taskType: string | undefined): string {
  switch (taskType) {
    case 'STOCK_LIST_SYNC':
      return '股票列表同步';
    case 'JYGS_REVIEW':
      return '韭研复盘抓取';
    default:
      return '行情数据同步';
  }
}

export function InitializePage() {
  // JYGS auth
  const [jygsStatus, setJygsStatus] = useState<JygsAuthStatus | null>(null);
  const [jygsError, setJygsError] = useState<string | null>(null);
    const [jygsLoginLoading, setJygsLoginLoading] = useState(false);

  const [mairuiConfig, setMairuiConfig] = useState<MairuiLicenceConfigResponse | null>(null);
  const [mairuiLicenceInput, setMairuiLicenceInput] = useState('');
  const [mairuiSaveLoading, setMairuiSaveLoading] = useState(false);
  const [mairuiMessage, setMairuiMessage] = useState<string | null>(null);

  const [initOverview, setInitOverview] = useState<InitV2OverviewResponse | null>(null);

  // Task
  const [startDate, setStartDate] = useState<string>(DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState<string>(todayYYYYMMDD());
  const [startLoading, setStartLoading] = useState(false);
  const [currentTask, setCurrentTask] = useState<TaskResponse | null>(null);
  const [selectedTaskType, setSelectedTaskType] = useState<TaskType>('MARKET_DATA');
  const [selectedMode, setSelectedMode] = useState<string>('FULL_SYNC');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Day details
  const [showDays, setShowDays] = useState(false);
  const [days, setDays] = useState<TaskDayItem[]>([]);
  const [daysTotal, setDaysTotal] = useState(0);
  const [daysPage, setDaysPage] = useState(1);
  const [daysLoading, setDaysLoading] = useState(false);

  // Daily update
  const [updateLoading, setUpdateLoading] = useState(false);
  const [updateResult, setUpdateResult] = useState<UpdateResult | null>(null);
  const [taskActionLoading, setTaskActionLoading] = useState(false);

  // Error
  const [error, setError] = useState<string | null>(null);

  // Initial load
  useEffect(() => {
    Promise.all([getInitV2Overview(), getJygsAuthStatus(), getMairuiLicenceConfig()])
        .then(([overview, jygs, mairui]) => {
        setInitOverview(overview);
        setCurrentTask(overview.running_task ?? overview.latest_task ?? null);
        setJygsStatus(jygs);
          setMairuiConfig(mairui);
      })
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

  const handleStartInit = async () => {
    setError(null);
    setStartLoading(true);
    setCurrentTask(null);
    setShowDays(false);
    try {
      // STOCK_LIST_SYNC uses today as placeholder date; backend ignores it
      const sd = selectedTaskType === 'STOCK_LIST_SYNC' ? todayYYYYMMDD() : startDate;
      const ed = selectedTaskType === 'STOCK_LIST_SYNC' ? todayYYYYMMDD() : endDate;
      const mode = selectedTaskType === 'MARKET_DATA' ? selectedMode : 'FULL_SYNC';
      const task = await createInitTask(sd, ed, mode, selectedTaskType);
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

  const handleSaveMairuiLicence = async () => {
    const value = mairuiLicenceInput.trim();
    if (!value) {
      setError('请输入有效的 Mairui licence');
      return;
    }

    setError(null);
    setMairuiMessage(null);
    setMairuiSaveLoading(true);
    try {
      const config = await saveMairuiLicence(value);
      setMairuiConfig(config);
      setMairuiLicenceInput('');
      setMairuiMessage('Mairui licence 已保存');
      const overview = await getInitV2Overview();
      setInitOverview(overview);
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存 Mairui licence 失败');
    } finally {
      setMairuiSaveLoading(false);
    }
  };

  const handleRetryTask = async () => {
    if (!currentTask) return;
    setError(null);
    setTaskActionLoading(true);
    try {
      const task = await retryInitTask(currentTask.task_id);
      setCurrentTask(task);
    } catch (e) {
      setError(e instanceof Error ? e.message : '重试任务失败');
    } finally {
      setTaskActionLoading(false);
    }
  };

  const handleTerminateTask = async () => {
    if (!currentTask) return;
    setError(null);
    setTaskActionLoading(true);
    try {
      const task = await terminateInitTask(currentTask.task_id);
      setCurrentTask(task);
    } catch (e) {
      setError(e instanceof Error ? e.message : '终止任务失败');
    } finally {
      setTaskActionLoading(false);
    }
  };

  // ── 韭研公社连接 handlers ───────────────────────────────────────────────

    const handleJygsPlaywrightLogin = async () => {
        setJygsLoginLoading(true);
    setJygsError(null);
        try {
            await loginJygsWithPlaywright(300);
            const status = await getJygsAuthStatus();
            setJygsStatus(status);
            if (!status.valid) {
                setJygsError('登录流程完成，但凭据校验未通过，请重试。');
            }
    } catch (e) {
            setJygsError(e instanceof Error ? e.message : 'Playwright 登录失败');
    } finally {
            setJygsLoginLoading(false);
    }
  };

  const handleJygsDisconnect = async () => {
    await clearJygsSession();
    setJygsStatus({ configured: false, valid: false, saved_at: null, expires_at: null });
  };


  const isRunning = currentTask?.status === 'RUNNING';
  const isDone = currentTask?.status === 'SUCCESS';
  const isFailed = currentTask?.status === 'FAILED';
  const isTerminated = currentTask?.status === 'TERMINATED';
  const isMarketTask = selectedTaskType === 'MARKET_DATA' || selectedTaskType === 'STOCK_LIST_SYNC';
  const canStartTask = isMarketTask ? !!initOverview?.market_data_configured : !!jygsStatus?.valid;

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
          通过 Mairui 接入全市场 A 股历史日线数据，支持按日期区间全量初始化。
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

      {mairuiMessage && (
        <Alert
          type="success"
          showIcon
          closable
          message={mairuiMessage}
          onClose={() => setMairuiMessage(null)}
        />
      )}

      <Card
          className="page-card"
          title={
            <Space>
              <DatabaseOutlined/>
              Mairui Licence 配置
            </Space>
          }
      >
        <Space direction="vertical" size={12} style={{width: '100%'}}>
          <Space>
            <Typography.Text>当前状态：</Typography.Text>
            {mairuiConfig === null ? (
                <Tag>检查中…</Tag>
            ) : mairuiConfig.configured ? (
                <Tag color="success" icon={<CheckCircleOutlined/>}>已配置</Tag>
            ) : (
                <Tag color="warning" icon={<CloseCircleOutlined/>}>未配置</Tag>
            )}
            {mairuiConfig?.configured && mairuiConfig.masked_licence && (
                <Typography.Text type="secondary" style={{fontSize: 12}}>
                  当前 Licence：{mairuiConfig.masked_licence}（来源：{mairuiConfig.source}）
                </Typography.Text>
            )}
          </Space>

          <Space.Compact style={{width: '100%', maxWidth: 640}}>
            <Input.Password
                value={mairuiLicenceInput}
                placeholder="请输入 Mairui licence"
                onChange={(e) => setMairuiLicenceInput(e.target.value)}
            />
            <Button
                type="primary"
                loading={mairuiSaveLoading}
                onClick={handleSaveMairuiLicence}
            >
              保存 Licence
            </Button>
          </Space.Compact>

          <Typography.Text type="secondary" style={{fontSize: 12}}>
            保存后将写入后端配置文件，并用于后续麦蕊行情接口请求。
          </Typography.Text>
        </Space>
      </Card>

      {/* 韭研公社连接 */}
      <Card
        className="page-card"
        title={
          <Space>
            <LinkOutlined />
            韭研公社连接
          </Space>
        }
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {/* 当前连接状态 */}
          <Space>
            <Typography.Text>当前状态：</Typography.Text>
            {jygsStatus === null ? (
              <Tag>检查中…</Tag>
            ) : jygsStatus.valid ? (
              <Tag color="success" icon={<CheckCircleOutlined />}>已连接</Tag>
            ) : (
              <Tag color="warning" icon={<CloseCircleOutlined />}>未连接</Tag>
            )}
            {jygsStatus?.valid && jygsStatus.saved_at && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                凭据保存于 {new Date(jygsStatus.saved_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}
              </Typography.Text>
            )}
          </Space>

          {/* 连接 / 断开 操作 */}
          {!jygsStatus?.valid ? (
              <Space direction="vertical" size={6} style={{width: '100%'}}>
                  <Typography.Text type="secondary">
                      点击后端 Playwright 一键登录，会弹出网页端页面，请在浏览器中完成登录。
                  </Typography.Text>
              <Button
                  type="primary"
                  icon={<LinkOutlined/>}
                  loading={jygsLoginLoading}
                  onClick={handleJygsPlaywrightLogin}
              >
                  Playwright 一键登录
              </Button>
            </Space>
          ) : (
            <Button
              icon={<DisconnectOutlined />}
              danger
              onClick={handleJygsDisconnect}
            >
              断开连接
            </Button>
          )}

          {/* JYGS 错误提示 */}
          {jygsError && (
            <Alert type="warning" showIcon closable message={jygsError} onClose={() => setJygsError(null)} />
          )}
        </Space>
      </Card>

      {/* V2 Init task creation */}
      <Card
        className="page-card"
        title={
          <Space>
            <DatabaseOutlined />
            任务创建
          </Space>
        }
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            支持三类任务：股票列表同步、行情数据同步（全量/增量）、韭研复盘抓取。
          </Typography.Text>
          <Space wrap>
            <Space direction="vertical" size={4}>
              <Typography.Text>任务类型：</Typography.Text>
              <Select<TaskType>
                value={selectedTaskType}
                onChange={(v) => {
                  setSelectedTaskType(v);
                  if (v === 'MARKET_DATA') setSelectedMode('FULL_SYNC');
                }}
                disabled={isRunning}
                style={{ width: 220 }}
                options={[
                  {label: '股票列表同步', value: 'STOCK_LIST_SYNC'},
                  {label: '行情数据同步', value: 'MARKET_DATA'},
                  { label: '韭研复盘抓取', value: 'JYGS_REVIEW' },
                ]}
              />
            </Space>

            {selectedTaskType === 'MARKET_DATA' && (
                <Space direction="vertical" size={4}>
                  <Typography.Text>同步模式：</Typography.Text>
                  <Select<string>
                      value={selectedMode}
                      onChange={setSelectedMode}
                      disabled={isRunning}
                      style={{width: 180}}
                      options={[
                        {label: '全量同步', value: 'FULL_SYNC'},
                        {label: '增量同步（自动续接）', value: 'INCREMENTAL_SYNC'},
                      ]}
                  />
                </Space>
            )}

            {selectedTaskType !== 'STOCK_LIST_SYNC' && (
                <Space direction="vertical" size={4}>
                  <Typography.Text>
                    {selectedTaskType === 'MARKET_DATA' && selectedMode === 'INCREMENTAL_SYNC'
                        ? '截止日期（起始日期自动检测）：'
                        : '导入区间：'}
                  </Typography.Text>
                  {selectedMode === 'INCREMENTAL_SYNC' && selectedTaskType === 'MARKET_DATA' ? (
                      <DatePicker
                          format="YYYYMMDD"
                          value={endDate ? dayjs(endDate, 'YYYYMMDD') : null}
                          onChange={(d) => {
                            if (d) setEndDate(d.format('YYYYMMDD'));
                          }}
                          disabled={isRunning}
                          allowClear={false}
                      />
                  ) : (
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
                  )}
                </Space>
            )}

            <Button
              type="primary"
              icon={<DatabaseOutlined />}
              loading={startLoading}
              disabled={isRunning || !canStartTask}
              onClick={handleStartInit}
              style={{ marginTop: 20 }}
            >
              {isRunning ? '任务运行中…' : (
                  selectedTaskType === 'STOCK_LIST_SYNC' ? '同步股票列表' :
                      selectedTaskType === 'JYGS_REVIEW' ? '开始韭研复盘抓取' :
                          selectedMode === 'INCREMENTAL_SYNC' ? '增量同步行情' : '全量同步行情'
              )}
            </Button>
          </Space>
          {!canStartTask && (
            <Alert
              type="warning"
              showIcon
              message={
                selectedTaskType === 'JYGS_REVIEW'
                  ? '请先完成韭研公社连接，再启动复盘抓取任务。'
                    : '请先配置 Mairui licence，再启动行情初始化任务。'
              }
            />
          )}
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
                      (isFailed || isTerminated) ? <CloseCircleOutlined/> :
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
                  title="已处理"
                  value={`${currentTask.processed_days} / ${currentTask.total_days}`}
                  suffix="天"
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
            <Descriptions.Item label="任务类型">{taskTypeLabel(currentTask.task_type)}</Descriptions.Item>
            <Descriptions.Item label="模式">{currentTask.mode}</Descriptions.Item>
            <Descriptions.Item label="日期区间">
              {currentTask.start_date} — {currentTask.end_date}
            </Descriptions.Item>
            <Descriptions.Item label="开始时间">{formatIso(currentTask.started_at)}</Descriptions.Item>
            {(isDone || isFailed || isTerminated) && (
              <Descriptions.Item label="完成时间">{formatIso(currentTask.finished_at)}</Descriptions.Item>
            )}
            {(isFailed || isTerminated) && (
              <Descriptions.Item label="错误信息" span={2}>
                <Typography.Text type="danger">{currentTask.error_message}</Typography.Text>
              </Descriptions.Item>
            )}
          </Descriptions>

          <Space style={{marginTop: 12}}>
            <Button size="small" onClick={handleToggleDays}>
              {showDays ? '收起日明细' : '查看日明细'}
            </Button>
            {isFailed && (
                <Button size="small" type="primary" loading={taskActionLoading} onClick={handleRetryTask}>
                  重试任务
                </Button>
            )}
            {(isRunning || isFailed) && (
                <Button size="small" danger loading={taskActionLoading} onClick={handleTerminateTask}>
                  终止任务
                </Button>
            )}
          </Space>

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
