import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ConsentModal } from '../components/ConsentModal';
import { hasConsented, markConsented } from '../lib/consent';
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

  // 이용 동의 — 최초 1회 강제. undefined=확인중, true=동의, false=미동의.
  // AsyncStorage 실패 시 false 로 간주해 동의 모달 표시 (안전장치).
  const [consented, setConsented] = useState<boolean | undefined>(undefined);
  useEffect(() => {
    hasConsented().then(setConsented).catch(() => setConsented(false));
  }, []);

  function handleAgree() {
    setConsented(true);
    markConsented().catch(() => {
      /* 저장 실패해도 세션 내 통과 — 다음 실행 시 재동의 */
    });
  }

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
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="checklist/[id]" options={{ title: '항목 상세' }} />
      </Stack>
      {/* consented === undefined 동안은 모달 표시 안 함 (깜빡임 방지).
          false 로 결정되면 Modal 띄우고 동의 전까지 앱 사용 차단. */}
      <ConsentModal visible={consented === false} onAgree={handleAgree} />
    </SafeAreaProvider>
  );
}
