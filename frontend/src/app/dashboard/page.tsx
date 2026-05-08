'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Navigation from '@/components/Navigation';
import LiveMonitor from '@/components/LiveMonitor';
import ClipCard from '@/components/ClipCard';
import { streams as streamsApi, clips as clipsApi } from '@/lib/api';
import type { StreamStatus, Clip } from '@/lib/types';

export default function DashboardPage() {
  const router = useRouter();
  const [status, setStatus] = useState<StreamStatus | null>(null);
  const [recentClips, setRecentClips] = useState<Clip[]>([]);
  const [loading, setLoading] = useState(true);
  const [clipRefresh, setClipRefresh] = useState(0);

  const token = typeof window !== 'undefined' ? localStorage.getItem('clipper_token') : null;

  useEffect(() => {
    if (!token) {
      router.replace('/');
      return;
    }
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, [token]);

  useEffect(() => {
    fetchRecentClips();
  }, [clipRefresh]);

  const fetchStatus = async () => {
    try {
      const data = await streamsApi.getStatus();
      setStatus(data);
    } catch {
      router.replace('/');
    } finally {
      setLoading(false);
    }
  };

  const fetchRecentClips = async () => {
    try {
      const data = await clipsApi.list({ limit: 6 });
      setRecentClips(data.clips);
    } catch { /* silent */ }
  };

  const handleNewClip = useCallback(() => {
    setClipRefresh((n) => n + 1);
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div
            className="w-10 h-10 border-2 border-t-transparent rounded-full animate-spin mx-auto mb-4"
            style={{ borderColor: 'var(--forge-accent)', borderTopColor: 'transparent' }}
          />
          <p className="mono text-xs text-[var(--forge-muted)]">INITIALIZING CLIPFORGE...</p>
        </div>
      </div>
    );
  }

  const streamer = status?.streamer;
  const isLive = status?.is_live ?? false;

  return (
    <div className="min-h-screen">
      <Navigation
        displayName={streamer?.display_name}
        profileImageUrl={streamer?.profile_image_url}
      />

      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header row */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <div className="flex items-center gap-3 mb-1">
              {isLive ? (
                <>
                  <div
                    className="relative w-2.5 h-2.5 rounded-full"
                    style={{ background: 'var(--forge-green)' }}
                  >
                    <div className="live-dot absolute inset-0 rounded-full" />
                  </div>
                  <span className="mono text-xs font-bold" style={{ color: 'var(--forge-green)' }}>
                    LIVE NOW
                  </span>
                </>
              ) : (
                <>
                  <div
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ background: 'var(--forge-muted)' }}
                  />
                  <span className="mono text-xs text-[var(--forge-muted)]">OFFLINE</span>
                </>
              )}
            </div>
            <h1 className="text-3xl font-extrabold tracking-tight">
              {streamer?.display_name ?? 'Dashboard'}
            </h1>
            {status?.stream?.title && (
              <p className="text-[var(--forge-muted)] text-sm mt-0.5 truncate max-w-md">
                {status.stream.title}
              </p>
            )}
          </div>

          {/* Stat pills */}
          <div className="flex gap-3">
            {[
              { label: 'Total', value: status?.clip_stats.total ?? 0 },
              { label: 'Ready', value: status?.clip_stats.ready ?? 0 },
              { label: 'Approved', value: status?.clip_stats.approved ?? 0 },
            ].map((s) => (
              <div
                key={s.label}
                className="text-center border border-[var(--forge-border)] px-4 py-2"
                style={{ background: 'var(--forge-surface)' }}
              >
                <div className="mono text-2xl font-bold">{s.value}</div>
                <div className="mono text-xs text-[var(--forge-muted)] uppercase">{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Main grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Sidebar: Live monitor */}
          <div className="lg:col-span-1 space-y-4">
            {/* Stream info */}
            {status?.stream && (
              <div
                className="border border-[var(--forge-border)] p-4 space-y-2"
                style={{ background: 'var(--forge-surface)' }}
              >
                <p className="mono text-xs text-[var(--forge-muted)] uppercase tracking-widest">Stream Info</p>
                {status.stream.game_name && (
                  <p className="text-sm">
                    <span className="text-[var(--forge-muted)]">Game: </span>
                    {status.stream.game_name}
                  </p>
                )}
                {status.stream.started_at && (
                  <p className="mono text-xs text-[var(--forge-muted)]">
                    Started: {new Date(status.stream.started_at).toLocaleTimeString()}
                  </p>
                )}
              </div>
            )}

            <LiveMonitor
              broadcasterLogin={streamer?.login ?? ''}
              isLive={isLive}
              onNewClip={handleNewClip}
            />

            {/* Offline message */}
            {!isLive && (
              <div
                className="border border-[var(--forge-border)] p-4 text-center"
                style={{ background: 'var(--forge-surface)' }}
              >
                <p className="mono text-xs text-[var(--forge-muted)]">
                  Monitoring starts automatically when you go live on Twitch.
                </p>
              </div>
            )}
          </div>

          {/* Main: Recent clips */}
          <div className="lg:col-span-2">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-bold text-lg">Recent Clips</h2>
              <button
                onClick={() => router.push('/clips')}
                className="mono text-xs text-[var(--forge-accent)] hover:opacity-80 transition-opacity"
              >
                VIEW ALL →
              </button>
            </div>

            {recentClips.length === 0 ? (
              <div
                className="border border-[var(--forge-border)] border-dashed p-12 text-center"
                style={{ borderColor: 'var(--forge-border-bright)' }}
              >
                <div className="text-4xl mb-3">🎬</div>
                <p className="font-semibold mb-1">No clips yet</p>
                <p className="mono text-xs text-[var(--forge-muted)] max-w-xs mx-auto">
                  Go live on Twitch and ClipForge will automatically detect hype moments and create clips.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {recentClips.map((clip) => (
                  <ClipCard key={clip.id} clip={clip} onUpdate={handleNewClip} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
