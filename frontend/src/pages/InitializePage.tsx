import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Input,
  Progress,
  Row,
  Space,
  Statistic,
  Tag,
  Typography,
  Upload,
} from 'antd';
import type { CheckboxOptionType } from 'antd/es/checkbox';
import type { UploadFile } from 'antd/es/upload';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  LockOutlined,
  SyncOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import {
  type InitStatusResponse,
  type MarketBoard,
  type StockListUploadResponse,
  type TokenConfigResponse,
  type UpdateResult,
  ALL_MARKET_BOARDS,
  getInitStatus,
  getTokenConfig,
  saveTokenConfig,
  startInit,
  triggerDailyUpdate,
  uploadStockList,
} from '../lib/api';

const POLL_INTERVAL_MS = 3000;

const MARKET_BOARD_OPTIONS: CheckboxOptionType[] = ALL_MARKET_BOARDS.map((b) => ({
  label: b,
  value: b,
}));

function formatIso(iso: string): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
  } catch {
    return iso;
  }
}

function statusColor(status: string): string {
  switch (status) {
    case 'running':
      return '#1677ff';
    case 'done':
      return '#52c41a';
    case 'error':
      return '#ff4d4f';
    default:
      return '#8c8c8c';
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'running':
      return '初始化中';
    case 'done':
      return '已完成';
    case 'error':
      return '出错';
    default:
      return '待初始化';
  }
}

