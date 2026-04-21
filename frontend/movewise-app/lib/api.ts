/**
 * FastAPI backend client for 이사이상무.
 */
import Constants from 'expo-constants';
import { Platform } from 'react-native';

// 웹(PWA) 빌드는 same-origin 을 기본값으로 → FastAPI 와 같은 App Service 에서 서빙.
// 네이티브(Expo Go/standalone) 는 기존 팀 Render URL 유지.
// EXPO_PUBLIC_API_URL 환경변수로 빌드 시 오버라이드 가능.
const DEFAULT_API_URL =
  Platform.OS === 'web' ? '' : 'https://movewise-jf1s.onrender.com';

const extra = (Constants.expoConfig?.extra ?? {}) as { apiUrl?: string };

let runtimeApiUrl =
  process.env.EXPO_PUBLIC_API_URL || extra.apiUrl || DEFAULT_API_URL;

export function getApiUrl(): string {
  return runtimeApiUrl;
}

export function setApiUrl(url: string): void {
  runtimeApiUrl = url;
}

// Legacy export (still used by MY screen display)
export const API_URL = runtimeApiUrl;

// ===== Types =====

export type HouseholdType = '자취' | '가족';
export type ContractType = '전세' | '월세' | '자가';
export type SchoolLevel = '초등' | '중등' | '고등';
export type MovingStyle = 'self' | 'company';

export interface ChecklistRequest {
  household: HouseholdType;
  contract: ContractType;
  contracts?: ContractType[];
  region: string;
  move_date: string; // YYYY-MM-DD
  has_pet: boolean;
  has_car: boolean;
  car_count?: number;
  has_children: boolean;
  children_count?: number;
  children_school_level?: SchoolLevel | null;
  is_foreigner?: boolean;
  is_apartment?: boolean;
  is_employed?: boolean;
  receives_welfare?: boolean;
  needs_id_reissue?: boolean;
  moving_style?: MovingStyle;
  deposit_krw?: number | null;
  monthly_rent_krw?: number | null;
  special_concerns?: string[];
  /** 자유 텍스트 — 토글로 못 잡는 엣지케이스. 비우면 LLM 호출 없이 정적 쿼리만. */
  free_text?: string | null;
}

export interface Citation {
  law_name: string;
  article: string;
  source_url?: string | null;
  article_title?: string | null;
  article_text?: string | null;
}

export interface ChecklistItem {
  category: string;
  title: string;
  description: string;
  d_day_offset: number;
  start_date: string;
  has_legal_deadline: boolean;
  deadline_date?: string | null;
  deadline_days?: number | null;
  penalty?: string | null;
  method?: string | null;
  contact?: string | null;
  region_hint?: string | null;
  citations: Citation[];
}

export interface ChecklistResponse {
  request: ChecklistRequest;
  generated_at: string;
  items: ChecklistItem[];
  total_items: number;
  used_queries: string[];
  warning?: string | null;
}

export interface SafeContractRequest {
  text: string;
  deposit_krw: number;
  expected_market_price_krw: number;
  region?: string;
}

export interface MarketDeal {
  apt_name: string;
  deal_amount_krw: number;
  deal_date: string;
  area_m2: number;
  floor: number;
  dong: string;
}

export interface MarketEstimate {
  source: string;
  region: string;
  lawd_cd?: string | null;
  query_ym: string;
  total_count: number;
  median_price_krw?: number | null;
  min_price_krw?: number | null;
  max_price_krw?: number | null;
  recent_deals: MarketDeal[];
  error?: string | null;
}

export interface RiskItem {
  severity: 'green' | 'yellow' | 'red';
  label: string;
  explanation_plain: string;
  related_laws: Citation[];
}

export interface ServiceReferral {
  icon: string;
  name: string;
  url: string;
  description: string;
}

export interface ChatCitation {
  source_type: 'law' | 'procedure' | 'youtube';
  title: string;
  content_snippet: string;
  url?: string | null;
  meta?: Record<string, any>;
}

export interface ChatResponse {
  answer: string;
  mode: 'fallback' | 'azure';
  citations: ChatCitation[];
  used_queries: string[];
}

export interface SafeContractResponse {
  extraction: Record<string, unknown>;
  jeontse_ratio: number;
  mortgage_ratio: number;
  risk_level: 'green' | 'yellow' | 'red';
  summary: string;
  risks: RiskItem[];
  referrals: ServiceReferral[];
  disclaimer: string;
  market_estimate?: MarketEstimate | null;
  inferred_region?: string | null;
}

// ===== Client =====

function withTimeout(ms: number): { signal: AbortSignal; clear: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  return { signal: controller.signal, clear: () => clearTimeout(timer) };
}

function wrapAbort(e: unknown): never {
  if (e instanceof Error && e.name === 'AbortError') {
    throw new Error('서버 응답 시간 초과 — 잠시 후 다시 시도해주세요');
  }
  throw e;
}

async function post<TReq, TRes>(path: string, body: TReq, timeoutMs = 45000): Promise<TRes> {
  const { signal, clear } = withTimeout(timeoutMs);
  try {
    const res = await fetch(`${getApiUrl()}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API ${res.status}: ${text}`);
    }
    return res.json() as Promise<TRes>;
  } catch (e) {
    return wrapAbort(e);
  } finally {
    clear();
  }
}

