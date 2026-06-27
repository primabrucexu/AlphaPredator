/**
 * 交易复盘编辑器 Drawer
 * 支持：上传截图 → OCR 解析 → 人工校对 → 填写主观复盘 → 保存
 */
import {DeleteOutlined, InboxOutlined, PlusOutlined} from '@ant-design/icons';
import {
  Alert, Button, DatePicker, Drawer, Form, Input, InputNumber,
  message, Radio, Select, Space, Spin, Steps, Table, Typography, Upload,
} from 'antd';
import type {UploadFile} from 'antd';
import dayjs from 'dayjs';
import {useEffect, useState} from 'react';
import {
  createTradeReview,
  ocrParseImage,
  updateTradeReview,
} from '../lib/api';
import type {OcrOperationItem, OperationItem, TradeReviewDetail} from '../lib/api';
import {StockSearchInput} from '../components/StockSearchBar';

const {TextArea} = Input;
const {Text} = Typography;

const OP_TYPE_LABELS: Record<string, string> = {
  buy: '建仓', add: '加仓', sell: '清仓',
  reduce: '减仓', t_buy: 'T+买', t_sell: 'T+卖',
};

interface Props {
  open: boolean;
  editTarget?: TradeReviewDetail | null;
  onClose: () => void;
  onSaved: () => void;
}

// 可编辑操作行，独立定义所有字段
interface EditRow {
  key: string;
  trade_time: string;
  operation_type: string;
  price: number;
  quantity: number;
  amount: number;
  source: string;
  note: string;
}