export function InitializePage() {
  const [initStatus, setInitStatus] = useState<InitStatusResponse | null>(null);
  const [marketFilters, setMarketFilters] = useState<MarketBoard[]>([...ALL_MARKET_BOARDS]);
  const [startLoading, setStartLoading] = useState(false);
  const [updateLoading, setUpdateLoading] = useState(false);
  const [updateResult, setUpdateResult] = useState<UpdateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Token config state
  const [tokenConfig, setTokenConfig] = useState<TokenConfigResponse | null>(null);
  const [tokenInput, setTokenInput] = useState('');
  const [tokenSaving, setTokenSaving] = useState(false);
  const [tokenSuccess, setTokenSuccess] = useState(false);

  // Stock list upload state
  const [uploadFileList, setUploadFileList] = useState<UploadFile[]>([]);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState<StockListUploadResponse | null>(null);

  const fetchStatus = async () => {
    try {
      const s = await getInitStatus();
      setInitStatus(s);
    } catch {
      // silently ignore poll errors
    }
  };

  const fetchTokenConfig = async () => {
    try {
      const t = await getTokenConfig();
      setTokenConfig(t);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchTokenConfig();
  }, []);

  // Start polling when running
  useEffect(() => {
    if (initStatus?.status === 'running') {
      if (!pollRef.current) {
        pollRef.current = setInterval(fetchStatus, POLL_INTERVAL_MS);
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
  }, [initStatus?.status]);

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
    try {
      const s = await startInit(60, marketFilters);
      setInitStatus(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : '启动初始化失败');
    } finally {
      setStartLoading(false);
    }
  };

  const handleDailyUpdate = async () => {
    setError(null);
    setUpdateLoading(true);
    setUpdateResult(null);
    try {
      const result = await triggerDailyUpdate();
      setUpdateResult(result);
      await fetchStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : '增量更新失败');
    } finally {
      setUpdateLoading(false);
    }
  };

  const progressPercent =
    initStatus && initStatus.total_stocks > 0
      ? Math.round((initStatus.processed_stocks / initStatus.total_stocks) * 100)
      : 0;

  const isRunning = initStatus?.status === 'running';
  const isDone = initStatus?.status === 'done';
  const isError = initStatus?.status === 'error';

  return (
    <Space direction="vertical" size={24} style={{ display: 'flex' }}>
      <Space direction="vertical" size={4}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          市场数据初始化
        </Typography.Title>
        <Typography.Text type="secondary">
          通过 Tushare 接入全市场 A 股数据，支持全量初始化与当日增量更新。
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
          message={`增量更新完成：交易日 ${updateResult.trade_date}，更新 ${updateResult.stock_count} 支股票，${updateResult.bar_count} 条行情记录`}
          onClose={() => setUpdateResult(null)}
        />
      )}

      {/* Token configuration card */}
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
              <Tag color="success" icon={<CheckCircleOutlined />}>
                已配置
              </Tag>
            ) : (
              <Tag color="warning" icon={<CloseCircleOutlined />}>
                未配置
              </Tag>
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
            {tokenSuccess && (
              <Typography.Text type="success">Token 已保存</Typography.Text>
            )}
          </Space>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Token 保存在服务端，不会在页面上显示。也可以通过环境变量 TUSHARE_TOKEN 配置。
          </Typography.Text>
        </Space>
      </Card>

      {/* Stock list upload card */}
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
                    <Tag key={board} color="blue">
                      {board}: {count}
                    </Tag>
                  ))}
                </Space>
              }
            />
          )}
        </Space>
      </Card>

      {/* Status card */}
      <Card className="page-card" title="初始化状态">
        <Row gutter={[16, 16]}>
          <Col xs={24} md={8}>
            <Statistic
              title="当前状态"
              value={statusLabel(initStatus?.status ?? 'idle')}
              valueStyle={{ color: statusColor(initStatus?.status ?? 'idle') }}
              prefix={
                isRunning ? (
                  <SyncOutlined spin />
                ) : isDone ? (
                  <CheckCircleOutlined />
                ) : isError ? (
                  <CloseCircleOutlined />
                ) : (
                  <DatabaseOutlined />
                )
              }
            />
          </Col>
          <Col xs={24} md={8}>
            <Statistic
              title="股票总数"
              value={initStatus?.total_stocks ?? 0}
              suffix="支"
            />
          </Col>
          <Col xs={24} md={8}>
            <Statistic
              title="最近交易日"
              value={initStatus?.trade_date || '—'}
            />
          </Col>
        </Row>

        {(isRunning || isDone) && initStatus && initStatus.total_stocks > 0 && (
          <div style={{ marginTop: 16 }}>
            <Progress
              percent={progressPercent}
              status={isRunning ? 'active' : isDone ? 'success' : 'exception'}
              format={(pct) =>
                `${initStatus.processed_stocks} / ${initStatus.total_stocks} (${pct}%)`
              }
            />
          </div>
        )}

        {initStatus && (
          <Descriptions style={{ marginTop: 16 }} column={2} size="small">
            <Descriptions.Item label="开始时间">
              {formatIso(initStatus.started_at)}
            </Descriptions.Item>
            <Descriptions.Item label="完成时间">
              {formatIso(initStatus.finished_at)}
            </Descriptions.Item>
            {isError && (
              <Descriptions.Item label="错误信息" span={2}>
                <Typography.Text type="danger">{initStatus.error_message}</Typography.Text>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Card>

      {/* Actions card */}
      <Card className="page-card" title="操作">
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Space direction="vertical" size={4}>
            <span>市场板块筛选：</span>
            <Checkbox.Group
              options={MARKET_BOARD_OPTIONS}
              value={marketFilters}
              onChange={(vals) => setMarketFilters(vals as MarketBoard[])}
              disabled={isRunning}
            />
          </Space>

          <Space wrap>
            <Button
              type="primary"
              icon={<DatabaseOutlined />}
              loading={startLoading}
              disabled={isRunning || marketFilters.length === 0}
              onClick={handleStartInit}
            >
              {isRunning ? '初始化中…' : '开始全量初始化'}
            </Button>
            <Button
              icon={<SyncOutlined />}
              loading={updateLoading}
              disabled={isRunning}
              onClick={handleDailyUpdate}
            >
              当日增量更新
            </Button>
          </Space>
        </Space>
      </Card>

      {/* Explanation card */}
      <Card className="page-card" title="说明">
        <Typography.Paragraph>
          <strong>全量初始化</strong>：从 Tushare 拉取全市场 A 股当日快照与历史 K 线（自 2024-01-01 起），导入本地数据库。
          受限于网络与 API 速率（最多 450 次/分钟），全量初始化通常需要数分钟到数十分钟，请耐心等待。
        </Typography.Paragraph>
        <Typography.Paragraph>
          <strong>市场板块筛选</strong>：只对选中板块的股票执行逐股行情拉取，可缩短初始化时间。
        </Typography.Paragraph>
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          <strong>当日增量更新</strong>：仅拉取今日行情并刷新数据库，适合每个交易日收盘后执行，耗时较短。
        </Typography.Paragraph>
      </Card>
    </Space>
  );
}
