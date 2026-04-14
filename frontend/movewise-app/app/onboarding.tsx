/**
 * Minimal 1-page onboarding — explains service + CTA to main tabs.
 */
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { Image, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppPressable } from '../components/AppPressable';

import { Text } from '../lib/AppText';
import { colors, radius, spacing, typography } from '../theme/colors';

const FEATURES = [
  {
    icon: 'checkmark-circle' as const,
    title: '개인화 체크리스트',
    desc: '조건 입력만으로 D-day 타임라인과 법적 기한이 자동 생성',
  },
  {
    icon: 'shield-checkmark' as const,
    title: 'SafeContract 해석',
    desc: '등기부등본을 쉬운 말로 해석하고 위험 요소 안내',
  },
  {
    icon: 'library' as const,
    title: '법 조항 근거',
    desc: '모든 항목이 실제 법률 조항에 기반 — 출처 확인 가능',
  },
];

export default function Onboarding() {
  const router = useRouter();
  return (
    <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <View style={styles.logoBadge}>
          <Image
            source={require('../assets/splash-icon.png')}
            style={styles.logoMark}
            resizeMode="contain"
          />
        </View>
        <Text style={styles.logo}>이사이상무</Text>
        <Text style={styles.subtitle}>이사부터 정착까지, 한 곳에서</Text>
      </View>

      <View style={styles.features}>
        {FEATURES.map((f) => (
          <View key={f.title} style={styles.featureRow}>
            <Ionicons name={f.icon} size={28} color={colors.primaryLight} />
            <View style={styles.featureText}>
              <Text style={styles.featureTitle}>{f.title}</Text>
              <Text style={styles.featureDesc}>{f.desc}</Text>
            </View>
          </View>
        ))}
      </View>

      <AppPressable style={styles.cta} onPress={() => router.replace('/(tabs)')}>
        <Text style={styles.ctaText}>시작하기</Text>
      </AppPressable>
      <Text style={styles.disclaimer}>
        ※ 참고용 도구입니다. 법률 자문이 아닙니다.
      </Text>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
    paddingHorizontal: spacing.lg,
  },
  header: {
    alignItems: 'center',
    marginTop: spacing.xxl,
    marginBottom: spacing.xl,
  },
  logoBadge: {
    width: 110,
    height: 110,
    borderRadius: 24,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
    shadowColor: colors.primary,
    shadowOpacity: 0.2,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 4,
  },
  logoMark: {
    width: 78,
    height: 78,
  },
  logo: {
    ...typography.display,
    fontSize: 32,
  },
  subtitle: {
    ...typography.caption,
    fontSize: 14,
    marginTop: spacing.sm,
  },
  features: {
    flex: 1,
    gap: spacing.lg,
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: colors.cardBg,
    padding: spacing.md,
    borderRadius: radius.md,
    gap: spacing.md,
  },
  featureText: {
    flex: 1,
  },
  featureTitle: {
    ...typography.subtitle,
    marginBottom: spacing.xs,
  },
  featureDesc: {
    ...typography.caption,
  },
  cta: {
    backgroundColor: colors.primary,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  ctaText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '700',
  },
  disclaimer: {
    ...typography.caption,
    textAlign: 'center',
    marginBottom: spacing.md,
  },
});
