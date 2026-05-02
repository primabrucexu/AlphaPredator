import { Card, Col, Row, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { Link } from 'react-router-dom';

interface ResultRow {
  stockCode: string;
  stockName: string;
  summary: string;
  finalAction: '买入' | '观察' | '回避';
  score: number;
  supportVotes: number;
  opposeVotes: number;
  focused: boolean;
}

const columns: ColumnsType<ResultRow> = [
  {
    title: '股票',
    render: (_, row) => (
      <Space direction="vertical" size={0}>
        <Space>
          {row.focused ? <Tag color="gold">重点关注</Tag> : null}
          <Link to={`/stocks/${row.stockCode}`}>{row.stockName}</Link>
        </Space>
        <Typography.Text type="secondary">{row.summary}</Typography.Text>
      </Space>
    ),
  },
  { title: '动作', dataIndex: 'finalAction' },
  { title: '最终分', dataIndex: 'score' },
  { title: '支持票', dataIndex: 'supportVotes' },
  { title: '反对票', dataIndex: 'opposeVotes' },
];

const rows: ResultRow[] = [
  {
    stockCode: '300308',
    stockName: '中际旭创',
    summary: '算力主线延续，业绩与趋势共振。',
    finalAction: '观察',
    score: 8.4,
    supportVotes: 3,
    opposeVotes: 1,
    focused: true,
  },
];

export function AiResultsPage() {
  return (
    <Space direction="vertical" size={24} style={{ display: 'flex' }}>
      <Typography.Title level={2} style={{ margin: 0 }}>
        AI 选股结果
      </Typography.Title>
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card className="page-card" title="结果列表（Phase 1 占位）">
            <Table rowKey="stockCode" pagination={false} columns={columns} dataSource={rows} />
          </Card>
        </Col>
      </Row>
    </Space>
  );
}
