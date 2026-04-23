// spike_load.js — sudden surge to test system under shock.
// Jumps from 10 to 200 users in 10 seconds. Tests resilience under burst traffic.

import { userJourney } from './common.js';

export const options = {
    scenarios: {
        spike_load: {
            executor: 'ramping-vus',
            startVUs: 10,
            stages: [
                { duration: '30s', target: 10 },    // warm-up baseline
                { duration: '10s', target: 200 },   // the spike
                { duration: '1m', target: 200 },    // hold at peak
                { duration: '30s', target: 10 },    // recover
                { duration: '20s', target: 0 },
            ],
            gracefulRampDown: '15s',
        },
    },
    thresholds: {
        // Spike tests expect degradation; thresholds are looser.
        'http_req_duration': ['p(95)<5000'],
        'http_req_failed': ['rate<0.15'],
    },
    summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
    userJourney();
}

export function handleSummary(data) {
    return {
        'results/spike_load_summary.json': JSON.stringify(data, null, 2),
    };
}
