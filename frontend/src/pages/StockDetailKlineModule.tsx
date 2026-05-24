import {type DailyBar, type StockIndicatorSeries} from '../lib/api';
import {InfoRow, PanelFloatCard} from './StockDetailPanelPrimitives';

function fmtNum(v: number | null | undefined, decimals = 2): string {
  return v != null ? v.toFixed(decimals) : '--';
}

function fmtSignedPct(v: number | null | undefined): string {
  if (v == null) return '--';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(2)}%`;
}

export function StockDetailKlineModule({
  top,
  activeBar,
  activeIdx,
  activePriceColor,
  activeChangePct,
  indicators,
  upColor,
  downColor,
  maColors,
}: {
  top: string;
  activeBar: DailyBar;
  activeIdx: number;
  activePriceColor: string;
  activeChangePct: number | null;
  indicators: StockIndicatorSeries;
  upColor: string;
  downColor: string;
  maColors: Record<'MA5' | 'MA10' | 'MA20' | 'MA60', string>;
}) {
  return (
    <PanelFloatCard top={top} title="K线">
      <InfoRow
        items={[
          {label: '日期', value: activeBar.trade_date},
          {label: '开', value: fmtNum(activeBar.open_price)},
          {label: '高', value: fmtNum(activeBar.high_price), color: upColor},
          {label: '低', value: fmtNum(activeBar.low_price), color: downColor},
          {label: '收', value: fmtNum(activeBar.close_price), color: activePriceColor},
          {label: '涨跌幅', value: fmtSignedPct(activeChangePct), color: activePriceColor},
        ]}
      />
      <InfoRow
        items={[
          {label: 'MA5', value: fmtNum(indicators.ma5[activeIdx]), color: maColors.MA5},
          {label: 'MA10', value: fmtNum(indicators.ma10[activeIdx]), color: maColors.MA10},
          {label: 'MA20', value: fmtNum(indicators.ma20[activeIdx]), color: maColors.MA20},
          {label: 'MA60', value: fmtNum(indicators.ma60[activeIdx]), color: maColors.MA60},
        ]}
      />
    </PanelFloatCard>
  );
}

