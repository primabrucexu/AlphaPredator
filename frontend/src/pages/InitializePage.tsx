import {useEffect, useRef, useState} from 'react';
import {useSearchParams} from 'react-router-dom';
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
  Tooltip,
  Typography,
} from 'antd';
import dayjs from 'dayjs';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DisconnectOutlined,
  LinkOutlined,
  LockOutlined,
  SyncOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import {
  clearJygsSession,
  createInitTask,
  getInitTask,
  getInitTaskDays,
  getInitV2Overview,
  getJygsAuthStatus,
  getTokenConfig,
  type InitV2OverviewResponse,
  type JygsAuthStatus,
  retryInitTask,
  saveJygsSession,
  saveTokenConfig,
  type StockListUploadResponse,
  type TaskDayItem,
  type TaskResponse,
  type TaskType,
  terminateInitTask,
  type TokenConfigResponse,
  triggerDailyUpdate,
  type UpdateResult,
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
  return taskType === 'JYGS_REVIEW' ? '韭研复盘抓取' : '行情初始化';
}

export function InitializePage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Token
  const [tokenConfig, setTokenConfig] = useState<TokenConfigResponse | null>(null);
  const [tokenInput, setTokenInput] = useState('');
  const [tokenSaving, setTokenSaving] = useState(false);
  const [tokenSuccess, setTokenSuccess] = useState(false);

  // JYGS auth
  const [jygsStatus, setJygsStatus] = useState<JygsAuthStatus | null>(null);
  const [jygsConnecting, setJygsConnecting] = useState(false);
  const [jygsError, setJygsError] = useState<string | null>(null);
  const [jygsManualSession, setJygsManualSession] = useState('');
  const [jygsManualSaving, setJygsManualSaving] = useState(false);
  const [showManualFallback, setShowManualFallback] = useState(false);
  const jygsPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const jygsPopupRef = useRef<Window | null>(null);

  // Stock list
  const [initOverview, setInitOverview] = useState<InitV2OverviewResponse | null>(null);
  const [stockListFile, setStockListFile] = useState<File | null>(null);
  const [stockListUploading, setStockListUploading] = useState(false);
  const [stockListResult, setStockListResult] = useState<StockListUploadResponse | null>(null);
  const stockListInputRef = useRef<HTMLInputElement | null>(null);

  // Task
  const [startDate, setStartDate] = useState<string>(DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState<string>(todayYYYYMMDD());
  const [startLoading, setStartLoading] = useState(false);
  const [currentTask, setCurrentTask] = useState<TaskResponse | null>(null);
  const [selectedTaskType, setSelectedTaskType] = useState<TaskType>('MARKET_DATA');
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
    Promise.all([getTokenConfig(), getInitV2Overview(), getJygsAuthStatus()])
      .then(([token, overview, jygs]) => {
        setTokenConfig(token);
        setInitOverview(overview);
        setCurrentTask(overview.running_task ?? overview.latest_task ?? null);
        setJygsStatus(jygs);
      })
      .catch(() => {});

    // 代理登录成功后会跳转回 /initialize?jygs_login=success
    if (searchParams.get('jygs_login') === 'success') {
      setSearchParams({}, { replace: true });
      getJygsAuthStatus().then(setJygsStatus).catch(() => {});
    }
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

  const handleStartInit = async () => {
    setError(null);
    setStartLoading(true);
    setCurrentTask(null);
    setShowDays(false);
    try {
      const task = await createInitTask(startDate, endDate, 'RANGE', selectedTaskType);
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

  const handleUploadStockList = async () => {
    if (!stockListFile) return;
    setError(null);
    setStockListUploading(true);
    try {
      const result = await uploadStockList(stockListFile);
      setStockListResult(result);
      setStockListFile(null);
      if (stockListInputRef.current) {
        stockListInputRef.current.value = '';
      }
      const overview = await getInitV2Overview();
      setInitOverview(overview);
    } catch (e) {
      setError(e instanceof Error ? e.message : '上传股票清单失败');
    } finally {
      setStockListUploading(false);
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

  const stopJygsPoll = () => {
    if (jygsPollRef.current) {
      clearInterval(jygsPollRef.current);
      jygsPollRef.current = null;
    }
  };

  const handleJygsConnect = () => {
    setJygsError(null);
    setJygsConnecting(true);
    setShowManualFallback(false);

    // 弹出代理登录窗口
    const proxyUrl = `${window.location.origin}/api/jygs/proxy/`;
    jygsPopupRef.current = window.open(proxyUrl, 'jygs-login', 'width=520,height=860,left=200,top=80');

    // 每 2 秒轮询鉴权状态
    jygsPollRef.current = setInterval(async () => {
      try {
        const status = await getJygsAuthStatus();
        if (status.valid) {
          setJygsStatus(status);
          setJygsConnecting(false);
          stopJygsPoll();
          jygsPopupRef.current?.close();
          jygsPopupRef.current = null;
        }
        // 若弹窗被用户手动关闭，停止轮询
        if (jygsPopupRef.current?.closed) {
          stopJygsPoll();
          setJygsConnecting(false);
          // 再检查一次，弹窗可能是被代理成功后转到 initialize?success 触发的关闭
          const finalStatus = await getJygsAuthStatus();
          setJygsStatus(finalStatus);
          if (!finalStatus.valid) {
            setShowManualFallback(true);
            setJygsError('代理登录未能捕获到凭据，请使用下方手动方式。');
          }
        }
      } catch {
        // ignore network errors during polling
      }
    }, 2000);
  };

  const handleJygsManualSave = async () => {
    if (!jygsManualSession.trim()) return;
    setJygsManualSaving(true);
    setJygsError(null);
    try {
      await saveJygsSession(jygsManualSession.trim());
      const status = await getJygsAuthStatus();
      setJygsStatus(status);
      setJygsManualSession('');
      setShowManualFallback(false);
    } catch (e) {
      setJygsError(e instanceof Error ? e.message : '保存失败');
    } finally {
      setJygsManualSaving(false);
    }
  };

  const handleJygsDisconnect = async () => {
    await clearJygsSession();
    setJygsStatus({ configured: false, valid: false, saved_at: null, expires_at: null });
  };

  const jygsConsoleSnippet =
    `fetch("${window.location.origin}/api/jygs/auth/session",` +
    `{method:"POST",headers:{"Content-Type":"application/json"},` +
    `body:JSON.stringify({session:document.cookie.split(";")` +
    `.find(c=>c.trim().startsWith("SESSION=")).trim().split("=")[1]})})` +
    `.then(r=>r.json()).then(d=>alert(d.ok?"✅ 已同步到 AlphaPredator！":"❌ "+d.error))`;

  const isRunning = currentTask?.status === 'RUNNING';
  const isDone = currentTask?.status === 'SUCCESS';
  const isFailed = currentTask?.status === 'FAILED';
  const isTerminated = currentTask?.status === 'TERMINATED';
  const isMarketTask = selectedTaskType === 'MARKET_DATA';
  const canStartTask = isMarketTask ? !!tokenConfig?.is_configured : !!jygsStatus?.valid;

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
          通过 Tushare 接入全市场 A 股历史日线数据，支持按日期区间全量初始化。
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

      {stockListResult && (
        <Alert
          type="success"
          showIcon
          closable
          message={`股票清单上传成功：共 ${stockListResult.total_stocks} 条，上市 ${stockListResult.active_stocks} 条`}
          onClose={() => setStockListResult(null)}
        />
      )}

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
            <Space wrap>
              <Button
                type="primary"
                icon={jygsConnecting ? <SyncOutlined spin /> : <LinkOutlined />}
                loading={jygsConnecting}
                onClick={handleJygsConnect}
              >
                {jygsConnecting ? '等待登录中…' : '一键代理登录'}
              </Button>
              {jygsConnecting && (
                <Typography.Text type="secondary">
                  请在弹出的窗口中完成登录，登录后将自动关闭
                </Typography.Text>
              )}
              <Button
                type="link"
                size="small"
                onClick={() => setShowManualFallback(v => !v)}
              >
                {showManualFallback ? '收起手动方式' : '代理登录失败？使用手动方式'}
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

          {/* 手动 SESSION 回退方式 */}
          {showManualFallback && (
            <Card size="small" style={{ background: '#fafafa' }}>
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <Typography.Text strong>手动方式（控制台）</Typography.Text>
                <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13 }}>
                  <li>
                    <Typography.Link href="https://www.jiuyangongshe.com" target="_blank">
                      点此打开韭研公社
                    </Typography.Link>
                    ，完成登录
                  </li>
                  <li>按 <Typography.Text code>F12</Typography.Text> 打开开发者工具 → 切到 <Typography.Text code>Console</Typography.Text> 标签</li>
                  <li>复制下方代码并粘贴到控制台后回车</li>
                </ol>
                <Space.Compact style={{ width: '100%' }}>
                  <Input
                    value={jygsConsoleSnippet}
                    readOnly
                    style={{ fontFamily: 'monospace', fontSize: 11 }}
                  />
                  <Tooltip title="复制">
                    <Button
                      icon={<CopyOutlined />}
                      onClick={() => navigator.clipboard.writeText(jygsConsoleSnippet)}
                    />
                  </Tooltip>
                </Space.Compact>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  执行后弹出"✅ 已同步"即表示成功，本页将自动刷新连接状态。
                </Typography.Text>

                <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
                  或直接粘贴 SESSION Cookie 的值：
                </Typography.Text>
                <Space.Compact style={{ width: '100%' }}>
                  <Input.Password
                    placeholder="粘贴 SESSION Cookie 值"
                    value={jygsManualSession}
                    onChange={e => setJygsManualSession(e.target.value)}
                    onPressEnter={handleJygsManualSave}
                  />
                  <Button
                    type="primary"
                    loading={jygsManualSaving}
                    disabled={!jygsManualSession.trim()}
                    onClick={handleJygsManualSave}
                  >
                    验证并保存
                  </Button>
                </Space.Compact>
              </Space>
            </Card>
          )}
        </Space>
      </Card>

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
            股票清单上传
          </Space>
        }
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space>
            <Typography.Text>当前状态：</Typography.Text>
            {initOverview === null ? (
              <Tag>检查中…</Tag>
            ) : initOverview.stock_list_uploaded ? (
              <Tag color="success" icon={<CheckCircleOutlined />}>已上传</Tag>
            ) : (
              <Tag color="warning" icon={<CloseCircleOutlined />}>未上传</Tag>
            )}
          </Space>

          {initOverview?.stock_list_updated_at && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              最近上传：{formatIso(initOverview.stock_list_updated_at)}
            </Typography.Text>
          )}

          <Space wrap>
            <input
              ref={stockListInputRef}
              type="file"
              accept=".csv"
              onChange={(e) => setStockListFile(e.target.files?.[0] ?? null)}
            />
            <Button
              type="primary"
              icon={<UploadOutlined />}
              loading={stockListUploading}
              disabled={!stockListFile}
              onClick={handleUploadStockList}
            >
              上传股票清单
            </Button>
            {stockListFile && (
              <Typography.Text type="secondary">已选择：{stockListFile.name}</Typography.Text>
            )}
          </Space>

          {!!initOverview && Object.keys(initOverview.board_counts).length > 0 && (
            <Space wrap>
              {Object.entries(initOverview.board_counts).map(([board, count]) => (
                <Tag key={board}>{board}：{count}</Tag>
              ))}
            </Space>
          )}

          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            支持上传 Tushare 股票清单，用于首页搜索、代码解析与板块统计。
          </Typography.Text>
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
            支持两类任务：行情全量初始化（Tushare）和韭研复盘抓取（JYGS）。
          </Typography.Text>
          <Space wrap>
            <Space direction="vertical" size={4}>
              <Typography.Text>任务类型：</Typography.Text>
              <Select<TaskType>
                value={selectedTaskType}
                onChange={setSelectedTaskType}
                disabled={isRunning}
                style={{ width: 220 }}
                options={[
                  { label: '行情全量初始化', value: 'MARKET_DATA' },
                  { label: '韭研复盘抓取', value: 'JYGS_REVIEW' },
                ]}
              />
            </Space>
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
              disabled={isRunning || !canStartTask}
              onClick={handleStartInit}
              style={{ marginTop: 20 }}
            >
              {isRunning ? '任务运行中…' : `开始${selectedTaskType === 'JYGS_REVIEW' ? '韭研复盘抓取' : '全量初始化'}`}
            </Button>
          </Space>
          {!canStartTask && (
            <Alert
              type="warning"
              showIcon
              message={
                selectedTaskType === 'JYGS_REVIEW'
                  ? '请先完成韭研公社连接，再启动复盘抓取任务。'
                  : '请先配置 Tushare Token，再启动行情初始化任务。'
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
