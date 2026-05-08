'use client';

import { useState, useEffect } from 'react';
import { clips as clipsApi } from '@/lib/api';
import type { Clip } from '@/lib/types';

interface ClipCardProps {
  clip: Clip;
  onUpdate: () => void;
}

const STATUS_CONFIG = {
  pending: { label: 'PENDING', color: 'var(--forge-muted)' },
  processing: { label: 'PROCESSING', color: 'var(--forge-amber)' },
  ready: { label: 'READY', color: 'var(--forge-accent)' },
  approved: { label: 'APPROVED', color: 'var(--forge-green)' },
  rejected: { label: 'REJECTED', color: 'var(--forge-red)' },
  exported: { label: 'EXPORTED', color: 'var(--forge-green)' },
};

export default function ClipCard({ clip, onUpdate }: ClipCardProps) {
  const [loading, setLoading] = useState<'approve' | 'reject' | null>(null);
  const [editingTitle, setEditingTitle] = useState(false);
  const [title, setTitle] = useState(clip.ai_title || '');
  const [expanded, setExpanded] = useState(false);
  // Optimistic status: updates immediately on action, then syncs when parent re-fetches
  const [localStatus, setLocalStatus] = useState(clip.status);

  useEffect(() => {
    setLocalStatus(clip.status);
  }, [clip.status]);

  const statusCfg = STATUS_CONFIG[localStatus] || STATUS_CONFIG.pending;

  const handleApprove = async () => {
    setLoading('approve');
    setLocalStatus('processing');
    try {
      await clipsApi.approve(clip.id);
      onUpdate();
    } catch {
      setLocalStatus(clip.status);
    } finally {
      setLoading(null);
    }
  };

  const handleReject = async () => {
    setLoading('reject');
    try {
      await clipsApi.reject(clip.id);
      setLocalStatus('rejected');
      onUpdate();
    } catch {
      setLocalStatus(clip.status);
    } finally {
      setLoading(null);
    }
  };

  const handleSaveTitle = async () => {
    if (title !== clip.ai_title) {
      await clipsApi.updateTitle(clip.id, title);
    }
    setEditingTitle(false);
  };

  const scorePercent = Math.min(100, (clip.highlight_score / 100) * 100);
  const scoreColor =
    clip.highlight_score >= 80
      ? 'var(--forge-green)'
      : clip.highlight_score >= 50
      ? 'var(--forge-amber)'
      : 'var(--forge-accent)';

  const detectedAt = clip.detected_at
    ? new Date(clip.detected_at).toLocaleTimeString()
    : null;

  return (
    <div
      className="clip-card border border-[var(--forge-border)] overflow-hidden animate-slide-in"
      style={{ background: 'var(--forge-surface)' }}
    >
      {/* Thumbnail / Preview */}
      <div
        className="relative aspect-video w-full overflow-hidden cursor-pointer"
        style={{ background: 'var(--forge-bg)' }}
        onClick={() => setExpanded(!expanded)}
      >
        {clip.has_processed_video ? (
          <video
            src={clipsApi.downloadUrl(clip.id)}
            className="w-full h-full object-cover"
            controls
            preload="metadata"
            onClick={(e) => e.stopPropagation()}
          />
        ) : clip.twitch_thumbnail_url ? (
          <img
            src={clip.twitch_thumbnail_url}
            alt="Clip thumbnail"
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <span className="mono text-xs text-[var(--forge-muted)]">NO PREVIEW</span>
          </div>
        )}

        {/* Score badge */}
        <div
          className="absolute top-2 right-2 mono text-xs font-bold px-2 py-0.5"
          style={{
            background: 'rgba(10, 10, 12, 0.85)',
            color: scoreColor,
            border: `1px solid ${scoreColor}`,
          }}
        >
          {clip.highlight_score.toFixed(0)} pts
        </div>

        {/* Status badge */}
        <div
          className="absolute top-2 left-2 mono text-xs font-bold px-2 py-0.5"
          style={{
            background: 'rgba(10, 10, 12, 0.85)',
            color: statusCfg.color,
          }}
        >
          {statusCfg.label}
        </div>

        {/* Duration */}
        {clip.duration_seconds && (
          <div
            className="absolute bottom-2 right-2 mono text-xs px-1.5 py-0.5"
            style={{ background: 'rgba(10, 10, 12, 0.85)' }}
          >
            {clip.duration_seconds.toFixed(0)}s
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {/* Title */}
        {editingTitle ? (
          <div className="flex gap-2">
            <input
              className="flex-1 bg-[var(--forge-bg)] border border-[var(--forge-accent)] px-2 py-1 text-sm outline-none"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSaveTitle()}
              autoFocus
            />
            <button
              onClick={handleSaveTitle}
              className="mono text-xs px-2 py-1 border border-[var(--forge-green)] text-[var(--forge-green)]"
            >
              SAVE
            </button>
          </div>
        ) : (
          <div
            className="font-semibold text-sm leading-tight cursor-pointer hover:text-[var(--forge-accent)] transition-colors"
            onClick={() => setEditingTitle(true)}
            title="Click to edit title"
          >
            {clip.ai_title || 'Untitled clip'}
            <span className="mono text-xs text-[var(--forge-muted)] ml-2">✎</span>
          </div>
        )}

        {/* Score bar mini */}
        <div className="h-1 w-full" style={{ background: 'var(--forge-border)' }}>
          <div
            className="h-full"
            style={{
              width: `${scorePercent}%`,
              background: scoreColor,
              transition: 'width 0.6s',
            }}
          />
        </div>

        {/* Breakdown pills */}
        {Object.keys(clip.score_breakdown).length > 0 && (
          <div className="flex flex-wrap gap-1">
            {Object.entries(clip.score_breakdown)
              .sort(([, a], [, b]) => b - a)
              .slice(0, 3)
              .map(([src, val]) => (
                <span
                  key={src}
                  className="mono text-xs px-2 py-0.5 border border-[var(--forge-border)]"
                  style={{ color: 'var(--forge-muted)' }}
                >
                  {src.replace('_', ' ')} +{val.toFixed(0)}
                </span>
              ))}
          </div>
        )}

        {/* Expanded details */}
        {expanded && (
          <div className="space-y-3 animate-slide-in">
            {/* Transcript */}
            {clip.transcript && (
              <div
                className="p-3 border-l-2 border-[var(--forge-accent)] text-xs text-[var(--forge-muted)] italic"
                style={{ background: 'var(--forge-bg)' }}
              >
                "{clip.transcript.slice(0, 200)}{clip.transcript.length > 200 ? '...' : ''}"
              </div>
            )}

            {/* Chat context */}
            {clip.chat_context.length > 0 && (
              <div style={{ background: 'var(--forge-bg)' }} className="p-3 space-y-1">
                <p className="mono text-xs text-[var(--forge-muted)] mb-2 uppercase">Chat at moment</p>
                {clip.chat_context.slice(0, 5).map((msg, i) => (
                  <div key={i} className="text-xs">
                    <span className="font-bold" style={{ color: 'var(--forge-accent)' }}>
                      {msg.user}
                    </span>
                    <span className="text-[var(--forge-muted)]">: {msg.text}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Hashtags */}
            {clip.ai_hashtags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {clip.ai_hashtags.slice(0, 8).map((tag) => (
                  <span
                    key={tag}
                    className="mono text-xs px-2 py-0.5"
                    style={{ color: 'var(--forge-accent)', background: 'var(--forge-accent-dim)' }}
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Timestamp */}
        {detectedAt && (
          <p className="mono text-xs text-[var(--forge-muted)]">Detected at {detectedAt}</p>
        )}

        {/* Action buttons */}
        <div className="flex gap-2 pt-1">
          {/* READY / PENDING: review actions */}
          {(localStatus === 'ready' || localStatus === 'pending') && (
            <>
              <button
                onClick={handleApprove}
                disabled={!!loading}
                className="flex-1 mono text-xs py-2 font-bold transition-opacity disabled:opacity-50"
                style={{ background: 'var(--forge-green)', color: 'var(--forge-bg)' }}
              >
                {loading === 'approve' ? '...' : '✓ APPROVE'}
              </button>
              <button
                onClick={handleReject}
                disabled={!!loading}
                className="flex-1 mono text-xs py-2 font-bold border transition-opacity disabled:opacity-50"
                style={{ borderColor: 'var(--forge-red)', color: 'var(--forge-red)', background: 'transparent' }}
              >
                {loading === 'reject' ? '...' : '✕ REJECT'}
              </button>
            </>
          )}

          {/* PROCESSING: spinner label */}
          {localStatus === 'processing' && (
            <div
              className="flex-1 mono text-xs py-2 text-center"
              style={{ color: 'var(--forge-amber)', border: '1px solid var(--forge-amber)' }}
            >
              ⟳ PROCESSING...
            </div>
          )}

          {/* REJECTED: info label, no download */}
          {localStatus === 'rejected' && (
            <div
              className="flex-1 mono text-xs py-2 text-center"
              style={{ color: 'var(--forge-red)', border: '1px solid var(--forge-red)' }}
            >
              ✕ REJECTED
            </div>
          )}

          {/* Twitch link */}
          {clip.twitch_clip_url && (
            <a
              href={clip.twitch_clip_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mono text-xs py-2 px-3 border border-[var(--forge-border)] text-[var(--forge-muted)] hover:text-[var(--forge-text)] transition-colors"
            >
              ↗
            </a>
          )}

          {/* APPROVED / EXPORTED: download — only when video is ready */}
          {(localStatus === 'approved' || localStatus === 'exported') && clip.has_processed_video && (
            <a
              href={clipsApi.downloadUrl(clip.id)}
              download
              className="flex-1 mono text-xs py-2 text-center border transition-colors"
              style={{ borderColor: 'var(--forge-green)', color: 'var(--forge-green)' }}
            >
              ↓ DOWNLOAD
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
