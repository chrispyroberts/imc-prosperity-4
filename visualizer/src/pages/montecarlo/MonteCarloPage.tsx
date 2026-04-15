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
import { DroOverlay } from './DroOverlay.tsx';
import { FvDiagnosticPanel } from './FvDiagnosticPanel.tsx';
import { PositionTrajectoryPanel } from './PositionTrajectoryPanel.tsx';

// stable color palette indexed by product position
const PRODUCT_COLORS = ['#12b886', '#fd7e14', '#4c6ef5', '#e64980', '#fab005', '#7950f2'];

function productColor(index: number): string {
  return PRODUCT_COLORS[index % PRODUCT_COLORS.length];
}

function basename(path: string): string {
  const normalized = path.replace(/\\/g, '/');
  return normalized.split('/').filter(Boolean).pop() ?? path;
}

function withVersion(url: string, version: string | null): string {
  if (version === null || version.length === 0) {
    return url;
  }

  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}v=${encodeURIComponent(version)}`;
}

type LocalDashboardStatus = {
  dashboardExists: boolean;
  dashboardMtimeMs: number | null;
  dashboardSizeBytes: number | null;
  root: string;
  currentRunId?: string | null;
  runs?: Array<{
    id: string;
    label: string;
    mtimeMs: number;
    dashboardUrl: string;
  }>;
};

export function MonteCarloPage(): ReactNode {
  const storedDashboard = useStore(state => state.monteCarlo);
  const { search } = useLocation();
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [status, setStatus] = useState('Loading Monte Carlo dashboard');
  const [localDashboard, setLocalDashboard] = useState<MonteCarloDashboard | null>(null);
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);
  const [dashboardVersion, setDashboardVersion] = useState<string | null>(null);
  const [availableRuns, setAvailableRuns] = useState<
    Array<{
      id: string;
      label: string;
      mtimeMs: number;
      dashboardUrl: string;
    }>
  >([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('latest');
  const [bandProduct, setBandProduct] = useState<string | null>(null);
  const searchParams = new URLSearchParams(search);
  const explicitOpenUrl = searchParams.get('open');
  const localMode = typeof window !== 'undefined' && ['localhost', '127.0.0.1'].includes(window.location.hostname);
  const latestRun = availableRuns[0] ?? null;
  const selectedRun =
    selectedRunId === 'latest'
      ? latestRun
      : availableRuns.find(run => run.id === selectedRunId) ?? latestRun;
  const localFallbackOpenUrl = localMode ? selectedRun?.dashboardUrl ?? '/dashboard.json' : null;
  const localStatusUrl = localMode ? '/__prosperity4mcbt__/status.json' : null;
  const openUrl = explicitOpenUrl ?? localFallbackOpenUrl;
  const effectiveOpenUrl = openUrl === null ? null : withVersion(openUrl, explicitOpenUrl === null ? dashboardVersion : null);
  const dashboard = effectiveOpenUrl === null ? storedDashboard : loadedUrl === effectiveOpenUrl ? localDashboard : null;

  useEffect(() => {
    if (localStatusUrl === null || explicitOpenUrl !== null) {
      return;
    }

    let cancelled = false;
    let previousVersion: string | null = null;

    const poll = async (): Promise<void> => {
      try {
        const response = await axios.get<LocalDashboardStatus>(localStatusUrl, {
          headers: {
            'Cache-Control': 'no-cache',
            Pragma: 'no-cache',
          },
        });

        if (cancelled) {
          return;
        }

        const runs = response.data.runs ?? [];
        setAvailableRuns(runs);

        if (runs.length === 0) {
          setSelectedRunId('latest');
        } else {
          setSelectedRunId(previous => {
            if (previous === 'latest') {
              return 'latest';
            }
            return runs.some(run => run.id === previous) ? previous : 'latest';
          });
        }

        if (!response.data.dashboardExists || response.data.dashboardMtimeMs === null) {
          setLocalDashboard(null);
          setLoadedUrl(null);
          setDashboardVersion(null);
          return;
        }

        const currentRun =
          response.data.currentRunId === undefined || response.data.currentRunId === null
            ? runs[0]
            : runs.find(run => run.id === response.data.currentRunId) ?? runs[0];
        const selectedForVersion = selectedRunId === 'latest' ? currentRun : runs.find(run => run.id === selectedRunId) ?? currentRun;
        const nextVersion = selectedForVersion === undefined ? String(response.data.dashboardMtimeMs) : String(selectedForVersion.mtimeMs);
        if (previousVersion !== nextVersion) {
          previousVersion = nextVersion;
          setDashboardVersion(nextVersion);
        }
      } catch {
        if (!cancelled) {
          setStatus('Waiting for local dashboard');
        }
      }
    };

    void poll();
    const interval = window.setInterval(() => {
      void poll();
    }, 1500);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [explicitOpenUrl, localStatusUrl, selectedRunId]);

  useEffect(() => {
    if (effectiveOpenUrl === null) {
      setLoadError(null);
      setStatus('Loading Monte Carlo dashboard');
      setLocalDashboard(null);
      setLoadedUrl(null);
      return;
    }

    if (effectiveOpenUrl.trim().length === 0) {
      return;
    }

    let cancelled = false;
    setLoadError(null);
    setStatus('Fetching dashboard');
    setLocalDashboard(null);
    setLoadedUrl(null);
    const load = async (): Promise<void> => {
      try {
        const response = await axios.get(effectiveOpenUrl, {
          headers: {
            'Cache-Control': 'no-cache',
            Pragma: 'no-cache',
          },
        });
        const parsed = parseVisualizerInput(response.data);

        if (cancelled) {
          return;
        }

        if (parsed.kind === 'monteCarlo') {
          setLocalDashboard(parsed.monteCarlo);
          setLoadedUrl(effectiveOpenUrl);
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
  }, [effectiveOpenUrl]);

  // sync bandProduct when dashboard changes
  useEffect(() => {
    if (dashboard === null) {
      return;
    }
    const bandKeys = Object.keys(dashboard.bandSeries ?? {});
    if (bandKeys.length === 0) {
      return;
    }
    setBandProduct(prev => {
      if (prev !== null && bandKeys.includes(prev)) {
        return prev;
      }
      return bandKeys[0];
    });
  }, [dashboard]);

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
  const scatterFit = dashboard.scatterFit;

  // derive product list from dashboard
  const productNames = dashboard.productNames ?? Object.keys(dashboard.products);

  // per-product trend fits (excluding TOTAL)
  const productTrendFits = productNames.map(name => dashboard.trendFits[name]).filter(Boolean);

  const selectedBandSeries = bandProduct !== null ? dashboard.bandSeries?.[bandProduct] : undefined;
  const bandOptions = Object.keys(dashboard.bandSeries ?? {}).map(product => ({ value: product, label: product }));
  const activeBandProduct = bandProduct ?? bandOptions[0]?.value ?? '';

  const totalHistogramSeries: Highcharts.SeriesOptionsType[] = [
    histogramSeries(dashboard.histograms.totalPnl, 'Total PnL', '#4c6ef5'),
    normalFitSeries(dashboard.normalFits.totalPnl),
  ];

  const scatterSeries: Highcharts.SeriesOptionsType[] = [
    {
      type: 'scatter',
      name: 'Sessions',
      color: '#4c6ef5',
      data: dashboard.sessions.map(row => {
        if (productNames.length >= 2) {
          const p0 = row.perProductPnl?.[productNames[0]] ?? 0;
          const p1 = row.perProductPnl?.[productNames[1]] ?? 0;
          return [p0, p1];
        }
        return [row.emeraldPnl, row.tomatoPnl];
      }),
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
    distributionLineSeries(dashboard.histograms.totalProfitability, 'Total', '#4c6ef5') as Highcharts.SeriesOptionsType,
    ...productNames.flatMap((name, i) => {
      const hist = dashboard.perProductHistograms?.[name]?.profitability
        ?? dashboard.histograms[`${name.toLowerCase().replace(/s$/, '')}Profitability`];
      return hist ? [distributionLineSeries(hist, name, productColor(i)) as Highcharts.SeriesOptionsType] : [];
    }),
  ];

  const stabilitySeries: Highcharts.SeriesOptionsType[] = [
    distributionLineSeries(dashboard.histograms.totalStability, 'Total', '#4c6ef5') as Highcharts.SeriesOptionsType,
    ...productNames.flatMap((name, i) => {
      const hist = dashboard.perProductHistograms?.[name]?.stability
        ?? dashboard.histograms[`${name.toLowerCase().replace(/s$/, '')}Stability`];
      return hist ? [distributionLineSeries(hist, name, productColor(i)) as Highcharts.SeriesOptionsType] : [];
    }),
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
              <Group gap="xs" align="flex-start">
                {explicitOpenUrl === null && localMode && availableRuns.length > 0 && (
                  <Select
                    w={260}
                    label="Run"
                    value={selectedRunId}
                    onChange={value => setSelectedRunId(value ?? 'latest')}
                    allowDeselect={false}
                    data={[
                      {
                        value: 'latest',
                        label: `Latest (${latestRun?.label ?? 'none'})`,
                      },
                      ...availableRuns.map(run => ({
                        value: run.id,
                        label: run.label,
                      })),
                    ]}
                  />
                )}
                <Badge variant="light">{dashboard.meta.sessionCount} sessions</Badge>
                <Badge variant="light">{dashboard.meta.bandSessionCount ?? dashboard.meta.sampleSessions} path traces</Badge>
                <Badge variant="light">{dashboard.meta.fvMode}</Badge>
                <Badge variant="light">{dashboard.meta.tradeMode}</Badge>
              </Group>
            </Group>
          </VisualizerCard>
        </Grid.Col>

        {dashboard.droReport && (
          <Grid.Col span={12}>
            <DroOverlay report={dashboard.droReport} />
          </Grid.Col>
        )}

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
                  {productNames.map(name => (
                    <Table.Th key={name}>{name}</Table.Th>
                  ))}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                <Table.Tr>
                  <Table.Td>Profitability</Table.Td>
                  <Table.Td>Mean fitted MTM slope in dollars per step.</Table.Td>
                  <Table.Td>{formatSlope(totalTrend.profitability.mean)}</Table.Td>
                  {productTrendFits.map((trend, i) => (
                    <Table.Td key={productNames[i]}>{formatSlope(trend.profitability.mean)}</Table.Td>
                  ))}
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>Stability</Table.Td>
                  <Table.Td>Mean linear-fit R². Higher means steadier PnL paths.</Table.Td>
                  <Table.Td>{formatNumber(totalTrend.stability.mean, 3)}</Table.Td>
                  {productTrendFits.map((trend, i) => (
                    <Table.Td key={productNames[i]}>{formatNumber(trend.stability.mean, 3)}</Table.Td>
                  ))}
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>Profitability 1σ</Table.Td>
                  <Table.Td>Cross-session spread of profitability.</Table.Td>
                  <Table.Td>{formatSlope(totalTrend.profitability.std)}</Table.Td>
                  {productTrendFits.map((trend, i) => (
                    <Table.Td key={productNames[i]}>{formatSlope(trend.profitability.std)}</Table.Td>
                  ))}
                </Table.Tr>
                <Table.Tr>
                  <Table.Td>Stability 1σ</Table.Td>
                  <Table.Td>Cross-session spread of stability.</Table.Td>
                  <Table.Td>{formatNumber(totalTrend.stability.std, 3)}</Table.Td>
                  {productTrendFits.map((trend, i) => (
                    <Table.Td key={productNames[i]}>{formatNumber(trend.stability.std, 3)}</Table.Td>
                  ))}
                </Table.Tr>
              </Table.Tbody>
            </Table>
          </VisualizerCard>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 4 }}>
          <VisualizerCard title="Fair Value Models">
            <Table withTableBorder withColumnBorders>
              <Table.Tbody>
                {Object.entries(dashboard.generatorModel).map(([name, model]) => (
                  <Table.Tr key={name}>
                    <Table.Td>{name}</Table.Td>
                    <Table.Td>
                      <Text fw={500}>{model.formula}</Text>
                      <Text size="sm" c="dimmed">
                        {model.notes[0]}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </VisualizerCard>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <SummaryTable title="Total PnL Summary" stats={dashboard.overall.totalPnl} />
        </Grid.Col>
        {productNames.map(name => (
          <Grid.Col key={name} span={{ base: 12, md: 4 }}>
            <SummaryTable title={`${name} PnL Summary`} stats={dashboard.products[name].pnl} />
          </Grid.Col>
        ))}

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
        {productNames.length >= 2 && (
          <Grid.Col span={{ base: 12, md: 6 }}>
            <SimpleChart
              title="Cross Product Scatter"
              subtitle={`corr ${formatNumber(scatterFit.correlation, 3)} · fit R² ${formatNumber(scatterFit.r2, 3)} · ${scatterFit.diagnosis}`}
              series={scatterSeries}
              options={{
                xAxis: { title: { text: `${productNames[0]} pnl` } },
                yAxis: { title: { text: `${productNames[1]} pnl` } },
              }}
            />
          </Grid.Col>
        )}

        {productNames.map((name, i) => {
          const perProductHist = dashboard.perProductHistograms?.[name];
          const perProductNorm = dashboard.perProductNormalFits?.[name];
          if (perProductHist === undefined || perProductNorm === undefined) {
            return null;
          }
          const color = productColor(i);
          const series: Highcharts.SeriesOptionsType[] = [
            histogramSeries(perProductHist.pnl, `${name} PnL`, color),
            normalFitSeries(perProductNorm),
          ];
          return (
            <Grid.Col key={name} span={{ base: 12, md: 6 }}>
              <SimpleChart
                title={`${name} PnL Distribution`}
                subtitle={`Normal fit μ ${formatNumber(perProductNorm.mean)} · σ ${formatNumber(perProductNorm.std)} · R² ${formatNumber(perProductNorm.r2, 3)}`}
                series={series}
                options={{
                  xAxis: { title: { text: `${name} final pnl` } },
                  yAxis: { title: { text: 'Session count' } },
                }}
              />
            </Grid.Col>
          );
        })}

        {productNames.map(name => {
          const simulated = dashboard.perProductFvBands?.[name];
          const observed = dashboard.perProductObservedFv?.[name];
          if (!simulated && !observed) return null;
          return (
            <Grid.Col key={`fv-diag-${name}`} span={12}>
              <FvDiagnosticPanel product={name} simulated={simulated} observed={observed} />
            </Grid.Col>
          );
        })}

        {productNames.map(name => {
          const paths = dashboard.perProductPositionPaths?.[name];
          if (!paths || paths.length === 0) return null;
          return (
            <Grid.Col key={`pos-traj-${name}`} span={12}>
              <PositionTrajectoryPanel product={name} paths={paths} />
            </Grid.Col>
          );
        })}

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
          <SessionRankingTable title="Best Sessions" rows={dashboard.topSessions} productNames={productNames} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <SessionRankingTable title="Worst Sessions" rows={dashboard.bottomSessions} productNames={productNames} />
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
                    value={activeBandProduct}
                    onChange={value => setBandProduct(value ?? bandOptions[0]?.value ?? '')}
                    allowDeselect={false}
                  />
                </Group>
              </VisualizerCard>
            </Grid.Col>
            <Grid.Col span={12}>
              <SimpleChart
                title={`${activeBandProduct} Fair Value`}
                series={buildBandChartSeries(selectedBandSeries.fair, productColor(productNames.indexOf(activeBandProduct)))}
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
                title={`${activeBandProduct} MTM PnL`}
                series={[
                  ...buildBandChartSeries(selectedBandSeries.mtmPnl, productColor(productNames.indexOf(activeBandProduct))),
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
                title={`${activeBandProduct} Position`}
                series={[
                  ...buildBandChartSeries(selectedBandSeries.position, productColor(productNames.indexOf(activeBandProduct))),
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
