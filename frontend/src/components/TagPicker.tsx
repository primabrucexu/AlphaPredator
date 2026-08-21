import { PlusOutlined } from '@ant-design/icons'
import { AutoComplete, Button, Space } from 'antd'
import { useMemo, useState } from 'react'
import type { GlobalTag } from '../types'

interface TagPickerProps {
  catalog: GlobalTag[]
  excludedIds: number[]
  onAdd: (name: string) => void
  loading?: boolean
}

export default function TagPicker({ catalog, excludedIds, onAdd, loading }: TagPickerProps) {
  const [name, setName] = useState('')
  const excluded = useMemo(() => new Set(excludedIds), [excludedIds])
  const options = useMemo(() => catalog.filter(tag => !excluded.has(tag.id)).map(tag => ({ value: tag.name })), [catalog, excluded])
  const matches = options.filter(option => option.value.toLowerCase().startsWith(name.trim().toLowerCase()))
  const add = () => {
    const value = name.trim()
    if (!value) return
    onAdd(value)
    setName('')
  }
  return <Space.Compact>
    <AutoComplete
      allowClear
      value={name}
      options={options}
      onChange={setName}
      onSelect={value => { onAdd(value); setName('') }}
      onKeyDown={event => { if (event.key === 'Enter' && matches.length === 0) add() }}
      filterOption={(input, option) => (option?.value ?? '').toLowerCase().startsWith(input.trim().toLowerCase())}
      placeholder="选择或新建标签"
      maxLength={64}
      style={{ width: 150 }}
    />
    <Button icon={<PlusOutlined />} loading={loading} onClick={add} />
  </Space.Compact>
}
