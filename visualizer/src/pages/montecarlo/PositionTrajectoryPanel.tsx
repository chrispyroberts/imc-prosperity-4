// per-product position path overlay across sample sessions.
import Highcharts from 'highcharts';
import HighchartsReact from 'highcharts-react-official';
import { Card, Text } from '@mantine/core';
import type { PositionPath } from '../../models';

export function PositionTrajectoryPanel({
  product,
  paths,
}: {
  product: string;
  paths: PositionPath[];
}) {
  if (!paths || paths.length === 0) return null;

  const series: Highcharts.SeriesOptionsType[] = paths.map((path, i) => ({
    name: `session ${i}`,
    type: 'line' as const,
    data: path.timestamps.map((t, j) => [t, path.position[j]]),
    color: `rgba(80, 120, 200, ${0.25 + 0.05 * (i % 10)})`,
    lineWidth: 1,
    marker: { enabled: false },
    showInLegend: false,
    enableMouseTracking: false,
  }));

  const options: Highcharts.Options = {
    chart: { height: 220, animation: false, backgroundColor: 'transparent' },
    title: { text: undefined },
    xAxis: { title: { text: 'timestamp' } },
    yAxis: { title: { text: 'position' } },
    legend: { enabled: false },
    credits: { enabled: false },
    tooltip: { enabled: false },
    series,
  };

  return (
    <Card withBorder mb="md">
      <Text fw={600} size="sm" mb="xs">
        {product} - position trajectory ({paths.length} sessions)
      </Text>
      <HighchartsReact highcharts={Highcharts} options={options} />
    </Card>
  );
}
