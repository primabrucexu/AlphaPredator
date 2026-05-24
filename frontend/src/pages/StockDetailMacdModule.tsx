import {type StockIndicatorSeries} from '../lib/api';
import {InfoRow, PanelFloatCard} from './StockDetailPanelPrimitives';

function fmtNum(v: number | null | undefined, decimals = 2): string {
  return v != null ? v.toFixed(decimals) : '--';
}

export function StockDetailMacdModule({
  top,
  activeIdx,
  indicators,
  activeMacdHist,
  upColor,
  downColor,
  macdColors,
}: {
  top: string;
  activeIdx: number;
  indicators: StockIndicatorSeries;
  activeMacdHist: number | null | undefined;
  upColor: string;
  downColor: string;
  macdColors: { DIF: string; DEA: string };
}) {
  return (
    <PanelFloatCard top={top} title="MACD">
      <InfoRow
        items={[
          {label: 'DIF', value: fmtNum(indicators.macd_dif[activeIdx], 4), color: macdColors.DIF},
          {label: 'DEA', value: fmtNum(indicators.macd_dea[activeIdx], 4), color: macdColors.DEA},
          {
            label: 'MACD',
            value: fmtNum(activeMacdHist, 4),
            color: activeMacdHist != null && activeMacdHist >= 0 ? upColor : downColor,
          },
        ]}
      />
    </PanelFloatCard>
  );
}

