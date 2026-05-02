import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import { Alert, Card, Col, Descriptions, Empty, Row, Space, Spin, Statistic, Tag, Typography } from 'antd';
import { useParams } from 'react-router-dom';
import { getStockDetail, type DailyBar } from '../lib/api';

function buildDailyKLineOption(dailyBars: DailyBar[]) {
  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
    },
    xAxis: {
      type: 'category',
      data: dailyBars.map((dailyBar) => dailyBar.trade_date),
    },
    yAxis: {
      scale: true,
      type: 'value',
    },
    series: [
      {
        type: 'candlestick',
        data: dailyBars.map((dailyBar) => [
          dailyBar.open_price,
          dailyBar.close_price,
          dailyBar.low_price,
          dailyBar.high_price,
        ]),
        itemStyle: {
          color: '#cf1322',
          color0: '#1677ff',
          borderColor: '#cf1322',
          borderColor0: '#1677ff',
        },
      },
    ],
  };
}

export function StockDetailPage() {
  const { stockCode } = useParams();

  const { data, error, isLoading } = useQuery({
    queryKey: ['stock-detail', stockCode],
    queryFn: () => getStockDetail(stockCode as string),
    enabled: Boolean(stockCode),
  });

  if (!stockCode) {
    return <Alert type="error" showIcon message="缺少股票代码参数" />;
  }

  if (isLoading) {
    return (
      <Space direction="vertical" size={24} style={{ display: 'flex' }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          股票详情 · {stockCode}
        </Typography.Title>
        <Card className="page-card">
          <Space align="center" size={12}>
            <Spin />
            <Typography.Text>正在加载股票详情...</Typography.Text>
          </Space>
        </Card>
      </Space>
    );
  }

  if (error) {
    return (
      <Space direction="vertical" size={24} style={{ display: 'flex' }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          股票详情 · {stockCode}
        </Typography.Title>
        <Alert
          type="error"
          showIcon
          message="加载股票详情失败"
          description={error instanceof Error ? error.message : '请检查后端服务是否已启动。'}
        />
      </Space>
    );
  }

  if (!data) {
    return (
      <Space direction="vertical" size={24} style={{ display: 'flex' }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          股票详情 · {stockCode}
        </Typography.Title>
        <Card className="page-card">
          <Empty description="暂无股票详情数据" />
        </Card>
      </Space>
    );
  }

  const dailyKLineOption = buildDailyKLineOption(data.daily_bars);

  return (
    <Space direction="vertical" size={24} style={{ display: 'flex' }}>
      <div>
        <Typography.Title level={2} style={{ marginBottom: 8 }}>
          {data.stock_name} · {data.stock_code}
        </Typography.Title>
        <Space direction="vertical" size={8} style={{ display: 'flex' }}>
          <Space wrap>
            {data.sectors.map((sector) => (
              <Tag key={sector} color="blue">
                {sector}
              </Tag>
            ))}
          </Space>
          <Typography.Text type="secondary">数据日期：{data.trade_date}</Typography.Text>
        </Space>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12} xl={6}>
          <Card className="page-card metric-card">
            <Statistic title="当前价格" value={data.current_price} precision={2} />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="page-card metric-card">
            <Statistic
              title="今日涨跌"
              value={data.change_amount}
              precision={2}
              valueStyle={{ color: data.change_amount >= 0 ? '#cf1322' : '#1677ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="page-card metric-card">
            <Statistic
              title="今日涨跌幅"
              value={data.change_pct}
              precision={2}
              suffix="%"
              valueStyle={{ color: data.change_pct >= 0 ? '#cf1322' : '#1677ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="page-card metric-card">
            <Statistic title="换手率" value={data.turnover_rate} precision={2} suffix="%" />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card className="page-card metric-card">
            <Statistic title="成交额(亿)" value={data.turnover_amount_billion} precision={2} suffix="亿" />
          </Card>
        </Col>
      </Row>

      <Card className="page-card" title="基础指标">
        <Descriptions column={{ xs: 1, md: 2, xl: 4 }} bordered>
          <Descriptions.Item label="MA5">
            {data.key_indicators.ma5 !== null ? data.key_indicators.ma5.toFixed(2) : '--'}
          </Descriptions.Item>
          <Descriptions.Item label="MA10">
            {data.key_indicators.ma10 !== null ? data.key_indicators.ma10.toFixed(2) : '--'}
          </Descriptions.Item>
          <Descriptions.Item label="MA20">
            {data.key_indicators.ma20 !== null ? data.key_indicators.ma20.toFixed(2) : '--'}
          </Descriptions.Item>
          <Descriptions.Item label="近 5 日均量">
            {data.key_indicators.avg_volume_5d !== null ? data.key_indicators.avg_volume_5d.toLocaleString() : '--'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card className="page-card" title="日 K">
        {data.daily_bars.length > 0 ? (
          <ReactECharts option={dailyKLineOption} style={{ height: 360 }} />
        ) : (
          <Empty description="暂无日 K 数据" />
        )}
      </Card>

      <Card className="page-card" title="AI 快速结论">
        <Descriptions column={1} bordered>
          <Descriptions.Item label="简短结论">{data.ai_quick_summary}</Descriptions.Item>
        </Descriptions>
      </Card>
    </Space>
  );
}
