// endurance.js — long-running test to find leaks, drift, and degradation.
// Moderate load (50 VUs) for 10 minutes. Shortened default for demo speed.
// Run a longer version with K6_DURATION_MULTIPLIER env var in production.

import { userJourney } from './common.js';

const DURATION_MULT = parseFloat(__ENV.K6_DURATION_MULTIPLIER || '1');
const hold = Math.floor(8 * DURATION_MULT); // 8 minutes default

export const options = {
    scenarios: {
        endurance: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '1m', target: 50 },
                { duration: `${hold}m`, target: 50 },
                { duration: '1m', target: 0 },
            ],
            gracefulRampDown: '15s',
        },
    },
    thresholds: {
        'http_req_duration': ['p(95)<1500'],
        'http_req_failed': ['rate<0.03'],
    },
    summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
    userJourney();
}

export function handleSummary(data) {
    return {
        'results/endurance_summary.json': JSON.stringify(data, null, 2),
    };
}
