import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import { Alert, Card, Col, Empty, List, Row, Space, Spin, Statistic, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { Link } from 'react-router-dom';
import { getMarketOverview, type MarketListRow } from '../lib/api';

function extractTrendDays(label: string): number {
  const match = label.match(/(\d+)/);
  return match ? Number(match[1]) : 1;
}

const marketColumns: ColumnsType<MarketListRow> = [
  {
    title: '股票',
    render: (_, row) => <Link to={`/stocks/${row.stock_code}`}>{row.stock_name}</Link>,
  },
  { title: '代码', dataIndex: 'stock_code' },
  { title: '当前价格', dataIndex: 'current_price', render: (value: number) => value.toFixed(2) },
  {
    title: '今日涨跌幅',
    dataIndex: 'change_pct',
    render: (value: number) => <span style={{ color: value >= 0 ? '#cf1322' : '#1677ff' }}>{value.toFixed(2)}%</span>,
  },
  {
    title: '成交额(亿)',
    dataIndex: 'turnover_amount_billion',
    render: (value: number) => value.toFixed(2),
  },
  { title: '换手率', dataIndex: 'turnover_rate', render: (value: number) => `${value.toFixed(2)}%` },
];

export function MarketOverviewPage() {
  const { data, error, isLoading } = useQuery({
    queryKey: ['market-overview'],
    queryFn: getMarketOverview,
  });

  if (isLoading) {
    return (
      <Space direction="vertical" size={24} style={{ display: 'flex' }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          市场总览
        </Typography.Title>
        <Card className="page-card">
          <Space align="center" size={12}>
            <Spin />
            <Typography.Text>正在加载市场总览数据...</Typography.Text>
          </Space>
        </Card>
      </Space>
    );
  }

  if (error) {
    return (
      <Space direction="vertical" size={24} style={{ display: 'flex' }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          市场总览
        </Typography.Title>
        <Alert
          type="error"
          showIcon
          message="加载市场总览失败"
          description={error instanceof Error ? error.message : '请检查后端服务是否已启动。'}
        />
      </Space>
    );
  }

  if (!data) {
    return (
      <Space direction="vertical" size={24} style={{ display: 'flex' }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          市场总览
        </Typography.Title>
        <Card className="page-card">
          <Empty description="暂无市场总览数据" />
        </Card>
      </Space>
    );
  }

  const hotSectorOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['热度', '持续天数'] },
    xAxis: { type: 'category', data: data.hot_sectors.map((sector) => sector.name) },
    yAxis: [{ type: 'value' }, { type: 'value' }],
    series: [
      { name: '热度', type: 'bar', data: data.hot_sectors.map((sector) => sector.heat_score) },
      {
        name: '持续天数',
        type: 'line',
        yAxisIndex: 1,
        data: data.hot_sectors.map((sector) => extractTrendDays(sector.trend_label)),
      },
    ],
  };

  return (
    <Space direction="vertical" size={24} style={{ display: 'flex' }}>
      <Space direction="vertical" size={4}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          市场总览
        </Typography.Title>
        <Typography.Text type="secondary">数据日期：{data.summary.trade_date}</Typography.Text>
      </Space>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card className="page-card metric-card">
            <Statistic title="上涨家数" value={data.summary.rising_count} valueStyle={{ color: '#cf1322' }} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card className="page-card metric-card">
            <Statistic title="下跌家数" value={data.summary.falling_count} valueStyle={{ color: '#1677ff' }} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card className="page-card metric-card">
            <Statistic title="成交额(亿)" value={data.summary.turnover_amount_billion} suffix="亿" />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={15}>
          <Card className="page-card chart-card" title="当日热点板块">
            {data.hot_sectors.length > 0 ? (
              <ReactECharts option={hotSectorOption} style={{ height: 320 }} />
            ) : (
              <Empty description="暂无热点板块数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={9}>
          <Card className="page-card" title="热点板块概览">
            {data.hot_sectors.length > 0 ? (
              <List
                dataSource={data.hot_sectors}
                renderItem={(item) => (
                  <List.Item>
                    <Space>
                      <Typography.Text strong>{item.name}</Typography.Text>
                      <Tag color="processing">{item.trend_label}</Tag>
                      <Typography.Text type="secondary">热度 {item.heat_score}</Typography.Text>
                    </Space>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无热点板块概览" />
            )}
          </Card>
        </Col>
      </Row>

      <Card className="page-card" title="市场股票列表">
        <Table rowKey="stock_code" pagination={false} columns={marketColumns} dataSource={data.stocks} />
      </Card>
    </Space>
  );
}
