/**
 * 특이 상황 프리셋 — checklist_service.py 의 키워드 매칭과 동기화.
 * 각 옵션이 선택되면 label 을 special_concerns 배열에 추가해 백엔드에 전달한다.
 */

export interface ConcernOption {
  id: string;
  label: string;  // 백엔드에 전달되는 키워드 (서버 측 키워드 매칭 기준)
  icon: string;   // Ionicons
  group: '임대차 분쟁' | '비용 정산' | '하자·수리 요청';
}

export const CONCERN_OPTIONS: ConcernOption[] = [
  // 임대차 분쟁
  { id: 'deposit_return', label: '보증금 반환', icon: 'cash-outline', group: '임대차 분쟁' },

  // 비용 정산
  { id: 'long_term_repair', label: '장기수선충당금', icon: 'construct-outline', group: '비용 정산' },
  { id: 'mgmt_deposit', label: '관리비예치금', icon: 'wallet-outline', group: '비용 정산' },
  { id: 'utility_settle', label: '공과금 정산', icon: 'flash-outline', group: '비용 정산' },

  // 하자·수리 요청
  { id: 'repair', label: '하자·수리 요청', icon: 'hammer-outline', group: '하자·수리 요청' },
];

export const CONCERN_GROUPS: Array<ConcernOption['group']> = [
  '임대차 분쟁',
  '비용 정산',
  '하자·수리 요청',
];
