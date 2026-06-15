import {useEffect, useRef, useState} from 'react';
import {
    Alert,
    Button,
    Card,
    Col,
    DatePicker,
    Descriptions,
    Input,
    InputNumber,
    Progress,
    Row,
    Segmented,
    Select,
    Space,
    Statistic,
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
    type BatchTaskResponse,
    clearJygsSession,
    createBatchInitTasks,
    createInitTask,
    getInitTask,
    getInitV2Overview,
    getJygsAuthStatus,
    getLatestInitTaskByType,
    getMairuiLicenceConfig,
    getTaskItems,
    type InitV2OverviewResponse,
    type JygsAuthStatus,
    loginJygsWithPlaywright,
    type MairuiLicenceConfigResponse,
    retryInitSubtask,
    retryInitTask,
    saveMairuiLicence,
    type TaskItemsResponse,
    type TaskResponse,
    type TaskType,
    terminateInitTask,
} from '../lib/api';

const POLL_INTERVAL_MS = 2000;
const DEFAULT_START_DATE = '20240101';

function todayYYYYMMDD(): string {
  return dayjs().format('YYYYMMDD');
}

function addOneDayYYYYMMDD(dateText: string): string {
  if (!/^\d{8}$/.test(dateText)) return '';
  return dayjs(`${dateText.slice(0, 4)}-${dateText.slice(4, 6)}-${dateText.slice(6, 8)}`)
    .add(1, 'day')
    .format('YYYYMMDD');
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

function taskTypeLabel(taskType: string | undefined): string {
  switch (taskType) {
    case 'STOCK_LIST_SYNC':
      return '股票列表同步';
    case 'MARKET_DATA_5M':
      return '5分钟K同步';
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
  const [mairuiRateLimitInput, setMairuiRateLimitInput] = useState(1000);
  const [mairuiFetchConcurrencyInput, setMairuiFetchConcurrencyInput] = useState(4);
  const [mairuiSaveLoading, setMairuiSaveLoading] = useState(false);
  const [mairuiMessage, setMairuiMessage] = useState<string | null>(null);

  const [initOverview, setInitOverview] = useState<InitV2OverviewResponse | null>(null);
  const [activeSection, setActiveSection] = useState<'tasks' | 'data-source'>('tasks');

  // Task
  const [startDate, setStartDate] = useState<string>(DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState<string>(todayYYYYMMDD());
  const [startLoading, setStartLoading] = useState(false);
  const [currentTask, setCurrentTask] = useState<TaskResponse | null>(null);
  const [progressTaskType, setProgressTaskType] = useState<TaskType>('MARKET_DATA');
  const [progressTaskLoading, setProgressTaskLoading] = useState(false);
  const [selectedTaskType, setSelectedTaskType] = useState<TaskType>('MARKET_DATA');
  const [selectedMode, setSelectedMode] = useState<string>('FULL_SYNC');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Day details
  const [showDays, setShowDays] = useState(false);
  const [taskItems, setTaskItems] = useState<TaskItemsResponse | null>(null);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [retryItemLabel, setRetryItemLabel] = useState('');

  // Incremental update
  const [updateLoading, setUpdateLoading] = useState(false);
  const [taskActionLoading, setTaskActionLoading] = useState(false);

    // Batch tasks
    const [batchStartLoading, setBatchStartLoading] = useState(false);
    const [batchTasks, setBatchTasks] = useState<BatchTaskResponse | null>(null);
    const batchTaskIdsRef = useRef<{ stock: string; market: string; jygs: string } | null>(null);
    const batchPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Error
  const [error, setError] = useState<string | null>(null);

  // Initial load
  useEffect(() => {
    Promise.all([getInitV2Overview(), getJygsAuthStatus(), getMairuiLicenceConfig()])
        .then(([overview, jygs, mairui]) => {
        setInitOverview(overview);
        const task = overview.running_task ?? overview.latest_task ?? null;
        setCurrentTask(task);
        if (task) setProgressTaskType(task.task_type);
          setJygsStatus(jygs);
          setMairuiConfig(mairui);
          setMairuiRateLimitInput(mairui.rate_limit_per_minute);
          setMairuiFetchConcurrencyInput(mairui.fetch_concurrency);
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

  useEffect(() => {
    if (!currentTask || !['SUCCESS', 'FAILED', 'TERMINATED'].includes(currentTask.status)) return;
    getInitV2Overview()
      .then(setInitOverview)
      .catch(() => {});
  }, [currentTask?.status, currentTask?.task_id]);


  // Refresh subtask items when task updates
  useEffect(() => {
    if (showDays && currentTask) {
      loadTaskItems(currentTask.task_id);
    }
  }, [currentTask?.processed_items]);

    // Batch tasks polling
    useEffect(() => {
        const ids = batchTaskIdsRef.current;
        if (!ids) return;

        const poll = setInterval(async () => {
            try {
                const [st, md, jy] = await Promise.all([
                    getInitTask(ids.stock),
                    getInitTask(ids.market),
                    getInitTask(ids.jygs),
                ]);
                setBatchTasks({stock_list_task: st, market_data_task: md, jygs_review_task: jy});

                const done = (s: string) => ['SUCCESS', 'FAILED', 'TERMINATED'].includes(s);
                if (done(st.status) && done(md.status) && done(jy.status)) {
                    clearInterval(poll);
                    batchPollRef.current = null;
                }
            } catch {
                // ignore
            }
        }, POLL_INTERVAL_MS);

        batchPollRef.current = poll;
        return () => {
            clearInterval(poll);
            batchPollRef.current = null;
        };
    }, [batchTasks?.stock_list_task?.task_id]);

  async function loadTaskItems(taskId: string) {
    setItemsLoading(true);
    try {
      const res = await getTaskItems(taskId);
      setTaskItems(res);
      setRetryItemLabel((prev) => prev || res.current_label || '');
    } catch {
      // ignore
    } finally {
      setItemsLoading(false);
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
      setProgressTaskType(selectedTaskType);
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
      await loadTaskItems(currentTask.task_id);
    }
    setShowDays(!showDays);
  };

  const handleOneClickIncrementalUpdate = async () => {
    setError(null);
    setUpdateLoading(true);
    try {
      const latestMarketTask = initOverview?.latest_market_data_task;
      if (!latestMarketTask) {
        setError('暂无成功行情同步记录，请先执行一次全量行情同步。');
        return;
      }

      const nextStartDate = addOneDayYYYYMMDD(latestMarketTask.end_date);
      const targetEndDate = todayYYYYMMDD();
      if (!nextStartDate) {
        setError('最近成功行情任务的截止日期格式异常，无法自动计算增量区间。');
        return;
      }
      if (nextStartDate > targetEndDate) {
        setMairuiMessage('行情已同步到今天，无需增量更新。');
        return;
      }

      setSelectedTaskType('MARKET_DATA');
      setSelectedMode('INCREMENTAL_SYNC');
      setStartDate(nextStartDate);
      setEndDate(targetEndDate);
      setShowDays(false);
      const task = await createInitTask(nextStartDate, targetEndDate, 'INCREMENTAL_SYNC', 'MARKET_DATA');
      setProgressTaskType('MARKET_DATA');
      setCurrentTask(task);
    } catch (e) {
      setError(e instanceof Error ? e.message : '一键增量更新失败');
    } finally {
      setUpdateLoading(false);
    }
  };

  const handleSaveMairuiLicence = async () => {
    const value = mairuiLicenceInput.trim();
    if (!value && !mairuiConfig?.configured) {
      setError('请输入有效的 Mairui licence');
      return;
    }

    setError(null);
    setMairuiMessage(null);
    setMairuiSaveLoading(true);
    try {
      const config = await saveMairuiLicence(value, mairuiRateLimitInput, mairuiFetchConcurrencyInput);
      setMairuiConfig(config);
      setMairuiRateLimitInput(config.rate_limit_per_minute);
      setMairuiFetchConcurrencyInput(config.fetch_concurrency);
      setMairuiLicenceInput('');
      setMairuiMessage('麦蕊数据源配置已保存');
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
      setProgressTaskType(task.task_type);
      setCurrentTask(task);
    } catch (e) {
      setError(e instanceof Error ? e.message : '断点继续失败');
    } finally {
      setTaskActionLoading(false);
    }
  };

  const handleRetrySubtask = async () => {
    if (!currentTask) return;
    const label = retryItemLabel.trim();
    if (!label) {
      setError('请先输入或选择要重试的子任务标识');
      return;
    }
    setError(null);
    setTaskActionLoading(true);
    try {
      const task = await retryInitSubtask(currentTask.task_id, label);
      setProgressTaskType(task.task_type);
      setCurrentTask(task);
      setShowDays(false);
      setTaskItems(null);
      setRetryItemLabel('');
    } catch (e) {
      setError(e instanceof Error ? e.message : '子任务重试失败');
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

    const handleStartBatch = async () => {
        setError(null);
        setBatchStartLoading(true);
        setBatchTasks(null);
        batchTaskIdsRef.current = null;
        if (batchPollRef.current) {
            clearInterval(batchPollRef.current);
            batchPollRef.current = null;
        }
        try {
            const result = await createBatchInitTasks(startDate, endDate);
            setBatchTasks(result);
            setProgressTaskType('MARKET_DATA');
            setCurrentTask(result.market_data_task);
            batchTaskIdsRef.current = {
                stock: result.stock_list_task.task_id,
                market: result.market_data_task.task_id,
                jygs: result.jygs_review_task.task_id,
            };
        } catch (e) {
            setError(e instanceof Error ? e.message : '批量任务启动失败');
        } finally {
            setBatchStartLoading(false);
        }
    };

  const handleProgressTaskTypeChange = async (taskType: TaskType) => {
    setProgressTaskType(taskType);
    setShowDays(false);
    setTaskItems(null);
    setRetryItemLabel('');
    setProgressTaskLoading(true);
    try {
      const task = await getLatestInitTaskByType(taskType);
      setCurrentTask(task);
    } catch (e) {
      setError(e instanceof Error ? e.message : '获取最新任务失败');
    } finally {
      setProgressTaskLoading(false);
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
  const isMarketTask = selectedTaskType === 'MARKET_DATA' || selectedTaskType === 'MARKET_DATA_5M' || selectedTaskType === 'STOCK_LIST_SYNC';
  const canStartTask = isMarketTask ? !!initOverview?.market_data_configured : !!jygsStatus?.valid;
  const latestMarketTask = initOverview?.latest_market_data_task ?? null;
  const oneClickStartDate = latestMarketTask ? addOneDayYYYYMMDD(latestMarketTask.end_date) : '';
  const oneClickEndDate = todayYYYYMMDD();

  const progressPercent = currentTask && currentTask.total_items > 0
    ? Math.round(currentTask.progress_percent)
    : 0;


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
            <DatabaseOutlined />
            当前行情数据
          </Space>
        }
      >
        <Row gutter={[24, 16]} align="middle">
          <Col xs={24} lg={16}>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="最近成功同步区间">
                {latestMarketTask ? `${latestMarketTask.start_date} — ${latestMarketTask.end_date}` : '暂无成功同步记录'}
              </Descriptions.Item>
              <Descriptions.Item label="最近同步完成时间">
                {latestMarketTask ? formatIso(latestMarketTask.task_end_date) : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="本地行情任务覆盖">
                {initOverview?.data_range.min_trade_date && initOverview?.data_range.max_trade_date
                  ? `${initOverview.data_range.min_trade_date} — ${initOverview.data_range.max_trade_date}`
                  : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="当前任务状态">
                {currentTask ? (
                  <Tag color={taskStatusColor(currentTask.status)}>{taskStatusLabel(currentTask.status)}</Tag>
                ) : '—'}
              </Descriptions.Item>
            </Descriptions>
          </Col>
          <Col xs={24} lg={8}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Typography.Text strong>一键增量更新</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {latestMarketTask
                  ? oneClickStartDate > oneClickEndDate
                    ? '行情已同步到今天'
                    : `将补齐：${oneClickStartDate} — ${oneClickEndDate}`
                  : '需先完成一次行情同步'}
              </Typography.Text>
              <Button
                type="primary"
                icon={<SyncOutlined />}
                loading={updateLoading}
                disabled={isRunning || !initOverview?.market_data_configured || !latestMarketTask}
                onClick={handleOneClickIncrementalUpdate}
              >
                一键增量更新
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Card className="page-card" bodyStyle={{ padding: 12 }}>
        <Segmented
          block
          value={activeSection}
          onChange={(value) => setActiveSection(value as 'tasks' | 'data-source')}
          options={[
            { label: '初始化任务', value: 'tasks' },
            { label: '数据源配置', value: 'data-source' },
          ]}
        />
      </Card>

      {activeSection === 'data-source' && (
        <>
      <Card
          className="page-card"
          title={
            <Space>
              <DatabaseOutlined/>
              麦蕊数据源配置
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

          <Row gutter={[12, 12]} align="bottom">
            <Col xs={24} lg={12}>
              <Typography.Text type="secondary">Licence</Typography.Text>
              <Input.Password
                  value={mairuiLicenceInput}
                  placeholder="请输入 Mairui licence"
                  onChange={(e) => setMairuiLicenceInput(e.target.value)}
              />
            </Col>
            <Col xs={24} sm={12} lg={5}>
              <Typography.Text type="secondary">请求速率（次/分钟）</Typography.Text>
              <InputNumber
                  min={1}
                  precision={0}
                  value={mairuiRateLimitInput}
                  onChange={(value) => setMairuiRateLimitInput(Number(value || 1))}
                  style={{width: '100%'}}
              />
            </Col>
            <Col xs={24} sm={12} lg={4}>
              <Typography.Text type="secondary">并发拉取数</Typography.Text>
              <InputNumber
                  min={1}
                  precision={0}
                  value={mairuiFetchConcurrencyInput}
                  onChange={(value) => setMairuiFetchConcurrencyInput(Number(value || 1))}
                  style={{width: '100%'}}
              />
            </Col>
            <Col xs={24} lg={3}>
              <Button
                  type="primary"
                  loading={mairuiSaveLoading}
                  onClick={handleSaveMairuiLicence}
                  block
              >
                保存配置
              </Button>
            </Col>
          </Row>

          <Typography.Text type="secondary" style={{fontSize: 12}}>
            保存后将写入后端 JSON 配置文件，并用于后续麦蕊行情接口请求和初始化任务并发拉取。
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
        </>
      )}

      {/* V2 Init task creation */}
      {activeSection === 'tasks' && (
        <>
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
            支持四类任务：股票列表同步、行情数据同步（全量/增量）、5分钟K同步、韭研复盘抓取。
          </Typography.Text>
          <Space wrap>
            <Space direction="vertical" size={4}>
              <Typography.Text>任务类型：</Typography.Text>
              <Select<TaskType>
                value={selectedTaskType}
                onChange={(v) => {
                  setSelectedTaskType(v);
                  if (v !== 'MARKET_DATA') setSelectedMode('FULL_SYNC');
                }}
                disabled={isRunning}
                style={{ width: 220 }}
                options={[
                  {label: '股票列表同步', value: 'STOCK_LIST_SYNC'},
                  {label: '行情数据同步', value: 'MARKET_DATA'},
                  {label: '5分钟K同步', value: 'MARKET_DATA_5M'},
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
                      selectedTaskType === 'MARKET_DATA_5M' ? '同步5分钟K' :
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

        {/* 一键全量初始化 */}
        <Card
            className="page-card"
            title={
                <Space>
                    <SyncOutlined/>
                    一键全量初始化
                </Space>
            }
        >
            <Space direction="vertical" size={12} style={{width: '100%'}}>
                <Typography.Text type="secondary">
                    同时创建三个任务：股票列表同步 → 行情数据同步 + 韭研复盘抓取（并行）。
                    需要 Mairui licence 和韭研公社凭据均已配置。
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
                            allowClear={false}
                        />
                    </Space>
                    <Button
                        type="primary"
                        icon={<SyncOutlined/>}
                        loading={batchStartLoading}
                        disabled={!initOverview?.market_data_configured || !jygsStatus?.valid}
                        onClick={handleStartBatch}
                        style={{marginTop: 20}}
                    >
                        一键全量初始化
                    </Button>
                </Space>
                {(!initOverview?.market_data_configured || !jygsStatus?.valid) && (
                    <Alert
                        type="warning"
                        showIcon
                        message="一键初始化需要 Mairui licence 和韭研公社凭据均已配置。"
                    />
                )}
            </Space>
        </Card>

        {/* 批量任务进度 */}
        {batchTasks && (
            <Card className="page-card" title="批量任务进度">
                <Space direction="vertical" size={16} style={{width: '100%'}}>
                    {([
                        {label: '① 股票列表同步', task: batchTasks.stock_list_task},
                        {label: '② 行情数据同步', task: batchTasks.market_data_task},
                        {label: '③ 韭研复盘抓取', task: batchTasks.jygs_review_task},
                    ] as { label: string; task: TaskResponse }[]).map(({label, task}) => {
                        const pct = task.total_items > 0 ? Math.round(task.progress_percent) : 0;
                        const running = task.status === 'RUNNING';
                        const done = task.status === 'SUCCESS';
                        const failed = task.status === 'FAILED' || task.status === 'TERMINATED';
                        return (
                            <div key={task.task_id}>
                                <Space style={{marginBottom: 6}}>
                                    <Typography.Text strong>{label}</Typography.Text>
                                    <Tag color={taskStatusColor(task.status)}>{taskStatusLabel(task.status)}</Tag>
                                    {task.current_label && (
                                        <Typography.Text type="secondary" style={{fontSize: 12}}>
                                            当前：{task.current_label}
                                        </Typography.Text>
                                    )}
                                </Space>
                                {(running || done) && (
                                    <Progress
                                        percent={pct}
                                        size="small"
                                        status={running ? 'active' : done ? 'success' : 'exception'}
                                        format={(p) =>
                                            task.total_items > 0
                                                ? `${task.processed_items}/${task.total_items} (${p}%)`
                                                : taskStatusLabel(task.status)
                                        }
                                    />
                                )}
                                {failed && task.error_message && (
                                    <Typography.Text type="danger" style={{fontSize: 12}}>
                                        {task.error_message}
                                    </Typography.Text>
                                )}
                                {task.status === 'PENDING' && (
                                    <Progress percent={0} size="small" status="normal" format={() => '等待启动…'}/>
                                )}
                            </div>
                        );
                    })}
                </Space>
            </Card>
        )}

      {/* Task progress */}
      <Card className="page-card" title="任务进度">
        <Space style={{ marginBottom: 16 }}>
          <Typography.Text>任务类型：</Typography.Text>
          <Select<TaskType>
            value={progressTaskType}
            onChange={handleProgressTaskTypeChange}
            loading={progressTaskLoading}
            style={{ width: 160 }}
            options={[
              { label: '行情同步', value: 'MARKET_DATA' },
              { label: '5分钟K', value: 'MARKET_DATA_5M' },
              { label: '热点复盘', value: 'JYGS_REVIEW' },
              { label: '股票列表', value: 'STOCK_LIST_SYNC' },
            ]}
          />
        </Space>
        {progressTaskLoading ? (
          <Typography.Text type="secondary">正在加载最新任务…</Typography.Text>
        ) : !currentTask ? (
          <Typography.Text type="secondary">
            暂无{taskTypeLabel(progressTaskType)}任务记录
          </Typography.Text>
        ) : (
          <>
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
                  title="总项数"
                  value={currentTask.total_items}
                  suffix="项"
              />
            </Col>
            <Col xs={24} md={6}>
              <Statistic
                  title="已处理"
                  value={`${currentTask.processed_items} / ${currentTask.total_items}`}
                  suffix="项"
              />
            </Col>
            <Col xs={24} md={6}>
              <Statistic
                title="当前处理"
                value={currentTask.current_label || '—'}
              />
            </Col>
          </Row>

          {(isRunning || isDone) && (
            <div style={{ marginTop: 16 }}>
              <Progress
                percent={progressPercent}
                status={isRunning ? 'active' : isDone ? 'success' : 'exception'}
                format={(pct) =>
                    `${currentTask.processed_items} / ${currentTask.total_items} (${pct}%)`
                }
              />
            </div>
          )}

          <Descriptions style={{ marginTop: 16 }} column={2} size="small">
            <Descriptions.Item label="任务 ID">{currentTask.task_id}</Descriptions.Item>
            <Descriptions.Item label="任务类型">{taskTypeLabel(currentTask.task_type)}</Descriptions.Item>
            <Descriptions.Item label="日期区间">
              {currentTask.start_date} — {currentTask.end_date}
            </Descriptions.Item>
            <Descriptions.Item label="开始时间">{formatIso(currentTask.task_start_date)}</Descriptions.Item>
            {(isDone || isFailed || isTerminated) && (
                <Descriptions.Item label="完成时间">{formatIso(currentTask.task_end_date)}</Descriptions.Item>
            )}
            {(isFailed || isTerminated) && (
              <Descriptions.Item label="错误信息" span={2}>
                <Typography.Text type="danger">{currentTask.error_message}</Typography.Text>
              </Descriptions.Item>
            )}
          </Descriptions>

          <Space style={{marginTop: 12}}>
            <Button size="small" loading={itemsLoading} onClick={handleToggleDays}>
              {showDays ? '收起子任务明细' : '查看子任务明细'}
            </Button>
            {(isFailed || isTerminated) && (
                <Button size="small" type="primary" loading={taskActionLoading} onClick={handleRetryTask}>
                  断点继续
                </Button>
            )}
            {(isRunning || isFailed) && (
                <Button size="small" danger loading={taskActionLoading} onClick={handleTerminateTask}>
                  终止任务
                </Button>
            )}
          </Space>

          {showDays && taskItems && (
              <div style={{marginTop: 16}}>
                <Descriptions
                    title="子任务明细"
                    bordered
                    size="small"
                    column={2}
                >
                  <Descriptions.Item label="处理单元类型">
                    {taskItems.label_name}
                  </Descriptions.Item>
                  <Descriptions.Item label="整体进度">
                    {taskItems.processed_items} / {taskItems.total_items} 项
                    （{taskItems.progress_percent}%）
                  </Descriptions.Item>
                  <Descriptions.Item label="当前处理" span={2}>
                    {taskItems.current_label
                        ? <Tag color="processing">{taskItems.current_label}</Tag>
                        : <Typography.Text type="secondary">—</Typography.Text>
                    }
                  </Descriptions.Item>
                  <Descriptions.Item label="已完成">
                    <Tag color="success">{taskItems.processed_items} 项</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="待处理">
                    <Tag color="default">
                      {Math.max(0, taskItems.total_items - taskItems.processed_items)} 项
                    </Tag>
                  </Descriptions.Item>
                  {taskItems.error_message && (
                      <Descriptions.Item label="错误信息" span={2}>
                        <Typography.Text type="danger" style={{fontSize: 12}}>
                          {taskItems.error_message}
                        </Typography.Text>
                      </Descriptions.Item>
                  )}
                </Descriptions>

                <Space style={{marginTop: 12}}>
                  <Input
                      placeholder={
                        taskItems.label_type === 'stock'
                            ? '输入股票代码，如 000001 或 000001.SZ'
                            : taskItems.label_type === 'date'
                                ? '输入交易日，如 20240518'
                                : '输入子任务标识'
                      }
                      value={retryItemLabel}
                      onChange={(e) => setRetryItemLabel(e.target.value)}
                      style={{width: 320}}
                  />
                  <Button
                      size="small"
                      type="primary"
                      loading={taskActionLoading}
                      disabled={isRunning}
                      onClick={handleRetrySubtask}
                  >
                    重试子任务
                  </Button>
                </Space>
              </div>
          )}

          {showDays && !taskItems && !itemsLoading && (
              <Typography.Text type="secondary" style={{marginTop: 12, display: 'block'}}>
                暂无子任务数据
              </Typography.Text>
          )}
          </>
        )}
      </Card>

        </>
      )}
    </Space>
  );
}
