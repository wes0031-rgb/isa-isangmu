/**
 * 법령 URL 헬퍼 — PC 사이트 대신 모바일 사이트로 변환.
 *
 * 앱은 폰에서만 보므로 m.law.go.kr / easylaw.go.kr/mob 같은
 * 모바일 최적화 페이지로 리다이렉트.
 */

const M_LAW_BASE = 'https://m.law.go.kr/법령';

/**
 * 법령명 (+선택: 조문) → 모바일 국가법령정보센터 URL.
 *
 * 예)
 *   buildMobileLawUrl('주택임대차보호법') → https://m.law.go.kr/법령/주택임대차보호법
 *   buildMobileLawUrl('주택임대차보호법', '제3조의2') → https://m.law.go.kr/법령/주택임대차보호법/제3조의2
 */
export function buildMobileLawUrl(
  lawName: string,
  article?: string | null,
): string {
  const lawEnc = encodeURIComponent(lawName.trim());
  if (article) {
    const artEnc = encodeURIComponent(article.trim());
    return `${M_LAW_BASE}/${lawEnc}/${artEnc}`;
  }
  return `${M_LAW_BASE}/${lawEnc}`;
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
