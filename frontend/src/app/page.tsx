'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { auth } from '@/lib/api';

export default function HomePage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // If already logged in, redirect to dashboard
    const token = localStorage.getItem('clipper_token');
    if (token) router.replace('/dashboard');
  }, [router]);

  const handleLogin = async () => {
    setLoading(true);
    try {
      const { url } = await auth.getLoginUrl();
      window.location.href = url;
    } catch {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center relative overflow-hidden">
      {/* Background grid */}
      <div
        className="absolute inset-0 opacity-20"
        style={{
          backgroundImage: `
            linear-gradient(var(--forge-border) 1px, transparent 1px),
            linear-gradient(90deg, var(--forge-border) 1px, transparent 1px)
          `,
          backgroundSize: '60px 60px',
        }}
      />

      {/* Corner accents */}
      <div className="absolute top-0 left-0 w-48 h-48 border-t border-l border-[var(--forge-accent)] opacity-30" />
      <div className="absolute bottom-0 right-0 w-48 h-48 border-b border-r border-[var(--forge-accent)] opacity-30" />

      <div className="relative z-10 text-center max-w-2xl px-6 animate-fade-in">
        {/* Logo mark */}
        <div className="inline-flex items-center gap-3 mb-8">
          <div className="w-10 h-10 bg-[var(--forge-accent)] rotate-12 flex items-center justify-center">
            <span className="text-white font-bold text-lg -rotate-12">⚡</span>
          </div>
          <span className="mono text-sm text-[var(--forge-muted)] tracking-widest uppercase">
            ClipForge v1.0
          </span>
        </div>

        <h1
          className="text-6xl font-extrabold mb-4 leading-none tracking-tight"
          style={{ letterSpacing: '-0.03em' }}
        >
          AI Clips.
          <br />
          <span style={{ color: 'var(--forge-accent)' }}>Zero effort.</span>
        </h1>

        <p className="text-[var(--forge-muted)] text-lg mb-10 leading-relaxed max-w-md mx-auto">
          ClipForge monitors your stream in real-time — chat spikes, hype moments,
          subs & raids — and automatically creates TikTok-ready clips.
        </p>

        {/* Feature list */}
        <div className="grid grid-cols-3 gap-4 mb-10 text-left">
          {[
            { icon: '💬', label: 'Chat velocity', desc: 'Spike detection' },
            { icon: '🎬', label: 'Auto clip', desc: 'Twitch API' },
            { icon: '📱', label: 'Vertical edit', desc: '9:16 FFmpeg' },
          ].map((f) => (
            <div
              key={f.label}
              className="border border-[var(--forge-border)] p-4"
              style={{ background: 'var(--forge-surface)' }}
            >
              <div className="text-2xl mb-1">{f.icon}</div>
              <div className="font-semibold text-sm">{f.label}</div>
              <div className="mono text-xs text-[var(--forge-muted)]">{f.desc}</div>
            </div>
          ))}
        </div>

        <button
          onClick={handleLogin}
          disabled={loading}
          className="inline-flex items-center gap-3 px-8 py-4 font-bold text-lg transition-all duration-200"
          style={{
            background: loading ? 'var(--forge-accent-dim)' : 'var(--forge-accent)',
            color: 'white',
            cursor: loading ? 'not-allowed' : 'pointer',
            border: 'none',
            outline: 'none',
          }}
          onMouseEnter={(e) => {
            if (!loading) e.currentTarget.style.opacity = '0.85';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.opacity = '1';
          }}
        >
          <svg viewBox="0 0 24 24" className="w-6 h-6 fill-current">
            <path d="M11.571 4.714h1.715v5.143H11.57zm4.715 0H18v5.143h-1.714zM6 0L1.714 4.286v15.428h5.143V24l4.286-4.286h3.428L22.286 12V0zm14.571 11.143l-3.428 3.428h-3.429l-3 3v-3H6.857V1.714h13.714z" />
          </svg>
          {loading ? 'Redirecting...' : 'Connect with Twitch'}
        </button>

        <p className="mt-4 mono text-xs text-[var(--forge-muted)]">
          Requires clips:edit + chat:read scopes
        </p>
      </div>

      {/* Bottom bar */}
      <div className="absolute bottom-0 left-0 right-0 border-t border-[var(--forge-border)] py-3 px-6 flex justify-between items-center">
        <span className="mono text-xs text-[var(--forge-muted)]">CLIPFORGE_SYS v1.0.0</span>
        <span className="mono text-xs text-[var(--forge-muted)]">
          AI-POWERED · REAL-TIME · AUTOMATED
        </span>
      </div>
    </main>
  );
}
