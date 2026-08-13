"use client";

import * as echarts from "echarts";
import { useEffect, useRef } from "react";

interface ChartProps {
  option: echarts.EChartsOption;
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
