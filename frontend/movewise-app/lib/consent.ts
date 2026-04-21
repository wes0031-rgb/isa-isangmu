/**
 * 이용 동의 상태 관리.
 *
 * 설계:
 * - AsyncStorage 키 `@consent_agreed_v1` 에 타임스탬프 저장.
 * - v1 접미사: 정책 문구 변경 시 v2 로 올려 전체 사용자에게 재동의 요구 가능.
 * - 미동의(null) 상태면 앱 진입 시 ConsentModal 강제 표시.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

const CONSENT_KEY = '@consent_agreed_v1';

export async function hasConsented(): Promise<boolean> {
  try {
    const v = await AsyncStorage.getItem(CONSENT_KEY);
    return !!v;
  } catch {
    return false;
  }
}

export async function markConsented(): Promise<void> {
  try {
    await AsyncStorage.setItem(CONSENT_KEY, new Date().toISOString());
  } catch {
    // AsyncStorage 실패해도 세션 내에선 통과 — 다음 실행 시 다시 물음
  }
}

export async function clearConsent(): Promise<void> {
  try {
    await AsyncStorage.removeItem(CONSENT_KEY);
  } catch {
    /* noop */
  }
}
