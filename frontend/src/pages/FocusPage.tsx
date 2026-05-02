import { Card, List, Space, Tag, Typography } from 'antd';

export function FocusPage() {
  return (
    <Space direction="vertical" size={24} style={{ display: 'flex' }}>
      <Typography.Title level={2} style={{ margin: 0 }}>
        重点关注
      </Typography.Title>
      <Card className="page-card" title="重点关注列表（Phase 1 占位）">
        <List
          dataSource={[
            {
              name: '中际旭创',
              action: '观察',
              summary: '算力主线仍在，但需观察量能与板块延续。',
            },
          ]}
          renderItem={(item) => (
            <List.Item>
              <Space direction="vertical" size={4}>
                <Space>
                  <Typography.Text strong>{item.name}</Typography.Text>
                  <Tag color="gold">{item.action}</Tag>
                </Space>
                <Typography.Text type="secondary">{item.summary}</Typography.Text>
              </Space>
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}
