import { Badge, Container, Grid, Group, Select, Table, Text, Title } from '@mantine/core';
import axios from 'axios';
import Highcharts from 'highcharts';
import { ReactNode, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { MonteCarloDashboard } from '../../models.ts';
import { useStore } from '../../store.ts';
import { parseVisualizerInput } from '../../utils/algorithm.tsx';
import { formatNumber } from '../../utils/format.ts';
import { VisualizerCard } from '../visualizer/VisualizerCard.tsx';
import {
  buildBandChartSeries,
  distributionLineSeries,
  ErrorMonteCarloView,
  formatSlope,
  histogramSeries,
  lineSeries,
  LoadingMonteCarloView,
  normalFitSeries,
  SessionRankingTable,
  SimpleChart,
  SummaryTable,
} from './MonteCarloComponents.tsx';

function basename(path: string): string {
  const normalized = path.replace(/\\/g, '/');
  return normalized.split('/').filter(Boolean).pop() ?? path;
}

export function MonteCarloPage(): ReactNode {
  const storedDashboard = useStore(state => state.monteCarlo);
  const { search } = useLocation();
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [status, setStatus] = useState('Loading Monte Carlo dashboard');
  const [localDashboard, setLocalDashboard] = useState<MonteCarloDashboard | null>(null);
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);
  const [bandProduct, setBandProduct] = useState('TOMATOES');
  const searchParams = new URLSearchParams(search);
  const explicitOpenUrl = searchParams.get('open');
  const localFallbackOpenUrl =
    typeof window !== 'undefined' && ['localhost', '127.0.0.1'].includes(window.location.hostname)
      ? '/dashboard.json'
      : null;
  const openUrl = explicitOpenUrl ?? localFallbackOpenUrl;
  const dashboard = openUrl === null ? storedDashboard : loadedUrl === openUrl ? localDashboard : null;

  useEffect(() => {
    if (openUrl === null) {
      setLoadError(null);
      setStatus('Loading Monte Carlo dashboard');
      setLocalDashboard(null);
      setLoadedUrl(null);
      return;
    }

    if (openUrl.trim().length === 0) {
      return;
    }

    let cancelled = false;
    setLoadError(null);
    setStatus('Fetching dashboard');
    setLocalDashboard(null);
    setLoadedUrl(null);
    const load = async (): Promise<void> => {
      try {
        const response = await axios.get(openUrl);
        const parsed = parseVisualizerInput(response.data);

        if (cancelled) {
          return;
        }

        if (parsed.kind === 'monteCarlo') {
          setLocalDashboard(parsed.monteCarlo);
          setLoadedUrl(openUrl);
          setStatus('Dashboard loaded');
          return;
        }

        setLoadError(new Error('This visualizer build only supports Monte Carlo dashboard bundles.'));
      } catch (error) {
        if (cancelled) {
          return;
        }
        setLoadError(error as Error);
      }
    };

    load();

    return () => {
      cancelled = true;
    };
  }, [openUrl]);

  useEffect(() => {
    if (dashboard?.bandSeries?.[bandProduct] !== undefined) {
      return;
    }
    if (dashboard?.bandSeries !== undefined) {
      const fallback = Object.keys(dashboard.bandSeries)[0];
      if (fallback !== undefined) {
        setBandProduct(fallback);
      }
    }
  }, [bandProduct, dashboard]);

  if (dashboard === null) {
    if (loadError !== null) {
      return <ErrorMonteCarloView error={loadError} />;
    }

    if (openUrl !== null) {
      return <LoadingMonteCarloView status={status} />;
    }
    return <LoadingMonteCarloView status={status} />;
  }

  const strategyName = basename(dashboard.meta.algorithmPath);
  const totalTrend = dashboard.trendFits.TOTAL;
  const emeraldTrend = dashboard.trendFits.EMERALDS;
  const tomatoTrend = dashboard.trendFits.TOMATOES;
  const scatterFit = dashboard.scatterFit;
  const selectedBandSeries = dashboard.bandSeries?.[bandProduct];
  const bandOptions = Object.keys(dashboard.bandSeries ?? {}).map(product => ({ value: product, label: product }));

  const totalHistogramSeries: Highcharts.SeriesOptionsType[] = [
    histogramSeries(dashboard.histograms.totalPnl, 'Total PnL', '#4c6ef5'),
    normalFitSeries(dashboard.normalFits.totalPnl),
  ];
  const emeraldHistogramSeries: Highcharts.SeriesOptionsType[] = [
    histogramSeries(dashboard.histograms.emeraldPnl, 'EMERALDS PnL', '#12b886'),
    normalFitSeries(dashboard.normalFits.emeraldPnl),
  ];
  const tomatoHistogramSeries: Highcharts.SeriesOptionsType[] = [
    histogramSeries(dashboard.histograms.tomatoPnl, 'TOMATOES PnL', '#fd7e14'),
    normalFitSeries(dashboard.normalFits.tomatoPnl),
  ];
  const scatterSeries: Highcharts.SeriesOptionsType[] = [
    {
      type: 'scatter',
      name: 'Sessions',
      color: '#4c6ef5',
      data: dashboard.sessions.map(row => [row.emeraldPnl, row.tomatoPnl]),
    },
    {
      type: 'line',
      name: 'Linear fit',
      color: '#fa5252',
      lineWidth: 2,
      data: scatterFit.line,
    },
  ];
  const profitabilitySeries: Highcharts.SeriesOptionsType[] = [
    distributionLineSeries(dashboard.histograms.totalProfitability, 'Total', '#4c6ef5'),
    distributionLineSeries(dashboard.histograms.emeraldProfitability, 'EMERALDS', '#12b886'),
    distributionLineSeries(dashboard.histograms.tomatoProfitability, 'TOMATOES', '#fd7e14'),
  ];
  const stabilitySeries: Highcharts.SeriesOptionsType[] = [
    distributionLineSeries(dashboard.histograms.totalStability, 'Total', '#4c6ef5'),
    distributionLineSeries(dashboard.histograms.emeraldStability, 'EMERALDS', '#12b886'),
    distributionLineSeries(dashboard.histograms.tomatoStability, 'TOMATOES', '#fd7e14'),
  ];

  return (
    <Container fluid py="md">
      <Grid>
        <Grid.Col span={12}>
          <VisualizerCard>
            <Group justify="space-between" align="flex-start">
              <div>
                <Title order={2}>Monte Carlo Results</Title>
                <Text c="dimmed">{strategyName}</Text>
              </div>
              <Group gap="xs">
                <Badge variant="light">{dashboard.meta.sessionCount} sessions</Badge>
                <Badge variant="light">{dashboard.meta.bandSessionCount ?? dashboard.meta.sampleSessions} path traces</Badge>
                <Badge variant="light">{dashboard.meta.fvMode}</Badge>
                <Badge variant="light">{dashboard.meta.tradeMode}</Badge>
              </Group>
            </Group>
          </VisualizerCard>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 6 }}>
          <VisualizerCard title="Mean Total PnL">
            <Title order={2}>{formatNumber(dashboard.overall.totalPnl.mean)}</Title>
            <Text c="dimmed" size="sm">
              95% mean CI {formatNumber(dashboard.overall.totalPnl.meanConfidenceLow95)} to{' '}
              {formatNumber(dashboard.overall.totalPnl.meanConfidenceHigh95)}
            </Text>
          </VisualizerCard>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <VisualizerCard title="Total PnL 1σ">
            <Title order={2}>{formatNumber(dashboard.overall.totalPnl.std)}</Title>
            <Text c="dimmed" size="sm">
              P05 {formatNumber(dashboard.overall.totalPnl.p05)} · P95 {formatNumber(dashboard.overall.totalPnl.p95)}
            </Text>
          </VisualizerCard>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 8 }}>
          <VisualizerCard title="Profitability And Statistics">
            <Table striped withTableBorder withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Metric</Table.Th>
                  <Table.Th>Meaning</Table.Th>
                  <Table.Th>Total</Table.Th>
                  <Table.Th>EMERALDS</Table.Th>
                  <Table.Th>TOMATOES</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                <Table.Tr>
                  <Table.Td>Profitability</Table.Td>
                  <Table.Td>Mean fitted MTM slope in dollars per step.</Table.Td>
                  <Table.Td>{formatSlope(totalTrend.profitability.mean)}</Table.Td>
                  <Table.Td>{formatSlope(emeraldTrend.profitability.mean)}</Table.Td>
                  <Table.Td>{formatSlope(tomatoTrend.profitability.mean)}</Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>Stability</Table.Td>
                  <Table.Td>Mean linear-fit R². Higher means steadier PnL paths.</Table.Td>
                  <Table.Td>{formatNumber(totalTrend.stability.mean, 3)}</Table.Td>
                  <Table.Td>{formatNumber(emeraldTrend.stability.mean, 3)}</Table.Td>
                  <Table.Td>{formatNumber(tomatoTrend.stability.mean, 3)}</Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>Profitability 1σ</Table.Td>
                  <Table.Td>Cross-session spread of profitability.</Table.Td>
                  <Table.Td>{formatSlope(totalTrend.profitability.std)}</Table.Td>
                  <Table.Td>{formatSlope(emeraldTrend.profitability.std)}</Table.Td>
                  <Table.Td>{formatSlope(tomatoTrend.profitability.std)}</Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>Stability 1σ</Table.Td>
                  <Table.Td>Cross-session spread of stability.</Table.Td>
                  <Table.Td>{formatNumber(totalTrend.stability.std, 3)}</Table.Td>
                  <Table.Td>{formatNumber(emeraldTrend.stability.std, 3)}</Table.Td>
                  <Table.Td>{formatNumber(tomatoTrend.stability.std, 3)}</Table.Td>
                </Table.Tr>
              </Table.Tbody>
            </Table>
          </VisualizerCard>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 4 }}>
          <VisualizerCard title="Fair Value Models">
            <Table withTableBorder withColumnBorders>
              <Table.Tbody>
                <Table.Tr>
                  <Table.Td>EMERALDS</Table.Td>
                  <Table.Td>
                    <Text fw={500}>{dashboard.generatorModel.EMERALDS.formula}</Text>
                    <Text size="sm" c="dimmed">
                      {dashboard.generatorModel.EMERALDS.notes[0]}
                    </Text>
                  </Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>TOMATOES</Table.Td>
                  <Table.Td>
                    <Text fw={500}>{dashboard.generatorModel.TOMATOES.formula}</Text>
                    <Text size="sm" c="dimmed">
                      {dashboard.generatorModel.TOMATOES.notes[0]}
                    </Text>
                  </Table.Td>
                </Table.Tr>
              </Table.Tbody>
            </Table>
          </VisualizerCard>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <SummaryTable title="Total PnL Summary" stats={dashboard.overall.totalPnl} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <SummaryTable title="EMERALDS PnL Summary" stats={dashboard.products.EMERALDS.pnl} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <SummaryTable title="TOMATOES PnL Summary" stats={dashboard.products.TOMATOES.pnl} />
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 6 }}>
          <SimpleChart
            title="Total PnL Distribution"
            subtitle={`Normal fit μ ${formatNumber(dashboard.normalFits.totalPnl.mean)} · σ ${formatNumber(dashboard.normalFits.totalPnl.std)} · R² ${formatNumber(dashboard.normalFits.totalPnl.r2, 3)}`}
            series={totalHistogramSeries}
            options={{
              xAxis: { title: { text: 'Final total pnl' } },
              yAxis: { title: { text: 'Session count' } },
            }}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <SimpleChart
            title="Cross Product Scatter"
            subtitle={`corr ${formatNumber(scatterFit.correlation, 3)} · fit R² ${formatNumber(scatterFit.r2, 3)} · ${scatterFit.diagnosis}`}
            series={scatterSeries}
            options={{
              xAxis: { title: { text: 'EMERALDS pnl' } },
              yAxis: { title: { text: 'TOMATOES pnl' } },
            }}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <SimpleChart
            title="EMERALDS PnL Distribution"
            subtitle={`Normal fit μ ${formatNumber(dashboard.normalFits.emeraldPnl.mean)} · σ ${formatNumber(dashboard.normalFits.emeraldPnl.std)} · R² ${formatNumber(dashboard.normalFits.emeraldPnl.r2, 3)}`}
            series={emeraldHistogramSeries}
            options={{
              xAxis: { title: { text: 'EMERALDS final pnl' } },
              yAxis: { title: { text: 'Session count' } },
            }}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <SimpleChart
            title="TOMATOES PnL Distribution"
            subtitle={`Normal fit μ ${formatNumber(dashboard.normalFits.tomatoPnl.mean)} · σ ${formatNumber(dashboard.normalFits.tomatoPnl.std)} · R² ${formatNumber(dashboard.normalFits.tomatoPnl.r2, 3)}`}
            series={tomatoHistogramSeries}
            options={{
              xAxis: { title: { text: 'TOMATOES final pnl' } },
              yAxis: { title: { text: 'Session count' } },
            }}
          />
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 6 }}>
          <SimpleChart
            title="Profitability Distribution"
            subtitle="Per-session fitted MTM slope in dollars per step"
            series={profitabilitySeries}
            options={{
              xAxis: {
                title: { text: '$ / step' },
                labels: {
                  formatter(this: Highcharts.AxisLabelsFormatterContextObject) {
                    return formatNumber(Number(this.value), 4);
                  },
                },
              },
              yAxis: { title: { text: 'Density proxy' } },
            }}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <SimpleChart
            title="Stability Distribution"
            subtitle="Per-session linear-fit R²"
            series={stabilitySeries}
            options={{
              xAxis: {
                title: { text: 'R²' },
                labels: {
                  formatter(this: Highcharts.AxisLabelsFormatterContextObject) {
                    return formatNumber(Number(this.value), 3);
                  },
                },
              },
              yAxis: { title: { text: 'Density proxy' } },
            }}
          />
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 6 }}>
          <SessionRankingTable title="Best Sessions" rows={dashboard.topSessions} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <SessionRankingTable title="Worst Sessions" rows={dashboard.bottomSessions} />
        </Grid.Col>

        {selectedBandSeries && (
          <>
            <Grid.Col span={12}>
              <VisualizerCard title="Path Boards">
                <Group justify="space-between" align="center">
                  <Text c="dimmed" size="sm">
                    Mean path with ±1σ and ±3σ bands across {dashboard.meta.bandSessionCount ?? dashboard.meta.sampleSessions} sessions.
                  </Text>
                  <Select
                    w={220}
                    data={bandOptions}
                    value={bandProduct}
                    onChange={value => setBandProduct(value ?? 'EMERALDS')}
                    allowDeselect={false}
                  />
                </Group>
              </VisualizerCard>
            </Grid.Col>
            <Grid.Col span={12}>
              <SimpleChart
                title={`${bandProduct} Fair Value`}
                series={buildBandChartSeries(selectedBandSeries.fair, bandProduct === 'EMERALDS' ? '#12b886' : '#fd7e14')}
                options={{
                  xAxis: {
                    title: { text: 'Step' },
                  },
                  yAxis: { title: { text: 'Fair value' } },
                }}
              />
            </Grid.Col>
            <Grid.Col span={12}>
              <SimpleChart
                title={`${bandProduct} MTM PnL`}
                series={[
                  ...buildBandChartSeries(selectedBandSeries.mtmPnl, bandProduct === 'EMERALDS' ? '#12b886' : '#fd7e14'),
                  lineSeries('Zero', '#868e96', selectedBandSeries.mtmPnl.timestamps, selectedBandSeries.mtmPnl.timestamps.map(() => 0), 'ShortDash'),
                ]}
                options={{
                  xAxis: {
                    title: { text: 'Step' },
                  },
                  yAxis: { title: { text: 'MTM pnl' } },
                }}
              />
            </Grid.Col>
            <Grid.Col span={12}>
              <SimpleChart
                title={`${bandProduct} Position`}
                series={[
                  ...buildBandChartSeries(selectedBandSeries.position, bandProduct === 'EMERALDS' ? '#12b886' : '#fd7e14'),
                  lineSeries('Zero', '#868e96', selectedBandSeries.position.timestamps, selectedBandSeries.position.timestamps.map(() => 0), 'ShortDash'),
                ]}
                options={{
                  xAxis: {
                    title: { text: 'Step' },
                  },
                  yAxis: { title: { text: 'Position' } },
                }}
              />
            </Grid.Col>
          </>
        )}
      </Grid>
    </Container>
  );
}
