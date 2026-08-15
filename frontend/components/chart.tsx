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

// Registered once, applied to every chart via echarts.init(el, "atlas-dark")
// -- a design-system-level fix rather than a per-chart-option one: every
// page's chart automatically gets correct dark-surface axis/legend/tooltip
// styling without each page having to restate it. Series colors are the
// dataviz skill's validated dark-mode categorical palette (fixed order,
// never cycled per filter); axis/split-line/text colors match
// app/globals.css's --chart-gridline/--chart-baseline/ink tokens.
echarts.registerTheme("atlas-dark", {
  color: [
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
  ],
  backgroundColor: "transparent",
  textStyle: { color: "#c3c2b7" },
  title: { textStyle: { color: "#f5f5f4" }, subtextStyle: { color: "#898781" } },
  legend: { textStyle: { color: "#c3c2b7" } },
  tooltip: {
    backgroundColor: "#232322",
    borderColor: "rgba(255,255,255,0.08)",
    textStyle: { color: "#f5f5f4" },
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: "#383835" } },
    axisTick: { lineStyle: { color: "#383835" } },
    axisLabel: { color: "#898781" },
    splitLine: { lineStyle: { color: "#2c2c2a" } },
  },
  valueAxis: {
    axisLine: { lineStyle: { color: "#383835" } },
    axisTick: { lineStyle: { color: "#383835" } },
    axisLabel: { color: "#898781" },
    splitLine: { lineStyle: { color: "#2c2c2a" } },
  },
});

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
    const chart = echarts.init(containerRef.current, "atlas-dark");
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
