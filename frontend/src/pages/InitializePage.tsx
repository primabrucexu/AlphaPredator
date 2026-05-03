import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  InputNumber,
  Progress,
  Row,
  Space,
  Statistic,
  Typography,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import {
  type InitStatusResponse,
  type UpdateResult,
  getInitStatus,
  startInit,
  triggerDailyUpdate,
} from '../lib/api';

const POLL_INTERVAL_MS = 3000;

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
  const [historyDays, setHistoryDays] = useState<number>(60);
  const [startLoading, setStartLoading] = useState(false);
  const [updateLoading, setUpdateLoading] = useState(false);
  const [updateResult, setUpdateResult] = useState<UpdateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = async () => {
    try {
      const s = await getInitStatus();
      setInitStatus(s);
    } catch (e) {
      // silently ignore poll errors
    }
  };

  useEffect(() => {
    fetchStatus();
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

  const handleStartInit = async () => {
    setError(null);
    setStartLoading(true);
    try {
      const s = await startInit(historyDays);
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
          从东方财富接入全市场 A 股数据，支持全量初始化与当日增量更新。
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
          <Space wrap>
            <span>历史行情天数：</span>
            <InputNumber
              min={1}
              max={365}
              value={historyDays}
              onChange={(v) => setHistoryDays(v ?? 60)}
              disabled={isRunning}
            />
            <Button
              type="primary"
              icon={<DatabaseOutlined />}
              loading={startLoading}
              disabled={isRunning}
              onClick={handleStartInit}
            >
              {isRunning ? '初始化中…' : '开始全量初始化'}
            </Button>
          </Space>

          <Space>
            <Button
              icon={<SyncOutlined />}
              loading={updateLoading}
              disabled={isRunning}
              onClick={handleDailyUpdate}
            >
              当日增量更新
            </Button>
            <Typography.Text type="secondary">
              更新今日行情数据（适用于已完成全量初始化后的每日刷新）
            </Typography.Text>
          </Space>
        </Space>
      </Card>

      {/* Explanation card */}
      <Card className="page-card" title="说明">
        <Typography.Paragraph>
          <strong>全量初始化</strong>：从东方财富拉取全市场 A 股当日快照与历史 K 线，导入本地数据库。
          受限于网络与 API 速率，全量初始化通常需要数分钟到数十分钟，请耐心等待。
        </Typography.Paragraph>
        <Typography.Paragraph>
          <strong>历史行情天数</strong>：初始化时拉取的历史行情覆盖天数（日历天）。
          数值越大，耗时越长；建议首次初始化使用 60 天。
        </Typography.Paragraph>
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          <strong>当日增量更新</strong>：仅拉取今日行情并刷新数据库，适合每个交易日收盘后执行，耗时较短。
        </Typography.Paragraph>
      </Card>
    </Space>
  );
}
