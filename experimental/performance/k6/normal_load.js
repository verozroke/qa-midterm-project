// normal_load.js — simulates typical business-hours traffic.
// ~20 VUs ramp up and hold for 2 minutes.  Target of teammate's report: avg 420ms, ~35 req/s.

import { userJourney } from './common.js';

export const options = {
    scenarios: {
        normal_load: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '30s', target: 10 },   // ramp to 10 users
                { duration: '1m', target: 20 },    // hold at 20 users
                { duration: '30s', target: 0 },    // ramp down
            ],
            gracefulRampDown: '10s',
        },
    },
    thresholds: {
        // CI quality gates — fail the test if violated.
        'http_req_duration': ['p(95)<1000'],
        'http_req_failed': ['rate<0.02'],
        'login_latency_ms': ['p(95)<800'],
    },
    summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
    userJourney();
}

export function handleSummary(data) {
    return {
        'results/normal_load_summary.json': JSON.stringify(data, null, 2),
        stdout: textSummary(data),
    };
}

function textSummary(data) {
    const m = data.metrics;
    const avg = (x) => (x && x.values && x.values.avg) ? x.values.avg.toFixed(1) : 'n/a';
    const p95 = (x) => (x && x.values && x.values['p(95)']) ? x.values['p(95)'].toFixed(1) : 'n/a';
    return `
=== Normal Load Summary ===
  http_req_duration avg: ${avg(m.http_req_duration)} ms  p95: ${p95(m.http_req_duration)} ms
  login_latency_ms  avg: ${avg(m.login_latency_ms)} ms   p95: ${p95(m.login_latency_ms)} ms
  error rate:            ${((m.errors?.values?.rate || 0) * 100).toFixed(2)}%
  iterations:            ${m.iterations?.values?.count || 0}
  req/s (approx):        ${((m.http_reqs?.values?.count || 0) / 120).toFixed(1)}
`;
}
