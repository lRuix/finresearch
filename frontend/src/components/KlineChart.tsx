import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, CandlestickChart, LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { KlineRow, Period } from "../types";

echarts.use([
  BarChart,
  CandlestickChart,
  LineChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

function formatTime(iso: string, period: Period): string {
  const date = new Date(iso);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  if (period === "h") {
    return `${month}-${day} ${String(date.getHours()).padStart(2, "0")}:00`;
  }
  return `${month}-${day}`;
}

function movingAverage(values: number[], period: number): Array<number | null> {
  return values.map((_, index) => {
    if (index < period - 1) {
      return null;
    }
    const slice = values.slice(index - period + 1, index + 1);
    return Number((slice.reduce((sum, value) => sum + value, 0) / period).toFixed(3));
  });
}

function buildOption(rows: KlineRow[], period: Period) {
  const dates = rows.map((row) => formatTime(row.time, period));
  const candles = rows.map((row) => [row.open, row.close, row.low, row.high]);
  const closes = rows.map((row) => row.close);
  const volumeData = rows.map((row) => ({
    value: row.volume,
    itemStyle: { color: row.close >= row.open ? "#f05c66" : "#2eb98b" },
  }));

  return {
    backgroundColor: "transparent",
    animation: false,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross", label: { backgroundColor: "#33413d" } },
      backgroundColor: "#1a2220",
      borderColor: "#33413d",
      textStyle: { color: "#e7efec", fontSize: 12 },
    },
    legend: {
      data: ["K线", "MA5", "MA10", "MA20"],
      top: 0,
      left: 4,
      itemWidth: 14,
      itemHeight: 8,
      textStyle: { color: "#92a19c", fontSize: 11 },
    },
    grid: [
      { left: 54, right: 14, top: 34, height: "58%" },
      { left: 54, right: 14, top: "77%", height: "14%" },
    ],
    xAxis: [
      {
        type: "category",
        data: dates,
        boundaryGap: true,
        axisLine: { lineStyle: { color: "#33413d" } },
        axisTick: { show: false },
        axisLabel: { color: "#92a19c", hideOverlap: true, fontSize: 11 },
        splitLine: { show: false },
      },
      {
        type: "category",
        gridIndex: 1,
        data: dates,
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      },
    ],
    yAxis: [
      {
        scale: true,
        splitLine: { lineStyle: { color: "#22302c" } },
        axisLabel: { color: "#92a19c", fontSize: 11 },
        axisLine: { show: false },
      },
      {
        gridIndex: 1,
        splitNumber: 2,
        splitLine: { show: false },
        axisLabel: { show: false },
        axisLine: { show: false },
      },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 42, end: 100 },
      {
        type: "slider",
        xAxisIndex: [0, 1],
        bottom: 2,
        height: 18,
        borderColor: "#33413d",
        backgroundColor: "#151c1a",
        fillerColor: "rgba(62,201,173,.12)",
        handleStyle: { color: "#3ec9ad" },
        textStyle: { color: "#92a19c", fontSize: 10 },
      },
    ],
    series: [
      {
        name: "K线",
        type: "candlestick",
        data: candles,
        barWidth: "64%",
        itemStyle: {
          color: "#f05c66",
          color0: "#2eb98b",
          borderColor: "#f05c66",
          borderColor0: "#2eb98b",
        },
      },
      {
        name: "MA5",
        type: "line",
        data: movingAverage(closes, 5),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.2, color: "#e0b04a" },
      },
      {
        name: "MA10",
        type: "line",
        data: movingAverage(closes, 10),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.2, color: "#5aa8f0" },
      },
      {
        name: "MA20",
        type: "line",
        data: movingAverage(closes, 20),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.2, color: "#b78bf0" },
      },
      {
        name: "成交量",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumeData,
        barWidth: "64%",
      },
    ],
  };
}

interface KlineChartProps {
  rows: KlineRow[];
  period: Period;
}

export default function KlineChart({ rows, period }: KlineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) {
      return;
    }
    chartRef.current = echarts.init(element);
    const observer = new ResizeObserver(() => chartRef.current?.resize());
    observer.observe(element);
    return () => {
      observer.disconnect();
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (chartRef.current && rows.length > 0) {
      chartRef.current.setOption(buildOption(rows, period), { notMerge: true });
    }
  }, [rows, period]);

  return (
    <div className="kline-chart" ref={containerRef} aria-label="K线价格趋势图" />
  );
}
