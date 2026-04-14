/**
 * 이사이상무 design tokens — 스티치 목업 색상/간격.
 */

export const colors = {
  // Brand
  primary: '#003A75',
  primaryLight: '#1F6FD0',
  primaryBg: '#E8F1FB',
  accent: '#F5A623',

  // Severity
  danger: '#E74C3C',
  warning: '#E67E22',
  success: '#27AE60',

  // Grays — 가독성 향상 위해 더 진한 텍스트
  text: '#0F1822',
  textSub: '#5A6573',
  textMute: '#9CA3AF',
  border: '#E5E8EB',
  borderLight: '#F1F3F5',
  bg: '#F5F7FB',
  cardBg: '#FFFFFF',
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

export const typography = {
  display: { fontSize: 30, fontWeight: '800' as const, color: colors.primary, lineHeight: 38 },
  title: { fontSize: 22, fontWeight: '700' as const, color: colors.text, lineHeight: 30 },
  subtitle: { fontSize: 17, fontWeight: '700' as const, color: colors.text, lineHeight: 24 },
  body: { fontSize: 15, fontWeight: '400' as const, color: colors.text, lineHeight: 22 },
  bodyBold: { fontSize: 15, fontWeight: '600' as const, color: colors.text, lineHeight: 22 },
  caption: { fontSize: 13, fontWeight: '400' as const, color: colors.textSub, lineHeight: 18 },
  captionBold: { fontSize: 13, fontWeight: '700' as const, color: colors.textSub, lineHeight: 18 },
  tabLabel: { fontSize: 12, fontWeight: '700' as const, lineHeight: 14 },
};
