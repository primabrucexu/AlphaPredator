import { Card, Segmented, Space, Table, Typography } from 'antd';
import { useState } from 'react';

interface HistoryRow {
  key: string;
  primary: string;
  secondary: string;
}

const historyRows: HistoryRow[] = [
  { key: '1', primary: '2026-05-01', secondary: 'Top 结果占位' },
  { key: '2', primary: '突破回踩策略', secondary: '命中次数占位' },
  { key: '3', primary: '中际旭创', secondary: '最近一次结论占位' },
];

export function HistoryPage() {
  const [view, setView] = useState<'date' | 'skill' | 'stock'>('date');

  return (
    <Space direction="vertical" size={24} style={{ display: 'flex' }}>
      <Typography.Title level={2} style={{ margin: 0 }}>
        历史记录
      </Typography.Title>
      <Card className="page-card" title="历史视图（Phase 1 占位）">
        <Space direction="vertical" size={16} style={{ display: 'flex' }}>
          <Segmented
            value={view}
            onChange={(value) => setView(value as typeof view)}
            options={[
              { label: '按日期', value: 'date' },
              { label: '按 Skill', value: 'skill' },
              { label: '按股票', value: 'stock' },
            ]}
          />
          <Table
            pagination={false}
            dataSource={historyRows}
            columns={[
              { title: view === 'date' ? '日期' : view === 'skill' ? 'Skill' : '股票', dataIndex: 'primary' },
              { title: '摘要', dataIndex: 'secondary' },
            ]}
          />
        </Space>
      </Card>
    </Space>
  );
}
