/**
 * 폰트 스케일 — 접근성용 글자 크기 토글.
 *
 * 동작 원리:
 *  1. MY 탭에서 일반/큼/아주 큼 3단계 선택 → AsyncStorage 영속화
 *  2. lib/AppText 의 Text wrapper 가 useFontScaleLevel() 로 구독
 *  3. 각 Text 는 자신의 base fontSize/lineHeight 에 SCALE_FACTORS 를 곱해서 렌더
 *  4. 레벨 변경 시 리스너가 모든 AppText 를 리렌더시켜 즉시 반영
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useState } from 'react';

export type FontScaleLevel = 'normal' | 'large' | 'xlarge';

const STORAGE_KEY = 'movewise:font_scale';

export const SCALE_FACTORS: Record<FontScaleLevel, number> = {
  normal: 1.0,
  large: 1.15,
  xlarge: 1.3,
};

export const SCALE_LABELS: Record<FontScaleLevel, string> = {
  normal: '기본',
  large: '큼',
  xlarge: '아주 큼',
};

let currentScale: FontScaleLevel = 'normal';
const listeners = new Set<(level: FontScaleLevel) => void>();

export async function loadFontScale(): Promise<FontScaleLevel> {
  try {
    const v = (await AsyncStorage.getItem(STORAGE_KEY)) as FontScaleLevel | null;
    if (v && v in SCALE_FACTORS) {
      currentScale = v;
      return v;
    }
  } catch {}
  return 'normal';
}

export async function setFontScale(level: FontScaleLevel): Promise<void> {
  currentScale = level;
  try {
    await AsyncStorage.setItem(STORAGE_KEY, level);
  } catch {}
  listeners.forEach((l) => l(level));
}

export function getFontScale(): FontScaleLevel {
  return currentScale;
}

/**
 * 레벨 자체가 필요할 때 (MY 탭 하이라이트, AppText 내부 구독 등)
 */
export function useFontScaleLevel(): [FontScaleLevel, (l: FontScaleLevel) => void] {
  const [level, setLevelState] = useState<FontScaleLevel>(currentScale);

  useEffect(() => {
    const listener = (l: FontScaleLevel) => setLevelState(l);
    listeners.add(listener);
    setLevelState(currentScale);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  const update = useCallback((l: FontScaleLevel) => {
    setFontScale(l);
  }, []);

  return [level, update];
}
