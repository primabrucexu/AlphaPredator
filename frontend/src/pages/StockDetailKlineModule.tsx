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
  expmaColors,
}: {
  top: string;
  activeBar: DailyBar;
  activeIdx: number;
  activePriceColor: string;
  activeChangePct: number | null;
  indicators: StockIndicatorSeries;
  upColor: string;
  downColor: string;
  expmaColors: Record<'EXPMA8' | 'EXPMA17' | 'EXPMA21' | 'EXPMA55', string>;
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
          {label: 'EXPMA8', value: fmtNum(indicators.expma8[activeIdx]), color: expmaColors.EXPMA8},
          {label: 'EXPMA17', value: fmtNum(indicators.expma17[activeIdx]), color: expmaColors.EXPMA17},
          {label: 'EXPMA21', value: fmtNum(indicators.expma21[activeIdx]), color: expmaColors.EXPMA21},
          {label: 'EXPMA55', value: fmtNum(indicators.expma55[activeIdx]), color: expmaColors.EXPMA55},
        ]}
      />
    </PanelFloatCard>
  );
}

