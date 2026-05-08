import type { Clip, StreamStatus } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('clipper_token');
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const url = new URL(`${API_BASE}${path}`);
  if (token) url.searchParams.set('token', token);

  const res = await fetch(url.toString(), {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

// Auth
export const auth = {
  getLoginUrl: () => request<{ url: string }>('/api/auth/login'),
  getMe: (token: string) => request<{
    streamer_id: string;
    twitch_id: string;
    login: string;
    display_name: string;
    profile_image_url: string | null;
  }>(`/api/auth/me?token=${token}`),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
};

// Streams
export const streams = {
  getStatus: () => request<StreamStatus>('/api/streams/status'),
};

// Clips
export const clips = {
  list: (params?: { status?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return request<{ clips: Clip[]; total: number }>(`/api/clips/${qs ? `?${qs}` : ''}`);
  },
  get: (id: string) => request<Clip>(`/api/clips/${id}`),
  approve: (id: string) => request(`/api/clips/${id}/approve`, { method: 'POST' }),
  reject: (id: string, reason?: string) =>
    request(`/api/clips/${id}/reject${reason ? `&reason=${encodeURIComponent(reason)}` : ''}`, {
      method: 'POST',
    }),
  updateTitle: (id: string, title: string) =>
    request(`/api/clips/${id}/title?title=${encodeURIComponent(title)}`, { method: 'PATCH' }),
  downloadUrl: (id: string, processed = true) => {
    const token = getToken();
    return `${API_BASE}/api/clips/${id}/download?processed=${processed}&token=${token}`;
  },
};

// WebSocket
export function createWs(broadcasterLogin: string): WebSocket {
  const wsBase = API_BASE.replace('http', 'ws');
  return new WebSocket(`${wsBase}/ws/${broadcasterLogin}`);
}
