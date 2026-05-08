export interface Clip {
  id: string;
  twitch_clip_id: string | null;
  twitch_clip_url: string | null;
  twitch_thumbnail_url: string | null;
  highlight_score: number;
  score_breakdown: Record<string, number>;
  status: 'pending' | 'processing' | 'ready' | 'approved' | 'rejected' | 'exported';
  transcript: string | null;
  chat_context: ChatMessage[];
  ai_title: string | null;
  ai_description: string | null;
  ai_hashtags: string[];
  duration_seconds: number | null;
  detected_at: string | null;
  approved_at: string | null;
  rejected_at: string | null;
  has_processed_video: boolean;
}

export interface ChatMessage {
  user: string;
  text: string;
  ts: number;
}

export interface StreamStatus {
  is_live: boolean;
  live_data: Record<string, unknown> | null;
  current_score: number;
  score_threshold: number;
  score_events: Array<{ score: number; source: string }>;
  stream: {
    id: string;
    title: string | null;
    game_name: string | null;
    started_at: string | null;
    is_live: boolean;
  } | null;
  clip_stats: {
    total: number;
    pending: number;
    ready: number;
    approved: number;
  };
  streamer: {
    id: string;
    login: string;
    display_name: string;
    profile_image_url: string | null;
  };
}

export interface WsMessage {
  channel: string;
  data: Record<string, unknown>;
}

export interface ScoreUpdate {
  total: number;
  breakdown: Record<string, number>;
  threshold: number;
  timestamp: number;
}
