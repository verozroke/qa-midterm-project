// common.js — shared helpers for all k6 performance scripts.
// Keeps DRY: BASE_URL + auth + ticket flow live here.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';

export const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
export const USERNAME = __ENV.TEST_USERNAME || 'test.user';
export const PASSWORD = __ENV.TEST_PASSWORD || 'ChangeMe123!';

// Custom metrics — these get exported alongside http_req_* in the summary.
export const loginLatency = new Trend('login_latency_ms');
export const ticketListLatency = new Trend('ticket_list_latency_ms');
export const ticketCreateLatency = new Trend('ticket_create_latency_ms');
export const errorRate = new Rate('errors');
export const authFailures = new Counter('auth_failures');

export function login() {
    const payload = JSON.stringify({ username: USERNAME, password: PASSWORD });
    const params = { headers: { 'Content-Type': 'application/json' }, tags: { name: 'login' } };
    const res = http.post(`${BASE_URL}/api/auth/login`, payload, params);

    loginLatency.add(res.timings.duration);
    const ok = check(res, {
        'login 200': (r) => r.status === 200,
        'token present': (r) => r.json('token') !== undefined,
    });
    if (!ok) {
        authFailures.add(1);
        errorRate.add(1);
        return null;
    }
    errorRate.add(0);
    return res.json('token');
}

export function listTickets(token) {
    const res = http.get(`${BASE_URL}/api/tickets`, {
        headers: { Authorization: `Bearer ${token}` },
        tags: { name: 'list_tickets' },
    });
    ticketListLatency.add(res.timings.duration);
    const ok = check(res, { 'list 200': (r) => r.status === 200 });
    errorRate.add(!ok);
    return res;
}

export function createTicket(token, i) {
    const payload = JSON.stringify({
        title: `Load Test Ticket ${i}-${__VU}-${__ITER}`,
        description: 'Ticket created during k6 load test run.',
        priority: 'medium',
        category: 'general',
    });
    const res = http.post(`${BASE_URL}/api/tickets`, payload, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        tags: { name: 'create_ticket' },
    });
    ticketCreateLatency.add(res.timings.duration);
    const ok = check(res, { 'create 201': (r) => r.status === 201 });
    errorRate.add(!ok);
    return res;
}

// Default user journey: login -> list -> create -> short think time.
export function userJourney() {
    const token = login();
    if (!token) { sleep(1); return; }
    listTickets(token);
    sleep(0.5);
    createTicket(token, __ITER);
    sleep(1);
}
