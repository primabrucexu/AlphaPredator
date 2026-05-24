import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import { Alert, Badge, Button, Card, Col, Collapse, DatePicker, Empty, Image, Input, Modal, Popover, Row, Space, Spin, Switch, Table, Tabs, Tag, Tooltip, Typography } from 'antd';
import { FileTextOutlined, SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { Link } from 'react-router-dom';
import dayjs from 'dayjs';
import {
    getHotReviewImages,
    getHotReviewTable,
    getHotSectorAggregated,
    getHotSectorHistory,
    getLimitUpStreaks,
    type HotReviewTableRow,
    type HotSectorAggregatedItem,
    type LimitUpStreakItem,
} from '../lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AdvancementRow {
    key: string;
    label: string;
    prevCount: number;
    advancedCount: number;
    rate: number;
}

interface SectorGroup {
    sector: string;
    count: number;
    rows: HotReviewTableRow[];
}

// ---------------------------------------------------------------------------
// Table columns
// ---------------------------------------------------------------------------

const streakColumns: ColumnsType<LimitUpStreakItem> = [
    {
        title: '股票',
        render: (_, row) => <Link to={`/stocks/${row.stock_code}`}>{row.stock_name || row.stock_code}</Link>,
    },
    { title: '代码', dataIndex: 'stock_code', width: 90 },
    {
        title: '板数',
        dataIndex: 'board_count',
        width: 80,
        render: (value: number) => <Tag color="volcano">{value} 板</Tag>,
    },
    { title: '封板时间', dataIndex: 'limit_up_time', width: 100, render: (v: string) => v || '—' },
    { title: '题材', dataIndex: 'hot_theme', render: (v: string) => v || '—' },
];

const advancementColumns: ColumnsType<AdvancementRow> = [
    { title: '板级晋级', dataIndex: 'label', width: 120 },
    { title: '昨日家数', dataIndex: 'prevCount', width: 90 },
    { title: '今日晋级', dataIndex: 'advancedCount', width: 90 },
    {
        title: '成功率',
        dataIndex: 'rate',
        width: 100,
        render: (rate: number) => {
            const color = rate >= 40 ? 'success' : rate >= 20 ? 'warning' : 'error';
            return <Tag color={color}>{rate}%</Tag>;
        },
    },
];

