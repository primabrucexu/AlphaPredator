import {type CSSProperties, type ReactNode, useRef, useState} from 'react';
import {AutoComplete, Input, Spin} from 'antd';
import {SearchOutlined} from '@ant-design/icons';
import {useNavigate} from 'react-router-dom';
import {searchStocks, type StockCandidate} from '../lib/api';

interface StockSearchInputProps {
    value?: string;
    onChange?: (value: string) => void;
    onSelectStock?: (stock: StockCandidate) => void;
    style?: CSSProperties;
    inputSize?: 'small' | 'middle' | 'large';
    placeholder?: string;
}

interface StockSearchBarProps {
    style?: CSSProperties;
    inputSize?: 'small' | 'middle' | 'large';
    placeholder?: string;
}

export function StockSearchInput({
                                     value,
                                     onChange,
                                     onSelectStock,
                                     style,
                                     inputSize = 'middle',
                                     placeholder = '搜索股票代码或名称',
                                 }: StockSearchInputProps) {
    const [searching, setSearching] = useState(false);
    const [options, setOptions] = useState<{ value: string; label: ReactNode }[]>([]);
    const [lastCandidates, setLastCandidates] = useState<StockCandidate[]>([]);
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const triggerSearch = (value: string) => {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        const q = value.trim();
        if (!q) {
            setOptions([]);
            setLastCandidates([]);
            return;
        }
        debounceRef.current = setTimeout(async () => {
            setSearching(true);
            try {
                const candidates = await searchStocks(q.toUpperCase(), 10);
                setLastCandidates(candidates);
                setOptions(
                    candidates.map((c) => ({
                        value: c.stock_code,
                        label: (
                            <div style={{display: 'flex', justifyContent: 'space-between', gap: 8}}>
                                <span style={{fontWeight: 500}}>{c.stock_name}</span>
                                <span style={{color: '#8c8c8c', fontVariantNumeric: 'tabular-nums'}}>
                  {c.stock_code}
                </span>
                            </div>
                        ),
                    })),
                );
            } catch {
                setOptions([]);
            } finally {
                setSearching(false);
            }
        }, 250);
    };

    const handleSelect = (stockCode: string) => {
        setOptions([]);
        onChange?.(stockCode);
        const selected = lastCandidates.find((item) => item.stock_code === stockCode);
        if (selected) onSelectStock?.(selected);
    };

    const handleEnter = () => {
        const q = (value ?? '').trim();
        if (!q) return;
        if (lastCandidates.length === 1) {
            setOptions([]);
            onChange?.(lastCandidates[0].stock_code);
            onSelectStock?.(lastCandidates[0]);
        }
    };

    return (
        <AutoComplete
            style={{width: 280, ...style}}
            options={options}
            value={value}
            onChange={(val) => {
                onChange?.(val);
                triggerSearch(val);
            }}
            onSelect={handleSelect}
            notFoundContent={searching ? <Spin size="small"/> : null}
        >
            <Input
                size={inputSize}
                placeholder={placeholder}
                prefix={searching ? <Spin size="small"/> : <SearchOutlined/>}
                onPressEnter={handleEnter}
                allowClear
            />
        </AutoComplete>
    );
}

export function StockSearchBar({
                                   style,
                                   inputSize = 'middle',
                                   placeholder = '搜索股票代码或名称',
                               }: StockSearchBarProps) {
    const navigate = useNavigate();
    const [query, setQuery] = useState('');

    return (
        <StockSearchInput
            value={query}
            onChange={setQuery}
            onSelectStock={(stock) => {
                setQuery('');
                navigate(`/stocks/${stock.stock_code}`);
            }}
            style={style}
            inputSize={inputSize}
            placeholder={placeholder}
        />
    );
}
