// peak_load.js — simulates peak business hours. Target ~100-120 concurrent users.
// Teammate's report target: avg 980ms, ~120 req/s, 3% error.

import { userJourney } from './common.js';

export const options = {
    scenarios: {
        peak_load: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '1m', target: 50 },    // ramp to 50
                { duration: '2m', target: 100 },   // push to 100
                { duration: '2m', target: 100 },   // hold
                { duration: '1m', target: 0 },     // ramp down
            ],
            gracefulRampDown: '15s',
        },
    },
    thresholds: {
        'http_req_duration': ['p(95)<2500'],
        'http_req_failed': ['rate<0.05'],
    },
    summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
    userJourney();
}

export function handleSummary(data) {
    return {
        'results/peak_load_summary.json': JSON.stringify(data, null, 2),
    };
}
