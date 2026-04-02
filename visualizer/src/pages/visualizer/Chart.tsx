import Highcharts from 'highcharts/highstock';
import HighchartsMore from 'highcharts/highcharts-more';
import HighchartsAccessibility from 'highcharts/modules/accessibility';
import HighchartsExporting from 'highcharts/modules/exporting';
import HighchartsOfflineExporting from 'highcharts/modules/offline-exporting';
import HighchartsHighContrastDarkTheme from 'highcharts/themes/high-contrast-dark';
import HighchartsReact from 'highcharts-react-official';
import merge from 'lodash/merge';
import { ReactNode, useMemo } from 'react';
import { useActualColorScheme } from '../../hooks/use-actual-color-scheme.ts';
import { formatNumber } from '../../utils/format.ts';
import { VisualizerCard } from './VisualizerCard.tsx';

HighchartsAccessibility(Highcharts);
HighchartsExporting(Highcharts);
HighchartsOfflineExporting(Highcharts);
HighchartsMore(Highcharts);

// Highcharts themes are distributed as Highcharts extensions
// The normal way to use them is to apply these extensions to the global Highcharts object
// However, themes work by overriding the default options, with no way to rollback
// To make theme switching work, we merge theme options into the local chart options instead
// This way we don't override the global defaults and can change themes without refreshing
// This function is a little workaround to be able to get the options a theme overrides
function getThemeOptions(theme: (highcharts: typeof Highcharts) => void): Highcharts.Options {
  const highchartsMock = {
    _modules: {
      'Core/Globals.js': {
        theme: null,
      },
      'Core/Defaults.js': {
        setOptions: () => {
          // Do nothing
        },
      },
    },
    win: {
      dispatchEvent: () => {},
    },
  };

  theme(highchartsMock as any);

  return highchartsMock._modules['Core/Globals.js'].theme! as Highcharts.Options;
}

interface ChartProps {
  title: string;
  options?: Highcharts.Options;
  series: Highcharts.SeriesOptionsType[];
  min?: number;
  max?: number;
}

export function Chart({ title, options, series, min, max }: ChartProps): ReactNode {
  const colorScheme = useActualColorScheme();
  const axisTextColor = colorScheme === 'dark' ? '#ffffff' : '#495057';
  const axisLineColor = colorScheme === 'dark' ? '#f1f3f5' : '#ced4da';
  const gridLineColor = colorScheme === 'dark' ? '#6c757d' : '#e9ecef';

  const fullOptions = useMemo((): Highcharts.Options => {
    const themeOptions = colorScheme === 'light' ? {} : getThemeOptions(HighchartsHighContrastDarkTheme);

    const chartOptions: Highcharts.Options = merge({}, {
      chart: {
        animation: false,
        height: 400,
        backgroundColor: 'transparent',
        plotBackgroundColor: 'transparent',
        zooming: {
          type: 'x',
        },
        panning: {
          enabled: true,
          type: 'x',
        },
        panKey: 'shift',
        numberFormatter: formatNumber,
        events: {
          load(this: any) {
            Highcharts.addEvent(this.tooltip, 'headerFormatter', (e: any) => {
              if (e.isFooter) {
                return true;
              }

              let timestamp = e.labelConfig.point.x;

              if (e.labelConfig.point.dataGroup) {
                const xData = e.labelConfig.series.xData;
                const lastTimestamp = xData[xData.length - 1];
                if (timestamp + 100 * e.labelConfig.point.dataGroup.length >= lastTimestamp) {
                  timestamp = lastTimestamp;
                }
              }

              e.text = `Timestamp ${formatNumber(timestamp)}<br/>`;
              return false;
            });
          },
        },
      },
      title: {
        text: title,
        style: {
          color: colorScheme === 'dark' ? '#e9ecef' : '#212529',
        },
      },
      credits: {
        href: 'javascript:window.open("https://www.highcharts.com/?credits", "_blank")',
        style: {
          color: colorScheme === 'dark' ? '#868e96' : '#868e96',
        },
      },
      plotOptions: {
        series: {
          dataGrouping: {
            approximation(this: any, values: number[]): number {
              const endIndex = this.dataGroupInfo.start + this.dataGroupInfo.length;
              if (endIndex < this.xData.length) {
                return values[0];
              } else {
                return values[values.length - 1];
              }
            },
            anchor: 'start',
            firstAnchor: 'firstPoint',
            lastAnchor: 'lastPoint',
            units: [['second', [1, 2, 5, 10]]],
          },
        },
      },
      xAxis: {
        type: 'datetime',
        title: {
          text: 'Timestamp',
          style: {
            color: axisTextColor,
            textOutline: 'none',
          },
        },
        crosshair: {
          width: 1,
          color: colorScheme === 'dark' ? '#adb5bd' : '#adb5bd',
        },
        gridLineColor,
        lineColor: axisLineColor,
        tickColor: axisLineColor,
        labels: {
          style: {
            color: axisTextColor,
            fontSize: '13px',
            fontWeight: '600',
            textOutline: 'none',
          },
          formatter: (params: Highcharts.AxisLabelsFormatterContextObject) => formatNumber(params.value as number),
        },
      },
      yAxis: {
        opposite: false,
        allowDecimals: false,
        min,
        max,
        gridLineColor,
        lineColor: axisLineColor,
        tickColor: axisLineColor,
        title: {
          style: {
            color: axisTextColor,
            textOutline: 'none',
          },
        },
        labels: {
          style: {
            color: axisTextColor,
            fontSize: '13px',
            fontWeight: '600',
            textOutline: 'none',
          },
        },
      },
      tooltip: {
        split: false,
        shared: true,
        outside: true,
        backgroundColor: colorScheme === 'dark' ? '#1f2328' : '#ffffff',
        borderColor: colorScheme === 'dark' ? '#495057' : '#ced4da',
        style: {
          color: colorScheme === 'dark' ? '#f8f9fa' : '#212529',
        },
      },
      legend: {
        enabled: true,
        itemStyle: {
          color: colorScheme === 'dark' ? '#e9ecef' : '#212529',
        },
        itemHoverStyle: {
          color: colorScheme === 'dark' ? '#ffffff' : '#000000',
        },
        itemHiddenStyle: {
          color: colorScheme === 'dark' ? '#6c757d' : '#adb5bd',
        },
      },
      rangeSelector: {
        enabled: false,
      },
      navigator: {
        enabled: false,
      },
      scrollbar: {
        enabled: false,
      },
      exporting: {
        buttons: {
          contextButton: {
            theme: {
              fill: colorScheme === 'dark' ? '#25262b' : '#ffffff',
              stroke: colorScheme === 'dark' ? '#495057' : '#ced4da',
            },
          },
        },
      },
      series,
    }, options ?? {});

    return merge(themeOptions, chartOptions);
  }, [axisLineColor, axisTextColor, colorScheme, gridLineColor, title, options, series, min, max]);

  return (
    <VisualizerCard p={0}>
      <HighchartsReact highcharts={Highcharts} constructorType={'stockChart'} options={fullOptions} immutable />
    </VisualizerCard>
  );
}
