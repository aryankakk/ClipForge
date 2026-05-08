'use client';

import { useEffect, useRef, useState } from 'react';
import { createWs } from '@/lib/api';
import type { ScoreUpdate } from '@/lib/types';

interface LiveMonitorProps {
  broadcasterLogin: string;
  isLive: boolean;
  onNewClip?: () => void;
}

const SOURCE_LABELS: Record<string, string> = {
  chat_velocity: 'Chat spike',
  chat_message: 'Chat message',
  sub: 'Subscription',
  resub: 'Resub',
  gift_sub: 'Gift sub',
  raid: 'Raid',
  channel_points: 'Channel points',
  cheer: 'Bits/Cheer',
  audio: 'Audio spike',
};

export default function LiveMonitor({ broadcasterLogin, isLive, onNewClip }: LiveMonitorProps) {
  const [score, setScore] = useState(0);
  const [breakdown, setBreakdown] = useState<Record<string, number>>({});
  const [threshold] = useState(60);
  const [connected, setConnected] = useState(false);
  const [recentEvents, setRecentEvents] = useState<Array<{ source: string; score: number; ts: number }>>([]);
  const [recentChats, setRecentChats] = useState<Array<{ user: string; text: string }>>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!broadcasterLogin || !isLive) return;

    const ws = createWs(broadcasterLogin);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      const { channel, data } = msg;

      if (channel.endsWith(':score')) {
        const update = data as ScoreUpdate;
        setScore(update.total);
        setBreakdown(update.breakdown || {});
      } else if (channel.endsWith(':clip')) {
        onNewClip?.();
      } else if (channel.endsWith(':chat')) {
        const chatMsg = data as { user: string; text: string; score_contribution: number };
        setRecentChats((prev) => [chatMsg, ...prev].slice(0, 12));
        if (chatMsg.score_contribution > 0) {
          setRecentEvents((prev) =>
            [{ source: 'chat_message', score: chatMsg.score_contribution, ts: Date.now() }, ...prev].slice(0, 10)
          );
        }
      }
    };

    return () => ws.close();
  }, [broadcasterLogin, isLive]);

  const pct = Math.min(100, (score / threshold) * 100);
  const isCritical = pct >= 80;
  const scoreColor = isCritical ? 'var(--forge-green)' : pct >= 50 ? 'var(--forge-amber)' : 'var(--forge-accent)';

  return (
    <div className="space-y-4">
      {/* Connection status */}
      <div className="flex items-center justify-between">
        <span className="mono text-xs text-[var(--forge-muted)] uppercase tracking-widest">
          Live Monitor
        </span>
        <div className="flex items-center gap-2">
          <div
            className="relative w-2 h-2 rounded-full"
            style={{ background: connected ? 'var(--forge-green)' : 'var(--forge-muted)' }}
          >
            {connected && <div className="live-dot absolute inset-0 rounded-full" />}
          </div>
          <span className="mono text-xs" style={{ color: connected ? 'var(--forge-green)' : 'var(--forge-muted)' }}>
            {connected ? 'WS CONNECTED' : 'DISCONNECTED'}
          </span>
        </div>
      </div>

      {/* Score meter */}
      <div
        className="border border-[var(--forge-border)] p-4"
        style={{ background: 'var(--forge-surface)' }}
      >
        <div className="flex justify-between items-baseline mb-3">
          <span className="font-semibold text-sm">Highlight Score</span>
          <span
            className="mono text-3xl font-bold"
            style={{ color: scoreColor, transition: 'color 0.3s' }}
          >
            {score.toFixed(0)}
            <span className="text-sm text-[var(--forge-muted)] ml-1">/ {threshold}</span>
          </span>
        </div>

        {/* Bar */}
        <div
          className="w-full h-3 rounded-none overflow-hidden"
          style={{ background: 'var(--forge-border)' }}
        >
          <div
            className="h-full score-fill rounded-none"
            style={{ width: `${pct}%`, background: `linear-gradient(90deg, var(--forge-accent), ${scoreColor})` }}
          />
        </div>
        {isCritical && (
          <p className="mono text-xs mt-2" style={{ color: 'var(--forge-green)' }}>
            ⚡ CLIP THRESHOLD REACHED
          </p>
        )}
      </div>

      {/* Score breakdown */}
      {Object.keys(breakdown).length > 0 && (
        <div
          className="border border-[var(--forge-border)] p-4 space-y-2"
          style={{ background: 'var(--forge-surface)' }}
        >
          <p className="mono text-xs text-[var(--forge-muted)] uppercase tracking-widest mb-3">Breakdown</p>
          {Object.entries(breakdown)
            .sort(([, a], [, b]) => b - a)
            .map(([src, val]) => (
              <div key={src} className="flex justify-between items-center">
                <span className="text-sm text-[var(--forge-muted)]">
                  {SOURCE_LABELS[src] || src}
                </span>
                <span className="mono text-sm font-bold" style={{ color: 'var(--forge-accent)' }}>
                  +{val.toFixed(0)}
                </span>
              </div>
            ))}
        </div>
      )}

      {/* Live chat feed */}
      {recentChats.length > 0 && (
        <div
          className="border border-[var(--forge-border)] p-4"
          style={{ background: 'var(--forge-surface)' }}
        >
          <p className="mono text-xs text-[var(--forge-muted)] uppercase tracking-widest mb-3">
            Chat Feed
          </p>
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {recentChats.map((msg, i) => (
              <div key={i} className="text-xs animate-slide-in">
                <span className="font-bold" style={{ color: 'var(--forge-accent)' }}>
                  {msg.user}
                </span>
                <span className="text-[var(--forge-muted)]">: </span>
                <span>{msg.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