export interface SafeContractUploadParams {
  uri: string;
  name: string;
  mimeType?: string;
  deposit_krw: number;
  expected_market_price_krw: number;
  region?: string;
}

async function postMultipart<TRes>(path: string, form: FormData, timeoutMs = 60000): Promise<TRes> {
  const { signal, clear } = withTimeout(timeoutMs);
  try {
    const res = await fetch(`${getApiUrl()}${path}`, {
      method: 'POST',
      body: form,
      signal,
    });
    if (!res.ok) {
      let detail: string;
      try {
        const body = await res.json();
        detail = body?.detail || JSON.stringify(body);
      } catch {
        detail = await res.text();
      }
      throw new Error(`API ${res.status}: ${detail}`);
    }
    return res.json() as Promise<TRes>;
  } catch (e) {
    return wrapAbort(e);
  } finally {
    clear();
  }
}

export const api = {
  async health(): Promise<{ service: string; version: string; azure_ready: boolean }> {
    // Render free tier 가 idle 후 sleep → 첫 요청은 cold start 로 30~60s 가능.
    // timeout 30s 로 흡수. 더 길면 사용자 체감 너무 느림.
    const { signal, clear } = withTimeout(30000);
    try {
      const res = await fetch(`${getApiUrl()}/`, { signal });
      if (!res.ok) throw new Error(`health ${res.status}`);
      return res.json();
    } catch (e) {
      return wrapAbort(e);
    } finally {
      clear();
    }
  },
  async realtySummary(region: string): Promise<MarketEstimate> {
    const res = await fetch(
      `${getApiUrl()}/realty/summary?region=${encodeURIComponent(region)}`,
    );
    if (!res.ok) throw new Error(`realty ${res.status}`);
    const d = await res.json();
    return {
      source: '국토교통부 실거래가',
      region: d.region,
      lawd_cd: d.lawd_cd,
      query_ym: d.query_ym,
      total_count: d.total_count,
      median_price_krw: d.median_price_krw,
      min_price_krw: d.min_price_krw,
      max_price_krw: d.max_price_krw,
      recent_deals: (d.recent_deals || []).map((x: any) => ({
        apt_name: x.apt_name,
        deal_amount_krw: x.deal_amount_krw,
        deal_date: x.deal_date,
        area_m2: x.area_m2,
        floor: x.floor,
        dong: x.dong ?? '',
      })),
      error: d.error,
    };
  },
  checklist(req: ChecklistRequest) {
    return post<ChecklistRequest, ChecklistResponse>('/checklist', req, 45000);
  },
  safecontract(req: SafeContractRequest) {
    return post<SafeContractRequest, SafeContractResponse>('/safecontract', req);
  },
  chat(
    question: string,
    history: { role: 'user' | 'assistant'; content: string }[] = [],
  ) {
    return post<
      {
        question: string;
        history: { role: 'user' | 'assistant'; content: string }[];
      },
      ChatResponse
    >('/chat', { question, history });
  },
  async chatPresets(): Promise<string[]> {
    const res = await fetch(`${getApiUrl()}/chat/presets`);
    if (!res.ok) throw new Error(`chat presets ${res.status}`);
    const d = await res.json();
    return d.questions || [];
  },
  /** 음성 파일 업로드 → Azure Speech-to-Text → {text, status} (ko-KR).
   *  status: "Success" / "NoMatch" / "InitialSilenceTimeout" / "BabbleTimeout" 등.
   *  Render 백엔드에 STT 미배포 상태라 로컬 backend cloudflared tunnel 로 직송 (발표 임시).
   */
  async stt(audioUri: string): Promise<{ text: string; status: string }> {
    // env 우선, 없으면 현재 cloudflared tunnel 로 fallback (발표 임시). tunnel 바뀌면 .env 갱신.
    const STT_BACKEND_URL =
      process.env.EXPO_PUBLIC_STT_BACKEND_URL ||
      'https://bobby-roberts-exam-content.trycloudflare.com';
    const form = new FormData();
    form.append('audio', {
      uri: audioUri,
      name: 'recording.wav',
      type: 'audio/wav',
    } as any);
    const { signal, clear } = withTimeout(20000);
    try {
      const res = await fetch(`${STT_BACKEND_URL}/api/stt`, {
        method: 'POST',
        body: form,
        signal,
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        throw new Error(`STT ${res.status} ${txt.slice(0, 80)}`);
      }
      const d = await res.json();
      return {
        text: (d.text || '').toString(),
        status: (d.status || 'Unknown').toString(),
      };
    } finally {
      clear();
    }
  },
  async safecontractUpload(params: SafeContractUploadParams): Promise<SafeContractResponse> {
    const form = new FormData();
    // React Native FormData 는 {uri, name, type} 객체를 받음
    form.append('file', {
      uri: params.uri,
      name: params.name,
      type: params.mimeType || 'application/pdf',
    } as any);
    form.append('deposit_krw', String(params.deposit_krw));
    form.append('expected_market_price_krw', String(params.expected_market_price_krw));
    if (params.region) form.append('region', params.region);
    return postMultipart<SafeContractResponse>('/safecontract/upload', form);
  },
};
