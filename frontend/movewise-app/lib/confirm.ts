/**
 * 크로스 플랫폼 확인창 — 웹에서는 window.confirm, 네이티브에서는 Alert.alert.
 *
 * React Native Web 의 Alert.alert 는 버튼 콜백이 동작하지 않아 확인창이 무시된다.
 * 이 헬퍼는 두 플랫폼 모두에서 await 로 결과를 받을 수 있게 추상화한다.
 */
import { Alert, Platform } from 'react-native';

export function confirmAsync(
  title: string,
  message: string,
  confirmLabel = '확인',
  cancelLabel = '취소',
): Promise<boolean> {
  if (Platform.OS === 'web') {
    if (typeof window === 'undefined') return Promise.resolve(false);
    return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  }
  return new Promise<boolean>((resolve) => {
    Alert.alert(title, message, [
      { text: cancelLabel, style: 'cancel', onPress: () => resolve(false) },
      {
        text: confirmLabel,
        style: 'destructive',
        onPress: () => resolve(true),
      },
    ]);
  });
}

export function alertAsync(title: string, message?: string): void {
  if (Platform.OS === 'web') {
    if (typeof window === 'undefined') return;
    window.alert(message ? `${title}\n\n${message}` : title);
    return;
  }
  Alert.alert(title, message);
}
