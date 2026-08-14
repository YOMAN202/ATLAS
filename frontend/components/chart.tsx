"use client";

// Tree-shaken echarts import: `import * as echarts from "echarts"` pulls
// in every chart type and component the full library ships (radar, geo,
// candlestick, dataZoom, toolbox, ...), most of which this app never
// renders (only bar/line/pie, with grid/tooltip/legend/title — verified
// by grepping every chart option in app/). Registering only what's used
// keeps this out of every dashboard's initial JS bundle.
import * as echarts from "echarts/core";
import { BarChart, LineChart, PieChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { ComposeOption } from "echarts/core";
import type { BarSeriesOption, LineSeriesOption, PieSeriesOption } from "echarts/charts";
import type {
  GridComponentOption,
  LegendComponentOption,
  TitleComponentOption,
  TooltipComponentOption,
} from "echarts/components";
import { useEffect, useRef } from "react";

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export type EChartsOption = ComposeOption<
  | BarSeriesOption
  | LineSeriesOption
  | PieSeriesOption
  | GridComponentOption
  | LegendComponentOption
  | TitleComponentOption
  | TooltipComponentOption
>;

interface ChartProps {
  option: EChartsOption;
  height?: number;
  className?: string;
}

// Direct echarts usage (no echarts-for-react wrapper) — the fixed stack
// (ATLAS-TDD.md §8) names ECharts, not a specific React binding; this
// keeps the dependency surface small.
export function Chart({ option, height = 280, className }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = echarts.init(containerRef.current);
    chartRef.current = chart;

    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return <div ref={containerRef} className={className} style={{ height }} />;
}
