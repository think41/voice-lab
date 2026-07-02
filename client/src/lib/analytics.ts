import type { RunRecord } from './types';

export interface ReportSummary {
  conversations: number;
  avgDurationSec: number;
  totalCostUsd: number;
  avgCostUsd: number;
  totalLlmCostUsd: number;
  avgLlmCostUsd: number;
  totalSttCostUsd: number;
  totalTtsCostUsd: number;
  totalTokens: number;
  providerReportedRuns: number;
}

export function runDurationSec(run: RunRecord): number {
  const start = Date.parse(run.created_at);
  if (Number.isNaN(start)) return 0;
  const lastEventTs = run.trace_events.reduce((max, event) => {
    const ts = Date.parse(event.created_at);
    return Number.isNaN(ts) ? max : Math.max(max, ts);
  }, start);
  return Math.max(0, (lastEventTs - start) / 1000);
}

export function aggregate(runs: RunRecord[]): ReportSummary {
  const conversations = runs.length;
  if (conversations === 0) {
    return {
      conversations: 0,
      avgDurationSec: 0,
      totalCostUsd: 0,
      avgCostUsd: 0,
      totalLlmCostUsd: 0,
      avgLlmCostUsd: 0,
      totalSttCostUsd: 0,
      totalTtsCostUsd: 0,
      totalTokens: 0,
      providerReportedRuns: 0,
    };
  }

  let totalDuration = 0;
  let totalCost = 0;
  let totalLlm = 0;
  let totalStt = 0;
  let totalTts = 0;
  let totalTokens = 0;
  let providerReportedRuns = 0;

  for (const run of runs) {
    totalDuration += runDurationSec(run);
    totalCost += run.usage_summary.total_cost_usd;
    totalLlm += run.usage_summary.llm.cost_usd;
    totalStt += run.usage_summary.stt.cost_usd;
    totalTts += run.usage_summary.tts.cost_usd;
    totalTokens += run.usage_summary.llm.total_tokens;
    if (run.usage_summary.stt.source === 'provider' || run.usage_summary.tts.source === 'provider') {
      providerReportedRuns += 1;
    }
  }

  return {
    conversations,
    avgDurationSec: totalDuration / conversations,
    totalCostUsd: totalCost,
    avgCostUsd: totalCost / conversations,
    totalLlmCostUsd: totalLlm,
    avgLlmCostUsd: totalLlm / conversations,
    totalSttCostUsd: totalStt,
    totalTtsCostUsd: totalTts,
    totalTokens,
    providerReportedRuns,
  };
}

export function formatDuration(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '0:00';
  const total = Math.round(sec);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function formatCost(usd: number, decimals = 4): string {
  if (!Number.isFinite(usd)) return '$0.00';
  return `$${usd.toFixed(decimals)}`;
}
