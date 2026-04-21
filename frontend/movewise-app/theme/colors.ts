/**
 * 이사이상무 design tokens — 스티치 목업 색상/간격.
 */

export const colors = {
  // Brand
  primary: '#003A75',
  primaryLight: '#1F6FD0',
  primaryBg: '#E8F1FB',
  primaryMute: '#B8D4EC',
  accent: '#F5A623',
  accentBg: '#FFF8EC',

  // Severity
  danger: '#E74C3C',
  dangerBg: '#FFEEEE',
  warning: '#E67E22',
  warningBg: '#FFF4E6',
  success: '#27AE60',
  successBg: '#E8F5E9',

  // Grays — 가독성 향상 위해 더 진한 텍스트
  text: '#0F1822',
  textSub: '#5A6573',
  textMute: '#6B7280',
  border: '#E5E8EB',
  borderLight: '#F1F3F5',
  bg: '#F5F7FB',
  cardBg: '#FFFFFF',
  white: '#FFFFFF',
  overlay: 'rgba(0,58,117,0.08)',
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  pill: 999,
};

// 한국어 가독성 최적화 — lineHeight 1.5~1.6 / fontSize 모바일 표준
// letterSpacing 약간 음수: 한글 자간 타이트 효과 + 칩·버튼 라벨 밀림 방지
export const typography = {
  display: { fontSize: 28, fontWeight: '800' as const, color: colors.primary, lineHeight: 40, letterSpacing: -0.3 },
  title: { fontSize: 22, fontWeight: '700' as const, color: colors.text, lineHeight: 32, letterSpacing: -0.2 },
  subtitle: { fontSize: 18, fontWeight: '700' as const, color: colors.text, lineHeight: 28, letterSpacing: -0.2 },
  body: { fontSize: 16, fontWeight: '400' as const, color: colors.text, lineHeight: 26, letterSpacing: -0.1 },
  bodyBold: { fontSize: 16, fontWeight: '600' as const, color: colors.text, lineHeight: 26, letterSpacing: -0.1 },
  caption: { fontSize: 13, fontWeight: '400' as const, color: colors.textSub, lineHeight: 20 },
  captionBold: { fontSize: 13, fontWeight: '700' as const, color: colors.textSub, lineHeight: 20 },
  tabLabel: { fontSize: 11, fontWeight: '700' as const, lineHeight: 16, letterSpacing: -0.1 },
};
