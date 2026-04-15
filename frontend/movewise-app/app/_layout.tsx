import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { loadFontScale } from '../lib/fontScale';
import { colors } from '../theme/colors';

export default function RootLayout() {
  // 폰트 스케일은 async 로드 중 UI 를 막지 않음.
  // 과거: `if (!ready) return null` 패턴이 loadFontScale() hang 시 무한 로딩 유발.
  // 현재: 기본값(normal) 으로 즉시 렌더하고, 로드 완료 후 listener 로 재렌더.
  useEffect(() => {
    loadFontScale().catch(() => {
      /* AsyncStorage 에러는 조용히 무시 — 기본값(normal) 유지 */
    });
  }, []);

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.primary },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: '700' },
          contentStyle: { backgroundColor: colors.bg },
        }}
      >
        <Stack.Screen name="index" options={{ headerShown: false }} />
        <Stack.Screen name="onboarding" options={{ headerShown: false }} />
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="checklist/[id]" options={{ title: '항목 상세' }} />
      </Stack>
    </SafeAreaProvider>
  );
}
