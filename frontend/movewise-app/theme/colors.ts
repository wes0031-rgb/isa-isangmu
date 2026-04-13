/**
 * MoveWise design tokens — 스티치 목업 색상/간격.
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

  // Grays
  text: '#1A2332',
  textSub: '#6B7684',
  textMute: '#9CA3AF',
  border: '#E5E8EB',
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
  display: { fontSize: 28, fontWeight: '700' as const, color: colors.primary },
  title: { fontSize: 22, fontWeight: '700' as const, color: colors.text },
  subtitle: { fontSize: 16, fontWeight: '600' as const, color: colors.text },
  body: { fontSize: 14, fontWeight: '400' as const, color: colors.text },
  caption: { fontSize: 12, fontWeight: '400' as const, color: colors.textSub },
};
