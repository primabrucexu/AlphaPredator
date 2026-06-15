import {type DailyBar, type StockIndicatorSeries} from '../lib/api';
import {InfoRow, PanelFloatCard} from './StockDetailPanelPrimitives';

function fmtNum(v: number | null | undefined, decimals = 2): string {
  return v != null ? v.toFixed(decimals) : '--';
}

function fmtVol(v: number): string {
  return v >= 1e8 ? `${(v / 1e8).toFixed(2)}亿手` : `${(v / 1e4).toFixed(0)}万手`;
}

const QIANYUAN_PER_YI = 100_000;

function fmtAmount(v: number | null | undefined): string {
  return v != null ? `${(v / QIANYUAN_PER_YI).toFixed(2)}亿` : '--';
}

function fmtPct(v: number | null | undefined): string {
  return v != null ? `${v.toFixed(2)}%` : '--';
}

export function StockDetailVolumeModule({
  top,
  activeBar,
  activeIdx,
  activePriceColor,
  indicators,
  expmaColors,
}: {
  top: string;
  activeBar: DailyBar;
  activeIdx: number;
  activePriceColor: string;
  indicators: StockIndicatorSeries;
  expmaColors: Record<'EXPMA8' | 'EXPMA17' | 'EXPMA21' | 'EXPMA55', string>;
}) {
  return (
    <PanelFloatCard top={top} title="VOL">
      <InfoRow
        items={[
          {label: 'VOL', value: fmtVol(activeBar.volume), color: activePriceColor},
          {label: '额', value: fmtAmount(activeBar.turnover_amount_billion)},
          {label: '换手', value: fmtPct(activeBar.turnover_rate)},
        ]}
      />
      <InfoRow
        items={[
          {label: 'MA5', value: fmtNum(indicators.volume_ma5[activeIdx]), color: expmaColors.EXPMA8},
          {label: 'MA10', value: fmtNum(indicators.volume_ma10[activeIdx]), color: expmaColors.EXPMA17},
          {label: 'MA20', value: fmtNum(indicators.volume_ma20[activeIdx]), color: expmaColors.EXPMA21},
        ]}
      />
    </PanelFloatCard>
  );
}

