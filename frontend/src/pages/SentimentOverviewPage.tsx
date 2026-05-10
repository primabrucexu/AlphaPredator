import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import { Alert, Card, Empty, Space, Spin, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { Link } from 'react-router-dom';
import { getHotSectorHistory, getLimitUpStreaks, type LimitUpStreakItem } from '../lib/api';

const streakColumns: ColumnsType<LimitUpStreakItem> = [
  {
    title: '股票',
    render: (_, row) => <Link to={`/stocks/${row.stock_code}`}>{row.stock_name || row.stock_code}</Link>,
  },
  { title: '代码', dataIndex: 'stock_code' },
  { title: '板数', dataIndex: 'board_count', render: (value: number) => <Tag color="volcano">{value} 板</Tag> },
  { title: '封板时间', dataIndex: 'limit_up_time', render: (value: string) => value || '—' },
  { title: '题材', dataIndex: 'hot_theme', render: (value: string) => value || '—' },
];

export function SentimentOverviewPage() {
  const historyQuery = useQuery({
    queryKey: ['hot-sector-history', 7],
    queryFn: () => getHotSectorHistory(7),
  });

  const streakQuery = useQuery({
    queryKey: ['limit-up-streaks', 2],
    queryFn: () => getLimitUpStreaks(undefined, 2),
  });

  const historyChart = useMemo(() => {
    const data = historyQuery.data;
    if (!data || data.days.length === 0) {
      return null;
    }

    const tradeDates = data.trade_dates;
    const themeNames = Array.from(new Set(data.days.flatMap((d) => d.sectors.map((s) => s.name))));
    const themeIndex = new Map(themeNames.map((name, idx) => [name, idx]));
    const points: [number, number, number][] = [];

    data.days.forEach((day, x) => {
      day.sectors.forEach((sector) => {
        const y = themeIndex.get(sector.name);
        if (y !== undefined) {
          points.push([x, y, sector.heat_score]);
        }
      });
    });

    return {
      tooltip: {
        formatter: (params: { value: [number, number, number] }) => {
          const [x, y, score] = params.value;
          return `${tradeDates[x]}<br/>${themeNames[y]}<br/>热度：${score}`;
        },
      },
      xAxis: { type: 'category', data: tradeDates },
      yAxis: { type: 'category', data: themeNames },
      visualMap: {
        min: 0,
        max: Math.max(...points.map((p) => p[2]), 1),
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
      },
      series: [
        {
          name: '热点热度',
          type: 'heatmap',
          data: points,
          label: { show: false },
          emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0, 0, 0, 0.35)' } },
        },
      ],
      grid: { left: 90, right: 20, top: 20, bottom: 60 },
    };
  }, [historyQuery.data]);

  if (historyQuery.isLoading || streakQuery.isLoading) {
    return (
      <Space direction="vertical" size={24} style={{ display: 'flex' }}>
        <Typography.Title level={2} style={{ margin: 0 }}>短线情绪总览</Typography.Title>
        <Card className="page-card"><Spin /></Card>
      </Space>
    );
  }

  if (historyQuery.error || streakQuery.error) {
    return (
      <Space direction="vertical" size={24} style={{ display: 'flex' }}>
        <Typography.Title level={2} style={{ margin: 0 }}>短线情绪总览</Typography.Title>
        <Alert type="error" showIcon message="加载短线情绪数据失败" />
      </Space>
    );
  }

  return (
    <Space direction="vertical" size={24} style={{ display: 'flex' }}>
      <Typography.Title level={2} style={{ margin: 0 }}>短线情绪总览</Typography.Title>

      <Card className="page-card" title="热点板块趋势热力图（近 7 日）">
        {historyChart ? <ReactECharts option={historyChart} style={{ height: 380 }} /> : <Empty description="暂无热点趋势数据" />}
      </Card>

      <Card className="page-card" title={`近期连板龙头（${streakQuery.data?.trade_date || '—'}）`}>
        <Table
          rowKey={(row) => `${row.trade_date}-${row.stock_code}`}
          columns={streakColumns}
          dataSource={streakQuery.data?.streaks ?? []}
          pagination={false}
        />
      </Card>
    </Space>
  );
}