/** 板块内股票明细列（不含板块列） */
const sectorStockColumns: ColumnsType<HotReviewTableRow> = [
    {
        title: '代码',
        dataIndex: 'stock_code',
        width: 90,
    },
    {
        title: '股票',
        width: 110,
        render: (_, row) => (
            <Link to={`/stocks/${row.stock_code}`}>{row.stock_name || row.stock_code}</Link>
        ),
    },
    {
        title: '连板',
        dataIndex: 'streak_text',
        width: 90,
        render: (v: string) => v || '首板',
    },
    {
        title: '涨停时间',
        dataIndex: 'limit_up_time',
        width: 90,
        render: (v: string) => v || '—',
    },
    {
        title: '摘要',
        dataIndex: 'short_reason',
        render: (v: string) =>
            v ? (
                <Typography.Paragraph
                    style={{ marginBottom: 0 }}
                    ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
                >
                    {v}
                </Typography.Paragraph>
            ) : '—',
    },
    {
        title: '解析',
        dataIndex: 'reason',
        width: 48,
        align: 'center',
        render: (v: string) =>
            v ? (
                <Popover
                    title="涨停解析"
                    content={
                        <div style={{ maxWidth: 360, whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
                            {v}
                        </div>
                    }
                    trigger="click"
                    placement="left"
                >
                    <Tooltip title="查看解析">
                        <Button type="text" size="small" icon={<SearchOutlined />} />
                    </Tooltip>
                </Popover>
            ) : '—',
    },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isStStock(name: string): boolean {
    return name.toUpperCase().includes('ST');
}

function isStRow(row: HotReviewTableRow): boolean {
    // 同时检查股票名和板块名，与后端 _is_st_row 保持一致
    // 数据库中部分 ST 股 name 字段为空，但 hot_theme='ST板块'
    return isStStock(row.stock_name) || isStStock(row.hot_theme);
}

function parseBoardCount(streakText: string): number {
    const text = String(streakText || '').trim();
    if (!text || text === '首板' || text === '首次涨停' || text === '-') return 1;
    const num = text.match(/(\d+)/);
    if (num) return Math.max(1, Number(num[1]));
    const cnMap: Array<[string, number]> = [
        ['十五', 15], ['十四', 14], ['十三', 13], ['十二', 12], ['十一', 11],
        ['十', 10], ['九', 9], ['八', 8], ['七', 7], ['六', 6],
        ['五', 5], ['四', 4], ['三', 3], ['两', 2], ['二', 2], ['一', 1],
    ];
    for (const [cn, value] of cnMap) {
        if (text.includes(cn)) return value;
    }
    return 1;
}

function splitThemes(hotTheme: string): string[] {
    return String(hotTheme || '')
        .split('、')
        .map(item => item.trim())
        .filter(Boolean);
}

// ---------------------------------------------------------------------------
// AggregatedTable 子组件
// ---------------------------------------------------------------------------

interface AggregatedTableProps {
    data: HotSectorAggregatedItem[];
    windows: number[];
}

/** 将去重数字映射到背景色（越多越深红） */
function heatColor(value: number, max: number): string {
    if (!value || !max) return 'transparent';
    const ratio = Math.min(value / max, 1);
    const alpha = 0.1 + ratio * 0.6;
    return `rgba(220, 53, 53, ${alpha})`;
}

function AggregatedTable({ data, windows }: AggregatedTableProps) {
    const sortedWindows = [...windows].sort((a, b) => a - b);
    const maxW = Math.max(...sortedWindows);
    const maxVal = data.reduce((m, item) => Math.max(m, item.counts[String(maxW)] ?? 0), 0);

    const columns: ColumnsType<HotSectorAggregatedItem> = [
        {
            title: '板块',
            dataIndex: 'name',
            fixed: 'left',
            width: 140,
            render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
        },
        ...sortedWindows.map(w => ({
            title: `${w} 日`,
            dataIndex: ['counts', String(w)],
            width: 90,
            align: 'center' as const,
            render: (val: number | undefined) => {
                const count = val ?? 0;
                return (
                    <div
                        style={{
                            background: heatColor(count, maxVal),
                            borderRadius: 4,
                            padding: '2px 8px',
                            fontWeight: count > 0 ? 600 : 400,
                            color: count > 0 ? '#d32f2f' : '#999',
                        }}
                    >
                        {count > 0 ? count : '—'}
                    </div>
                );
            },
        })),
    ];

    if (!data.length) return <Empty description="暂无汇聚数据" />;

    return (
        <Table<HotSectorAggregatedItem>
            rowKey="name"
            columns={columns}
            dataSource={data}
            pagination={false}
            size="small"
            scroll={{ y: 380 }}
        />
    );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function SentimentOverviewPage() {
    const [showSt, setShowSt] = useState(false);
    const [showOthers, setShowOthers] = useState(false);
    const [reviewTradeDate, setReviewTradeDate] = useState<string>();
    const [reviewKeyword, setReviewKeyword] = useState('');
    const [streakTradeDate, setStreakTradeDate] = useState<string>();
    const [imageModalOpen, setImageModalOpen] = useState(false);


    // ── 历史趋势 ──────────────────────────────────────────────────────────────
    const historyQuery = useQuery({
        queryKey: ['hot-sector-history', 60],
        queryFn: () => getHotSectorHistory(60, false),
    });

    // ── 多日汇聚 ──────────────────────────────────────────────────────────────
    const aggregatedQuery = useQuery({
        queryKey: ['hot-sector-aggregated'],
        queryFn: () => getHotSectorAggregated(false),
    });

    const tradeDates: string[] = historyQuery.data?.trade_dates ?? [];
    const latestDate = tradeDates.at(-1) ?? '';

    // ── 复盘图片 ──────────────────────────────────────────────────────────────
    const selectedReviewDate = reviewTradeDate || latestDate;
    const reviewImagesQuery = useQuery({
        queryKey: ['hot-review-images', selectedReviewDate || 'latest'],
        queryFn: () => getHotReviewImages(selectedReviewDate || undefined),
    });
    const reviewTableQuery = useQuery({
        queryKey: ['hot-review-table', selectedReviewDate || 'latest'],
        queryFn: () => getHotReviewTable(selectedReviewDate || undefined, false),
    });
    const images = reviewImagesQuery.data?.images ?? [];
    const filteredReviewRows = useMemo(() => {
        const rows = reviewTableQuery.data?.rows ?? [];
        let filtered = rows;
        
        // ST 过滤（与后端同步，前端加保险）
        if (!showSt) {
            filtered = filtered.filter(row => !isStRow(row));
        }
        
        // 关键词过滤
        const keyword = reviewKeyword.trim().toLowerCase();
        if (!keyword) {
            return filtered;
        }
        return filtered.filter(row => [
            row.stock_code,
            row.stock_name,
            row.limit_up_time,
            row.streak_text,
            row.hot_theme,
            row.short_reason,
            row.reason,
        ].some(value => String(value || '').toLowerCase().includes(keyword)));
    }, [reviewTableQuery.data?.rows, reviewKeyword, showSt]);

    const sectorGroups = useMemo((): SectorGroup[] => {
        const sectorMap = new Map<string, HotReviewTableRow[]>();
        filteredReviewRows.forEach(row => {
            const sectors = splitThemes(row.hot_theme);
            if (!sectors.length) {
                const list = sectorMap.get('其他') ?? [];
                list.push(row);
                sectorMap.set('其他', list);
                return;
            }
            sectors.forEach(sector => {
                const list = sectorMap.get(sector) ?? [];
                list.push(row);
                sectorMap.set(sector, list);
            });
        });

        const groups = [...sectorMap.entries()]
            .map(([sector, rows]) => {
                const uniqueRows = [...new Map(rows.map(item => [`${item.trade_date}-${item.stock_code}`, item])).values()];
                const sortedRows = [...uniqueRows].sort((a, b) => {
                    const boardDiff = parseBoardCount(b.streak_text) - parseBoardCount(a.streak_text);
                    return boardDiff !== 0 ? boardDiff : String(a.limit_up_time || '').localeCompare(String(b.limit_up_time || ''));
                });
                return { sector, count: sortedRows.length, rows: sortedRows };
            })
            .sort((a, b) => b.count !== a.count ? b.count - a.count : a.sector.localeCompare(b.sector, 'zh-CN'));

        return showOthers ? groups : groups.filter(g => g.sector !== '其他');
    }, [filteredReviewRows, showOthers]);

    // ── 连板数据 ──────────────────────────────────────────────────────────────
    const selectedStreakDate = streakTradeDate || latestDate;
    const prevStreakDate = useMemo(() => {
        if (!tradeDates.length) return undefined;
        const idx = tradeDates.indexOf(selectedStreakDate);
        return idx > 0 ? tradeDates[idx - 1] : undefined;
    }, [tradeDates, selectedStreakDate]);

    const todayStreakQuery = useQuery({
        queryKey: ['limit-up-streaks', selectedStreakDate || 'latest', 2],
        queryFn: () => getLimitUpStreaks(selectedStreakDate || undefined, 2, false),
    });

    const prevStreakQuery = useQuery({
        queryKey: ['limit-up-streaks', prevStreakDate ?? 'none', 2],
        queryFn: () => getLimitUpStreaks(prevStreakDate, 2, false),
        enabled: !!prevStreakDate,
    });

    // ── ST 过滤 ───────────────────────────────────────────────────────────────
    const todayStreaks = useMemo(() => {
        const streaks = todayStreakQuery.data?.streaks ?? [];
        return showSt ? streaks : streaks.filter(s => !isStStock(s.stock_name));
    }, [todayStreakQuery.data, showSt]);

    const prevStreaks = useMemo(() => {
        const streaks = prevStreakQuery.data?.streaks ?? [];
        return showSt ? streaks : streaks.filter(s => !isStStock(s.stock_name));
    }, [prevStreakQuery.data, showSt]);

    // ── 连板分布 ──────────────────────────────────────────────────────────────
    const boardDist = useMemo(() => {
        const dist = { two: 0, three: 0, fourPlus: 0 };
        todayStreaks.forEach(s => {
            if (s.board_count === 2) dist.two++;
            else if (s.board_count === 3) dist.three++;
            else if (s.board_count >= 4) dist.fourPlus++;
        });
        return dist;
    }, [todayStreaks]);

    // ── 晋级成功率 ────────────────────────────────────────────────────────────
    const advancementStats = useMemo((): AdvancementRow[] => {
        if (!prevStreaks.length) return [];
        const todayMap = new Map(todayStreaks.map(s => [s.stock_code, s]));

        const levels = [
            {
                key: '2板',
                label: '2板→3板',
                filter: (s: LimitUpStreakItem) => s.board_count === 2,
                advanced: (_p: LimitUpStreakItem, t: LimitUpStreakItem) => t.board_count === 3,
            },
            {
                key: '3板',
                label: '3板→4板',
                filter: (s: LimitUpStreakItem) => s.board_count === 3,
                advanced: (_p: LimitUpStreakItem, t: LimitUpStreakItem) => t.board_count === 4,
            },
            {
                key: '4板+',
                label: '4板+→更高',
                filter: (s: LimitUpStreakItem) => s.board_count >= 4,
                advanced: (p: LimitUpStreakItem, t: LimitUpStreakItem) => t.board_count > p.board_count,
            },
        ];

        return levels
            .map(level => {
                const prevGroup = prevStreaks.filter(level.filter);
                if (!prevGroup.length) return null;
                const advancedCount = prevGroup.filter(s => {
                    const today = todayMap.get(s.stock_code);
                    return today ? level.advanced(s, today) : false;
                }).length;
                return {
                    key: level.key,
                    label: level.label,
                    prevCount: prevGroup.length,
                    advancedCount,
                    rate: Math.round((advancedCount / prevGroup.length) * 100),
                };
            })
            .filter((x): x is AdvancementRow => x !== null);
    }, [todayStreaks, prevStreaks]);

    // ── 可用日期集合（用于 DatePicker 禁用） ──────────────────────────────────
    const availableDatesSet = useMemo(() => new Set<string>(tradeDates), [tradeDates]);
    const disabledDate = (current: dayjs.Dayjs) => {
        if (!current) return false;
        return !availableDatesSet.has(current.format('YYYY-MM-DD'));
    };

    // ── 趋势图 ECharts 配置 ───────────────────────────────────────────────────
    const historyChart = useMemo(() => {
        const data = historyQuery.data;
        if (!data || data.days.length === 0) return null;

        const dates = data.trade_dates;
        const themeHeat = new Map<string, number>();
        data.days.forEach(d => {
            d.sectors
                .filter(s => (showSt || !isStStock(s.name)) && (showOthers || s.name !== '其他'))
                .forEach(s => {
                    themeHeat.set(s.name, (themeHeat.get(s.name) ?? 0) + s.heat_score);
                });
        });

        const allThemes = [...themeHeat.entries()]
            .sort((a, b) => b[1] - a[1])
            .slice(0, 15)
            .map(([name]) => name);

        const dayMap = new Map(data.days.map(d => [d.trade_date, d]));

        const series = allThemes.map(theme => ({
            name: theme,
            type: 'line',
            smooth: false,
            symbol: 'circle',
            symbolSize: 5,
            data: dates.map(date => {
                const day = dayMap.get(date);
                const sector = day?.sectors.find(s => s.name === theme);
                return sector?.heat_score ?? null;
            }),
            connectNulls: false,
        }));

        // 默认展示近 10 日
        const defaultStart = dates.length > 0 ? Math.max(0, Math.round((1 - 10 / dates.length) * 100)) : 80;

        return {
            tooltip: {
                trigger: 'axis',
                formatter: (params: { seriesName: string; value: number | null; name: string }[]) => {
                    const date = params[0]?.name ?? '';
                    const lines = params
                        .filter(p => p.value !== null && p.value !== undefined)
                        .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
                        .map(p => `${p.seriesName}：${p.value} 家`)
                        .join('<br/>');
                    return `${date}<br/>${lines}`;
                },
            },
            legend: {
                data: allThemes,
                type: 'scroll',
                top: 0,
                pageButtonPosition: 'end',
            },
            xAxis: { type: 'category', data: dates, boundaryGap: false },
            yAxis: { type: 'value', name: '涨停家数', minInterval: 1 },
            dataZoom: [
                {
                    type: 'slider',
                    xAxisIndex: 0,
                    bottom: 10,
                    start: defaultStart,
                    end: 100,
                    height: 20,
                },
            ],
            grid: { left: 60, right: 20, top: 50, bottom: 60 },
            series,
        };
    }, [historyQuery.data, showSt, showOthers]);

    // ── 渲染 ──────────────────────────────────────────────────────────────────
    if (historyQuery.isLoading) {
        return (
            <Space direction="vertical" size={24} style={{ display: 'flex' }}>
                <Typography.Title level={2} style={{ margin: 0 }}>短线情绪总览</Typography.Title>
                <Card className="page-card"><Spin /></Card>
            </Space>
        );
    }

    if (historyQuery.error) {
        return (
            <Space direction="vertical" size={24} style={{ display: 'flex' }}>
                <Typography.Title level={2} style={{ margin: 0 }}>短线情绪总览</Typography.Title>
                <Alert type="error" showIcon message="加载短线情绪数据失败" />
            </Space>
        );
    }

    return (
        <Space direction="vertical" size={24} style={{ display: 'flex' }}>
            {/* 标题 + ST 开关 */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography.Title level={2} style={{ margin: 0 }}>短线情绪总览</Typography.Title>
                <Space>
                    <Typography.Text type="secondary">显示其他</Typography.Text>
                    <Switch checked={showOthers} onChange={setShowOthers} />
                    <Typography.Text type="secondary">显示 ST 数据</Typography.Text>
                    <Switch checked={showSt} onChange={setShowSt} />
                </Space>
            </div>

            <Row gutter={[16, 16]} align="top">
                <Col xs={24} xl={13}>
                    <Space direction="vertical" size={16} style={{ display: 'flex' }}>
                        {/* 热点板块涨停趋势 + 多日汇聚 */}
                        <Card className="page-card" styles={{ body: { paddingTop: 0 } }}>
                            <Tabs
                                defaultActiveKey="trend"
                                items={[
                                    {
                                        key: 'trend',
                                        label: '涨停趋势（近 60 日）',
                                        children: historyChart
                                            ? <ReactECharts option={historyChart} style={{ height: 420 }} />
                                            : <Empty description="暂无热点趋势数据" />,
                                    },
                                    {
                                        key: 'aggregated',
                                        label: '多日汇聚',
                                        children: aggregatedQuery.isLoading
                                            ? <Spin />
                                            : <AggregatedTable
                                                data={(aggregatedQuery.data?.sectors ?? []).filter(s => (showSt || !isStStock(s.name)) && (showOthers || s.name !== '其他'))}
                                                windows={aggregatedQuery.data?.windows ?? [5, 10, 20]}
                                            />,
                                    },
                                ]}
                            />
                        </Card>

                        {/* 连板情况 */}
                        <Card
                            className="page-card"
                            title={`连板情况（${selectedStreakDate || '—'}）`}
                            extra={
                                <DatePicker
                                    placeholder="选择交易日"
                                    disabledDate={disabledDate}
                                    value={streakTradeDate ? dayjs(streakTradeDate) : (latestDate ? dayjs(latestDate) : null)}
                                    onChange={date => setStreakTradeDate(date?.format('YYYY-MM-DD'))}
                                    allowClear={false}
                                />
                            }
                        >
                            {todayStreakQuery.isLoading ? (
                                <Spin />
                            ) : (
                                <Space direction="vertical" size={20} style={{ display: 'flex' }}>
                                    {/* 当日连板分布 */}
                                    <div>
                                        <Typography.Text strong style={{ display: 'block', marginBottom: 12 }}>
                                            当日连板分布
                                        </Typography.Text>
                                        <Space size={16} wrap>
                                            {[
                                                { label: '2板', value: boardDist.two, color: '#fa8c16' },
                                                { label: '3板', value: boardDist.three, color: '#f5222d' },
                                                { label: '4板+', value: boardDist.fourPlus, color: '#722ed1' },
                                            ].map(item => (
                                                <Card
                                                    key={item.label}
                                                    size="small"
                                                    style={{ minWidth: 110, textAlign: 'center', borderColor: item.color }}
                                                >
                                                    <div style={{ fontSize: 28, fontWeight: 700, color: item.color, lineHeight: 1.2 }}>
                                                        {item.value}
                                                    </div>
                                                    <div style={{ color: '#666', marginTop: 4, fontSize: 13 }}>
                                                        {item.label} <span style={{ fontSize: 12 }}>家</span>
                                                    </div>
                                                </Card>
                                            ))}
                                        </Space>
                                    </div>

                                    {/* 连板晋级成功率 */}
                                    <div>
                                        <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
                                            连板晋级成功率
                                            {prevStreakDate && (
                                                <Typography.Text type="secondary" style={{ fontWeight: 400, marginLeft: 8, fontSize: 12 }}>
                                                    （基于 {prevStreakDate} → {selectedStreakDate}）
                                                </Typography.Text>
                                            )}
                                        </Typography.Text>
                                        {prevStreakQuery.isLoading ? (
                                            <Spin size="small" />
                                        ) : advancementStats.length > 0 ? (
                                            <Table<AdvancementRow>
                                                rowKey="key"
                                                columns={advancementColumns}
                                                dataSource={advancementStats}
                                                pagination={false}
                                                size="small"
                                            />
                                        ) : (
                                            <Typography.Text type="secondary">
                                                {prevStreakDate ? '暂无晋级数据' : '无前一交易日数据'}
                                            </Typography.Text>
                                        )}
                                    </div>

                                    {/* 连板明细 */}
                                    <div>
                                        <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
                                            连板明细
                                        </Typography.Text>
                                        <Table<LimitUpStreakItem>
                                            rowKey={row => `${row.trade_date}-${row.stock_code}`}
                                            columns={streakColumns}
                                            dataSource={todayStreaks}
                                            pagination={false}
                                            locale={{ emptyText: '暂无连板股票' }}
                                            size="small"
                                        />
                                    </div>
                                </Space>
                            )}
                        </Card>
                    </Space>
                </Col>

                <Col xs={24} xl={11}>
                    {/* 复盘数据库内容 */}
                    <Card
                        className="page-card"
                        title="涨停信息表"
                        extra={
                            <Space wrap>
                                <DatePicker
                                    placeholder="选择交易日"
                                    disabledDate={disabledDate}
                                    value={reviewTradeDate ? dayjs(reviewTradeDate) : (latestDate ? dayjs(latestDate) : null)}
                                    onChange={date => setReviewTradeDate(date?.format('YYYY-MM-DD'))}
                                    allowClear={false}
                                />
                                <Input
                                    allowClear
                                    placeholder="搜索股票/题材/OCR"
                                    value={reviewKeyword}
                                    onChange={event => setReviewKeyword(event.target.value)}
                                    style={{ width: 180 }}
                                />
                                <Button onClick={() => setImageModalOpen(true)} disabled={images.length === 0}>
                                    查看复盘图片
                                </Button>
                            </Space>
                        }
                    >
                        {reviewTableQuery.isLoading ? (
                            <Spin />
                        ) : sectorGroups.length === 0 ? (
                            <Empty description={reviewKeyword ? '无匹配记录' : '暂无复盘数据库记录'} />
                        ) : (
                            <div style={{ maxHeight: 900, overflowY: 'auto' }}>
                                <Collapse
                                    defaultActiveKey={sectorGroups.map(g => g.sector)}
                                    size="small"
                                    items={sectorGroups.map(group => ({
                                        key: group.sector,
                                        label: (
                                            <Space>
                                                <Typography.Text strong>{group.sector}</Typography.Text>
                                                <Badge
                                                    count={group.count}
                                                    style={{ backgroundColor: '#d32f2f' }}
                                                />
                                            </Space>
                                        ),
                                        children: (
                                            <Table<HotReviewTableRow>
                                                rowKey={row => `${row.trade_date}-${row.stock_code}`}
                                                columns={sectorStockColumns}
                                                dataSource={group.rows}
                                                pagination={false}
                                                size="small"
                                                style={{ marginBottom: 0 }}
                                            />
                                        ),
                                    }))}
                                />
                            </div>
                        )}
                    </Card>
                </Col>
            </Row>

            <Modal
                title={`复盘图片（${selectedReviewDate || '—'}）`}
                open={imageModalOpen}
                onCancel={() => setImageModalOpen(false)}
                footer={null}
                width="90vw"
                style={{ maxWidth: 1400, top: 24 }}
                styles={{ body: { maxHeight: '80vh', overflowY: 'auto', padding: '12px 0' } }}
            >
                {reviewImagesQuery.isLoading ? (
                    <Spin />
                ) : images.length > 0 ? (
                    <Space direction="vertical" size={16} style={{ display: 'flex' }}>
                        {images.map((img, idx) => (
                            <Image
                                key={idx}
                                src={img.url}
                                width="100%"
                                style={{ borderRadius: 6, display: 'block' }}
                                preview={false}
                            />
                        ))}
                    </Space>
                ) : (
                    <Empty description="该日期暂无复盘图片" />
                )}
            </Modal>

        </Space>
    );
}

