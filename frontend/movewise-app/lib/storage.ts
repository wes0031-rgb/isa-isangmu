/**
 * AsyncStorage 래퍼 — 체크리스트 영속화, 완료 상태, 설정.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { ChecklistRequest, ChecklistResponse } from './api';

const K = {
  CHECKLIST: 'movewise:checklist',
  COMPLETIONS: 'movewise:completions',
  API_URL: 'movewise:api_url',
  USER_NAME: 'movewise:user_name',
} as const;

// ===== Checklist =====

export interface StoredChecklist {
  request: ChecklistRequest;
  response: ChecklistResponse;
  saved_at: string; // ISO
}

export async function saveChecklist(
  request: ChecklistRequest,
  response: ChecklistResponse,
): Promise<void> {
  const record: StoredChecklist = {
    request,
    response,
    saved_at: new Date().toISOString(),
  };
  await AsyncStorage.setItem(K.CHECKLIST, JSON.stringify(record));
}

export async function loadChecklist(): Promise<StoredChecklist | null> {
  const raw = await AsyncStorage.getItem(K.CHECKLIST);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as StoredChecklist;
    // 스키마 가드 — 구버전 또는 손상된 데이터면 자동 정리
    if (
      !parsed?.request?.move_date ||
      !Array.isArray(parsed?.response?.items)
    ) {
      await AsyncStorage.removeItem(K.CHECKLIST);
      await AsyncStorage.removeItem(K.COMPLETIONS);
      return null;
    }
    return parsed;
  } catch {
    await AsyncStorage.removeItem(K.CHECKLIST);
    return null;
  }
}

export async function clearChecklist(): Promise<void> {
  await AsyncStorage.removeItem(K.CHECKLIST);
  await AsyncStorage.removeItem(K.COMPLETIONS);
}

// ===== Completion state =====

export type CompletionMap = Record<string, boolean>; // categoryKey → done

export async function loadCompletions(): Promise<CompletionMap> {
  const raw = await AsyncStorage.getItem(K.COMPLETIONS);
  if (!raw) return {};
  try {
    return JSON.parse(raw) as CompletionMap;
  } catch {
    return {};
  }
}

export async function setCompletion(key: string, done: boolean): Promise<void> {
  const current = await loadCompletions();
  current[key] = done;
  await AsyncStorage.setItem(K.COMPLETIONS, JSON.stringify(current));
}

// ===== Settings =====

export async function loadApiUrl(): Promise<string | null> {
  return AsyncStorage.getItem(K.API_URL);
}

export async function saveApiUrl(url: string): Promise<void> {
  await AsyncStorage.setItem(K.API_URL, url);
}

export async function loadUserName(): Promise<string | null> {
  return AsyncStorage.getItem(K.USER_NAME);
}

export async function saveUserName(name: string): Promise<void> {
  await AsyncStorage.setItem(K.USER_NAME, name);
}
