// per-product FV process diagnostic: observed day-0 vs simulated p05/p50/p95 bands.
import Highcharts from 'highcharts';
import { ReactNode, useMemo } from 'react';
import { useActualColorScheme } from '../../hooks/use-actual-color-scheme.ts';
import { SimpleChart } from './MonteCarloComponents.tsx';

interface FvBands {
  timestamps: number[];
  band_p05: number[];
  band_p50: number[];
  band_p95: number[];
}

interface ObservedFv {
  timestamps: number[];
  fv: number[];
}

interface FvDiagnosticPanelProps {
  product: string;
  simulated?: FvBands;
  observed?: ObservedFv;
}

export function FvDiagnosticPanel({ product, simulated, observed }: FvDiagnosticPanelProps): ReactNode {
  const colorScheme = useActualColorScheme();

  const series = useMemo((): Highcharts.SeriesOptionsType[] => {
    const out: Highcharts.SeriesOptionsType[] = [];

    if (observed) {
      out.push({
        type: 'line',
        name: 'observed',
        color: 'rgb(230, 80, 80)',
        lineWidth: 2,
        dashStyle: 'Solid',
        marker: { enabled: false },
        data: observed.timestamps.map((t, i) => [t, observed.fv[i]]),
        zIndex: 3,
      });
    }

    if (simulated) {
      // shaded p05-p95 area
      out.push({
        type: 'arearange',
        name: 'sim p05-p95',
        color: 'rgba(80, 120, 200, 0.15)',
        lineWidth: 0,
        marker: { enabled: false },
        enableMouseTracking: false,
        data: simulated.timestamps.map((t, i) => [t, simulated.band_p05[i], simulated.band_p95[i]]),
        zIndex: 0,
      } as Highcharts.SeriesOptionsType);

      out.push({
        type: 'line',
        name: 'sim p50',
        color: 'rgb(80, 120, 200)',
        lineWidth: 2,
        dashStyle: 'ShortDash',
        marker: { enabled: false },
        data: simulated.timestamps.map((t, i) => [t, simulated.band_p50[i]]),
        zIndex: 2,
      });

      out.push({
        type: 'line',
        name: 'sim p05',
        color: 'rgba(80, 120, 200, 0.5)',
        lineWidth: 1,
        dashStyle: 'Dot',
        marker: { enabled: false },
        data: simulated.timestamps.map((t, i) => [t, simulated.band_p05[i]]),
        zIndex: 1,
      });

      out.push({
        type: 'line',
        name: 'sim p95',
        color: 'rgba(80, 120, 200, 0.5)',
        lineWidth: 1,
        dashStyle: 'Dot',
        marker: { enabled: false },
        data: simulated.timestamps.map((t, i) => [t, simulated.band_p95[i]]),
        zIndex: 1,
      });
    }

    return out;
  }, [observed, simulated, colorScheme]);

  if (series.length === 0) return null;

  return (
    <SimpleChart
      title={`${product} - FV process diagnostic`}
      subtitle="observed (red) vs simulated p05/p50/p95 (blue)"
      series={series}
      options={{
        xAxis: { title: { text: 'timestamp' } },
        yAxis: { title: { text: 'fair value' } },
        legend: { enabled: true },
      }}
    />
  );
}
