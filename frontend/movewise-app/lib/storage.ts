/**
 * AsyncStorage 래퍼 — 체크리스트 영속화, 완료 상태, 설정.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { ChecklistItem, ChecklistRequest, ChecklistResponse } from './api';

const K = {
  CHECKLIST: 'movewise:checklist',
  COMPLETIONS: 'movewise:completions',
  CUSTOM_ITEMS: 'movewise:custom_items',
  NOTES: 'movewise:notes',
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
  await AsyncStorage.removeItem(K.CUSTOM_ITEMS);
  await AsyncStorage.removeItem(K.NOTES);
}

// ===== Custom items (사용자가 직접 추가한 체크리스트 항목) =====

export async function loadCustomItems(): Promise<ChecklistItem[]> {
  const raw = await AsyncStorage.getItem(K.CUSTOM_ITEMS);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // 마이그레이션: 빈 start_date 를 오늘 날짜로 채움
    const today = new Date().toISOString().slice(0, 10);
    let migrated = false;
    for (const item of parsed) {
      if (!item.start_date) {
        item.start_date = today;
        migrated = true;
      }
    }
    if (migrated) {
      await AsyncStorage.setItem(K.CUSTOM_ITEMS, JSON.stringify(parsed));
    }
    return parsed;
  } catch {
    return [];
  }
}

export async function addCustomItem(item: ChecklistItem): Promise<void> {
  const current = await loadCustomItems();
  current.push(item);
  await AsyncStorage.setItem(K.CUSTOM_ITEMS, JSON.stringify(current));
}

export async function removeCustomItem(key: string): Promise<void> {
  const current = await loadCustomItems();
  const filtered = current.filter((it) => `${it.category}::${it.title}` !== key);
  await AsyncStorage.setItem(K.CUSTOM_ITEMS, JSON.stringify(filtered));
}

// ===== Personal notes (각 항목별 메모) =====

export type NotesMap = Record<string, string>; // itemKey → note text

export async function loadNotes(): Promise<NotesMap> {
  const raw = await AsyncStorage.getItem(K.NOTES);
  if (!raw) return {};
  try {
    return JSON.parse(raw) as NotesMap;
  } catch {
    return {};
  }
}

export async function setNote(key: string, text: string): Promise<void> {
  const current = await loadNotes();
  if (text.trim()) {
    current[key] = text;
  } else {
    delete current[key];
  }
  await AsyncStorage.setItem(K.NOTES, JSON.stringify(current));
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

export async function clearCompletions(): Promise<void> {
  await AsyncStorage.removeItem(K.COMPLETIONS);
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
