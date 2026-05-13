import {useEffect, useMemo, useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import {Alert, Button, Card, DatePicker, Empty, InputNumber, Select, Space, Spin, Table, Tag, Typography} from 'antd';
import type {ColumnsType} from 'antd/es/table';
import {Link} from 'react-router-dom';
import {
    getHotReviewImages,
    getHotSectorHistory,
    getLimitUpStreaks,
    type HotSectorHistorySector,
    type LimitUpStreakItem,
} from '../lib/api';

const HISTORY_DAY_OPTIONS = [5, 7, 10, 20].map((value) => ({value, label: `近 ${value} 日`}));

const hotSectorColumns: ColumnsType<HotSectorHistorySector> = [
    {
        title: '排名',
        dataIndex: 'rank_today',
        render: (value: number | undefined) => value ?? '—',
        width: 90,
    },
    {title: '板块', dataIndex: 'name'},
    {
        title: '涨停家数',
        dataIndex: 'heat_score',
        render: (value: number) => value,
    },
    {
        title: '趋势',
        render: (_, row) => row.trend_label || row.trend_tag || '—',
    },
    {
        title: '最高连板',
        dataIndex: 'max_board_count',
        render: (value: number | undefined) => (typeof value === 'number' ? `${value} 板` : '—'),
    },
];

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
    const [historyDays, setHistoryDays] = useState(7);
    const [minBoards, setMinBoards] = useState(2);
    const [streakTradeDate, setStreakTradeDate] = useState<string>();
    const [currentImageIndex, setCurrentImageIndex] = useState(0);

  const historyQuery = useQuery({
      queryKey: ['hot-sector-history', historyDays],
      queryFn: () => getHotSectorHistory(historyDays),
  });

  const streakQuery = useQuery({
      queryKey: ['limit-up-streaks', streakTradeDate ?? 'latest', minBoards],
      queryFn: () => getLimitUpStreaks(streakTradeDate, minBoards),
  });

    const latestDay = useMemo(() => {
        const days = historyQuery.data?.days;
        if (!days || days.length === 0) {
            return null;
        }
        return [...days].sort((a, b) => a.trade_date.localeCompare(b.trade_date)).at(-1) ?? null;
    }, [historyQuery.data]);

    const reviewImagesQuery = useQuery({
        queryKey: ['hot-review-images', latestDay?.trade_date ?? 'latest'],
        queryFn: () => getHotReviewImages(latestDay?.trade_date),
    });

    useEffect(() => {
        setCurrentImageIndex(0);
    }, [reviewImagesQuery.data?.trade_date, reviewImagesQuery.data?.images?.length]);

    const currentImage = reviewImagesQuery.data?.images[currentImageIndex] ?? null;

    const switchImage = (step: number) => {
        const images = reviewImagesQuery.data?.images ?? [];
        if (images.length === 0) {
            return;
        }
        setCurrentImageIndex((prev) => (prev + step + images.length) % images.length);
    };

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
            return `${tradeDates[x]}<br/>${themeNames[y]}<br/>涨停家数：${score}`;
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
            name: '涨停家数',
          type: 'heatmap',
          data: points,
          label: { show: false },
          emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0, 0, 0, 0.35)' } },
        },
      ],
      grid: { left: 90, right: 20, top: 20, bottom: 60 },
    };
  }, [historyQuery.data]);

    if (historyQuery.isLoading || streakQuery.isLoading || reviewImagesQuery.isLoading) {
    return (
      <Space direction="vertical" size={24} style={{ display: 'flex' }}>
        <Typography.Title level={2} style={{ margin: 0 }}>短线情绪总览</Typography.Title>
        <Card className="page-card"><Spin /></Card>
      </Space>
    );
  }

    if (historyQuery.error || streakQuery.error || reviewImagesQuery.error) {
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

        <Card className="page-card" title="查询条件">
            <Space wrap size={16}>
                <Space>
                    <Typography.Text type="secondary">趋势范围</Typography.Text>
                    <Select
                        style={{width: 120}}
                        options={HISTORY_DAY_OPTIONS}
                        value={historyDays}
                        onChange={(value) => setHistoryDays(value)}
                    />
                </Space>
                <Space>
                    <Typography.Text type="secondary">连板最小板数</Typography.Text>
                    <InputNumber
                        min={2}
                        max={20}
                        value={minBoards}
                        onChange={(value) => setMinBoards(typeof value === 'number' ? value : 2)}
                    />
                </Space>
                <Space>
                    <Typography.Text type="secondary">连板交易日</Typography.Text>
                    <DatePicker
                        placeholder="默认最新交易日"
                        onChange={(_, dateString) => setStreakTradeDate(typeof dateString === 'string' && dateString ? dateString : undefined)}
                    />
                </Space>
            </Space>
        </Card>

        <Card className="page-card" title={`热点板块趋势热力图（近 ${historyDays} 日）`}>
        {historyChart ? <ReactECharts option={historyChart} style={{ height: 380 }} /> : <Empty description="暂无热点趋势数据" />}
      </Card>

        <Card className="page-card" title={`当日热点板块排行（${latestDay?.trade_date || '—'}）`}>
            <Table
                rowKey={(row) => row.name}
                columns={hotSectorColumns}
                dataSource={latestDay?.sectors ?? []}
                pagination={false}
                locale={{emptyText: '暂无当日热点板块数据'}}
            />
        </Card>

        <Card className="page-card"
              title={`当日复盘图片（${reviewImagesQuery.data?.trade_date || latestDay?.trade_date || '—'}）`}>
            {currentImage ? (
                <Space direction="vertical" size={12} style={{display: 'flex'}}>
                    <img
                        src={currentImage.url}
                        alt={`复盘图 ${currentImageIndex + 1}`}
                        style={{
                            width: '100%',
                            maxHeight: 520,
                            objectFit: 'contain',
                            borderRadius: 8,
                            background: '#fafafa'
                        }}
                    />
                    <Space style={{justifyContent: 'space-between', width: '100%'}}>
                        <Button onClick={() => switchImage(-1)}>上一张</Button>
                        <Typography.Text type="secondary">
                            {currentImageIndex + 1} / {reviewImagesQuery.data?.images.length}
                        </Typography.Text>
                        <Button onClick={() => switchImage(1)}>下一张</Button>
                    </Space>
                </Space>
            ) : (
                <Empty description="暂无复盘图片"/>
            )}
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