function opToEditRow(op: OperationItem | OcrOperationItem, idx: number): EditRow {
  return {
    key: String(idx),
    trade_time: op.trade_time,
    operation_type: op.operation_type,
    price: op.price,
    quantity: op.quantity,
    amount: op.amount,
    source: (op as OperationItem).source ?? 'ocr',
    note: (op as OperationItem).note ?? '',
  };
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.split(',')[1] ?? result);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function TradeReviewEditorDrawer({open, editTarget, onClose, onSaved}: Props) {
  const [currentStep, setCurrentStep] = useState(0);
  const [form] = Form.useForm();
  const [rows, setRows] = useState<EditRow[]>([]);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrError, setOcrError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (editTarget) {
      form.setFieldsValue({
        stock_code: editTarget.stock_code,
        stock_name: editTarget.stock_name,
        start_date: editTarget.start_date ? dayjs(editTarget.start_date) : null,
        end_date: editTarget.end_date ? dayjs(editTarget.end_date) : null,
        status: editTarget.status,
        entry_reason: editTarget.entry_reason,
        entry_expectation: editTarget.entry_expectation,
        reflection_did_well: editTarget.reflection_did_well,
        reflection_did_poorly: editTarget.reflection_did_poorly,
        reflection_redo_plan: editTarget.reflection_redo_plan,
      });
      setRows((editTarget.operations ?? []).map(opToEditRow));
    } else {
      form.resetFields();
      setRows([]);
      setOcrError('');
    }
    setCurrentStep(0);
  }, [open, editTarget, form]);

  const handleUpload = async (info: {fileList: UploadFile[]}) => {
    const file = info.fileList[info.fileList.length - 1]?.originFileObj;
    if (!file) return;
    setOcrLoading(true);
    setOcrError('');
    try {
      const b64 = await fileToBase64(file);
      const res = await ocrParseImage({image_base64: b64, mime_type: file.type || 'image/jpeg'});
      if (res.stock_name) form.setFieldValue('stock_name', res.stock_name);
      if (res.stock_code) form.setFieldValue('stock_code', res.stock_code);
      if (res.start_date) form.setFieldValue('start_date', dayjs(res.start_date));
      if (res.end_date) form.setFieldValue('end_date', dayjs(res.end_date));
      if (res.status) form.setFieldValue('status', res.status);
      if (res.operations.length > 0) {
        setRows(res.operations.map(opToEditRow));
        message.success(`OCR 识别成功，解析出 ${res.operations.length} 条成交记录，请校对`);
      } else {
        message.warning('OCR 未识别到成交明细，请手动填写');
      }
    } catch (e) {
      setOcrError(`OCR 解析失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setOcrLoading(false);
    }
  };

  const addRow = () => setRows(prev => [...prev, {
    key: String(Date.now()), operation_type: 'buy',
    trade_time: dayjs().format('YYYY-MM-DDTHH:mm:ss'),
    price: 0, quantity: 0, amount: 0, source: 'manual', note: '',
  }]);

  const removeRow = (key: string) => setRows(prev => prev.filter(r => r.key !== key));

  const patchRow = (key: string, patch: Partial<Omit<EditRow, 'key'>>) =>
    setRows(prev => prev.map(r => {
      if (r.key !== key) return r;
      const next = {...r, ...patch};
      if ('price' in patch || 'quantity' in patch) {
        next.amount = parseFloat((next.price * next.quantity).toFixed(2));
      }
      return next;
    }));

  const handleSave = async () => {
    try {
      const v = await form.validateFields();
      setSaving(true);
      const buys = rows.filter(r => ['buy', 'add', 't_buy'].includes(r.operation_type));
      const sells = rows.filter(r => ['sell', 'reduce', 't_sell'].includes(r.operation_type));
      const buyTotal = buys.reduce((s, r) => s + r.amount, 0);
      const sellTotal = sells.reduce((s, r) => s + r.amount, 0);
      const payload = {
        stock_code: v.stock_code ?? '',
        stock_name: v.stock_name ?? '',
        start_date: v.start_date ? dayjs(v.start_date).format('YYYY-MM-DD') : '',
        end_date: v.end_date ? dayjs(v.end_date).format('YYYY-MM-DD') : undefined,
        status: v.status ?? 'open',
        total_buy_amount: buyTotal > 0 ? parseFloat(buyTotal.toFixed(2)) : undefined,
        total_sell_amount: sellTotal > 0 ? parseFloat(sellTotal.toFixed(2)) : undefined,
        realized_pnl: buyTotal > 0 && sellTotal > 0 ? parseFloat((sellTotal - buyTotal).toFixed(2)) : undefined,
        return_rate: buyTotal > 0 && sellTotal > 0 ? parseFloat(((sellTotal - buyTotal) / buyTotal).toFixed(6)) : undefined,
        entry_reason: v.entry_reason ?? '',
        entry_expectation: v.entry_expectation ?? '',
        reflection_did_well: v.reflection_did_well ?? '',
        reflection_did_poorly: v.reflection_did_poorly ?? '',
        reflection_redo_plan: v.reflection_redo_plan ?? '',
        operations: rows.map(r => ({
          trade_time: r.trade_time, operation_type: r.operation_type,
          price: r.price, quantity: r.quantity, amount: r.amount,
          source: r.source, note: r.note,
        } as OperationItem)),
        decision_notes: [],
      };
      if (editTarget) {
        await updateTradeReview(editTarget.id, payload);
        message.success('复盘记录已更新');
      } else {
        await createTradeReview(payload);
        message.success('复盘记录已创建');
      }
      onSaved();
      onClose();
    } catch (e) {
      if ((e as {errorFields?: unknown}).errorFields) return;
      message.error(`保存失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const columns = [
    {title: '操作时间', dataIndex: 'trade_time', width: 158,
      render: (v: string, r: EditRow) => (
        <Input size="small" value={v} onChange={e => patchRow(r.key, {trade_time: e.target.value})} />
      )},
    {title: '类型', dataIndex: 'operation_type', width: 90,
      render: (v: string, r: EditRow) => (
        <Select size="small" value={v} style={{width: '100%'}}
          options={Object.entries(OP_TYPE_LABELS).map(([k, label]) => ({value: k, label}))}
          onChange={val => patchRow(r.key, {operation_type: val})} />
      )},
    {title: '价格', dataIndex: 'price', width: 88,
      render: (v: number, r: EditRow) => (
        <InputNumber size="small" value={v} step={0.01} style={{width: '100%'}}
          onChange={val => patchRow(r.key, {price: val ?? 0})} />
      )},
    {title: '数量', dataIndex: 'quantity', width: 88,
      render: (v: number, r: EditRow) => (
        <InputNumber size="small" value={v} step={100} style={{width: '100%'}}
          onChange={val => patchRow(r.key, {quantity: val ?? 0})} />
      )},
    {title: '金额', dataIndex: 'amount', width: 96,
      render: (v: number, r: EditRow) => (
        <InputNumber size="small" value={v} step={0.01} style={{width: '100%'}}
          onChange={val => patchRow(r.key, {amount: val ?? 0})} />
      )},
    {title: '来源', dataIndex: 'source', width: 60,
      render: (v: string) => <Text type="secondary" style={{fontSize: 12}}>{v === 'ocr' ? 'OCR' : '手动'}</Text>},
    {title: '', width: 38,
      render: (_: unknown, r: EditRow) => (
        <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => removeRow(r.key)} />
      )},
  ];

  return (
    <Drawer title={editTarget ? '编辑复盘记录' : '新建复盘记录'} open={open} onClose={onClose} width={760}
      footer={
        <Space style={{justifyContent: 'flex-end', width: '100%'}}>
          {currentStep > 0 && <Button onClick={() => setCurrentStep(s => s - 1)}>上一步</Button>}
          {currentStep < 2 && <Button type="primary" onClick={() => setCurrentStep(s => s + 1)}>下一步</Button>}
          {currentStep === 2 && <Button type="primary" loading={saving} onClick={handleSave}>保存</Button>}
          <Button onClick={onClose}>取消</Button>
        </Space>
      }>
      <Steps current={currentStep} size="small" style={{marginBottom: 24}}
        items={[{title: '基础信息'}, {title: '成交明细'}, {title: '主观复盘'}]} />

      {/* Step 0：基础信息 + OCR */}
      <div style={{display: currentStep === 0 ? 'block' : 'none'}}>
        <Typography.Title level={5}>上传交易截图（可选）</Typography.Title>
        <Spin spinning={ocrLoading} tip="OCR 识别中…">
          <Upload.Dragger accept="image/*" showUploadList={false} beforeUpload={() => false}
            onChange={handleUpload} style={{marginBottom: 16}}>
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p>点击或拖拽同花顺交易截图，自动识别成交数据</p>
            <p style={{color: '#999', fontSize: 12}}>支持 JPG / PNG，识别后可人工校对</p>
          </Upload.Dragger>
        </Spin>
        {ocrError && <Alert type="error" message={ocrError} style={{marginBottom: 16}} />}
        <Form form={form} layout="vertical">
          <Space style={{flexWrap: 'wrap'}}>
            <Form.Item name="stock_name" label="股票名称" rules={[{required: true}]} style={{marginBottom: 8}}>
              <Input placeholder="如：卓郎智能" />
            </Form.Item>
            <Form.Item name="stock_code" label="股票代码" style={{marginBottom: 8}}>
              <StockSearchInput
                placeholder="代码/名称/拼音"
                style={{width: 180}}
                onSelectStock={(stock) => form.setFieldValue('stock_name', stock.stock_name)}
              />
            </Form.Item>
            <Form.Item name="start_date" label="建仓日期" rules={[{required: true}]} style={{marginBottom: 8}}>
              <DatePicker format="YYYY-MM-DD" />
            </Form.Item>
            <Form.Item name="end_date" label="清仓日期" style={{marginBottom: 8}}>
              <DatePicker format="YYYY-MM-DD" />
            </Form.Item>
            <Form.Item name="status" label="状态" initialValue="open" style={{marginBottom: 8}}>
              <Radio.Group>
                <Radio.Button value="open">持仓中</Radio.Button>
                <Radio.Button value="closed">已清仓</Radio.Button>
              </Radio.Group>
            </Form.Item>
          </Space>
        </Form>
      </div>

      {/* Step 1：成交明细 */}
      <div style={{display: currentStep === 1 ? 'block' : 'none'}}>
        <Space style={{marginBottom: 12, justifyContent: 'space-between', width: '100%'}}>
          <Typography.Title level={5} style={{margin: 0}}>成交明细</Typography.Title>
          <Button size="small" icon={<PlusOutlined />} onClick={addRow}>手动添加</Button>
        </Space>
        <Table size="small" dataSource={rows} columns={columns} rowKey="key"
          pagination={false} scroll={{x: 640}}
          locale={{emptyText: '暂无成交记录，可上传截图自动识别或手动添加'}} />
      </div>

      {/* Step 2：主观复盘 */}
      <div style={{display: currentStep === 2 ? 'block' : 'none'}}>
        <Form form={form} layout="vertical">
          <Form.Item name="entry_reason" label="建仓理由">
            <TextArea rows={3} placeholder="当时为什么建仓？板块逻辑、技术形态、消息面…" />
          </Form.Item>
          <Form.Item name="entry_expectation" label="建仓预期">
            <TextArea rows={2} placeholder="当时预期的走法是什么？" />
          </Form.Item>
          <Form.Item name="reflection_did_well" label="做对了什么">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="reflection_did_poorly" label="做错了什么">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="reflection_redo_plan" label="如果重来怎么做">
            <TextArea rows={2} />
          </Form.Item>
        </Form>
      </div>
    </Drawer>
  );
}
