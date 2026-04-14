/**
 * 법령 URL 헬퍼 — 국가법령정보센터 PC 페이지로 이동.
 *
 * m.law.go.kr 가 안정적이지 않아 www.law.go.kr 을 사용.
 */

const LAW_BASE = 'https://www.law.go.kr/법령';

/**
 * 법령명 → 국가법령정보센터 URL.
 * article 파라미터는 호환성 위해 남기지만 현재 URL 에는 포함하지 않음.
 */
export function buildMobileLawUrl(
  lawName: string,
  _article?: string | null,
): string {
  const lawEnc = encodeURIComponent(lawName.trim());
  return `${LAW_BASE}/${lawEnc}`;
}

/**
 * 백엔드에서 받은 citation URL 을 모바일 버전으로 가능하면 변환.
 * law_name·article 이 있으면 우선 사용, 없으면 원본 URL 반환.
 */
export function toMobileCitationUrl(params: {
  law_name?: string | null;
  article?: string | null;
  fallback_url?: string | null;
}): string | null {
  if (params.law_name) {
    return buildMobileLawUrl(params.law_name, params.article || undefined);
  }
  // easylaw.go.kr 는 그대로 유지 (mob 경로는 리다이렉트 안정성이 떨어짐)
  return params.fallback_url || null;
}

/**
 * 챗봇 citation title('주택임대차보호법 제3조의2')에서 법령명·조문 분리.
 */
export function parseLawTitle(title: string): {
  law_name: string;
  article: string | null;
} {
  // '주택임대차보호법 제3조의2 (보증금의 회수)' 같은 경우
  const clean = title.replace(/\s*\([^)]+\)\s*$/, '').trim();
  const match = clean.match(/^(.*?)\s+(제\S+)$/);
  if (match) {
    return { law_name: match[1], article: match[2] };
  }
  return { law_name: clean, article: null };
}
