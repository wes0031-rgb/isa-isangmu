/**
 * Splash screen — auto redirects to onboarding after brief delay.
 */
import { useRouter } from 'expo-router';
import { useEffect } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { Text } from '../lib/AppText';
import { colors, spacing, typography } from '../theme/colors';

export default function Splash() {
  const router = useRouter();

  useEffect(() => {
    const t = setTimeout(() => router.replace('/onboarding'), 1200);
    return () => clearTimeout(t);
  }, [router]);

  return (
    <View style={styles.root}>
      <Text style={styles.logo}>이사이상무</Text>
      <Text style={styles.tagline}>이사 여정 가이드</Text>
      <ActivityIndicator color="#ffffff" style={{ marginTop: spacing.xl }} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primary,
  },
  logo: {
    ...typography.display,
    color: '#ffffff',
    fontSize: 40,
    letterSpacing: 1.5,
  },
  tagline: {
    color: '#B8D4EC',
    fontSize: 16,
    marginTop: spacing.sm,
  },
});
