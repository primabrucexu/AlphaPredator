import { SearchOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { AutoComplete, Input, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

export default function SearchBar() {
  const [value, setValue] = useState('')
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  useEffect(() => { const timer = setTimeout(() => setQuery(value.trim()), 250); return () => clearTimeout(timer) }, [value])
  const result = useQuery({ queryKey: ['stock-search', query], queryFn: () => api.searchStocks(query), enabled: query.length > 0 })
  const options = (result.data || []).map(stock => ({
    value: stock.symbol,
    label: <div className="search-option"><span>{stock.name}</span><Typography.Text type="secondary">{stock.symbol}</Typography.Text></div>,
  }))
  return <AutoComplete className="global-search" value={value} options={options} onSearch={setValue}
    onSelect={(symbol) => { setValue(''); navigate(`/stocks/${symbol}`) }} notFoundContent={query && !result.isFetching ? '未找到股票' : null}>
    <Input prefix={<SearchOutlined />} placeholder="代码 / 名称 / 拼音首字母" allowClear />
  </AutoComplete>
}
