'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Navigation from '@/components/Navigation';
import ClipCard from '@/components/ClipCard';
import { clips as clipsApi } from '@/lib/api';
import type { Clip } from '@/lib/types';

const FILTERS = [
  { label: 'All', value: '' },
  { label: 'Ready', value: 'ready' },
  { label: 'Pending', value: 'pending' },
  { label: 'Approved', value: 'approved' },
  { label: 'Rejected', value: 'rejected' },
];

export default function ClipsPage() {
  const router = useRouter();
  const [clipsList, setClipsList] = useState<Clip[]>([]);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const PER_PAGE = 12;

  const token = typeof window !== 'undefined' ? localStorage.getItem('clipper_token') : null;

  useEffect(() => {
    if (!token) router.replace('/');
  }, [token]);

  const fetchClips = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clipsApi.list({
        status: filter || undefined,
        limit: PER_PAGE,
        offset: page * PER_PAGE,
      });
      setClipsList(data.clips);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  }, [filter, page]);

  useEffect(() => {
    fetchClips();
  }, [fetchClips]);

  const handleFilterChange = (val: string) => {
    setFilter(val);
    setPage(0);
  };

  return (
    <div className="min-h-screen">
      <Navigation />

      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight">Clip Queue</h1>
            <p className="text-[var(--forge-muted)] text-sm mt-1">
              {total} clips · Review, edit titles, and export
            </p>
          </div>

          {/* Sort/filter info */}
          <div className="mono text-xs text-[var(--forge-muted)] text-right">
            <p>Sorted by: detected_at DESC</p>
            <p>Page {page + 1}</p>
          </div>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-1 mb-6 border-b border-[var(--forge-border)] pb-0">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => handleFilterChange(f.value)}
              className="mono text-xs px-4 py-2 transition-colors"
              style={{
                color: filter === f.value ? 'var(--forge-text)' : 'var(--forge-muted)',
                borderBottom:
                  filter === f.value
                    ? '2px solid var(--forge-accent)'
                    : '2px solid transparent',
                background: 'transparent',
                cursor: 'pointer',
                marginBottom: '-1px',
              }}
            >
              {f.label.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Grid */}
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="border border-[var(--forge-border)] overflow-hidden"
                style={{ background: 'var(--forge-surface)' }}
              >
                <div className="aspect-video skeleton" />
                <div className="p-4 space-y-2">
                  <div className="h-4 skeleton" />
                  <div className="h-2 skeleton w-3/4" />
                  <div className="h-8 skeleton mt-4" />
                </div>
              </div>
            ))}
          </div>
        ) : clipsList.length === 0 ? (
          <div
            className="border border-[var(--forge-border)] border-dashed p-16 text-center"
            style={{ borderColor: 'var(--forge-border-bright)' }}
          >
            <div className="text-4xl mb-3">📭</div>
            <p className="font-semibold mb-1">No clips {filter ? `with status "${filter}"` : 'yet'}</p>
            <p className="mono text-xs text-[var(--forge-muted)]">
              Clips appear here automatically when ClipForge detects highlight moments.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {clipsList.map((clip) => (
              <ClipCard key={clip.id} clip={clip} onUpdate={fetchClips} />
            ))}
          </div>
        )}

        {/* Pagination */}
        {total > PER_PAGE && (
          <div className="flex justify-center gap-3 mt-8">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="mono text-xs px-4 py-2 border border-[var(--forge-border)] disabled:opacity-40 hover:border-[var(--forge-accent)] transition-colors"
            >
              ← PREV
            </button>
            <span className="mono text-xs py-2 text-[var(--forge-muted)]">
              {page * PER_PAGE + 1}–{Math.min((page + 1) * PER_PAGE, total)} / {total}
            </span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={(page + 1) * PER_PAGE >= total}
              className="mono text-xs px-4 py-2 border border-[var(--forge-border)] disabled:opacity-40 hover:border-[var(--forge-accent)] transition-colors"
            >
              NEXT →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
