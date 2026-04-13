/**
 * 특이 상황 프리셋 — checklist_service.py 의 키워드 매칭과 동기화.
 * 각 옵션이 선택되면 label 을 special_concerns 배열에 추가해 백엔드에 전달한다.
 */

export interface ConcernOption {
  id: string;
  label: string;  // 백엔드에 전달되는 키워드 (서버 측 키워드 매칭 기준)
  icon: string;   // Ionicons
  group: '임대차 분쟁' | '비용 정산' | '하자·수리' | '기타';
}

export const CONCERN_OPTIONS: ConcernOption[] = [
  // 임대차 분쟁
  { id: 'deposit_return', label: '보증금 반환 우려', icon: 'cash-outline', group: '임대차 분쟁' },
  { id: 'lease_registration', label: '임차권등기', icon: 'shield-checkmark-outline', group: '임대차 분쟁' },
  { id: 'rent_increase', label: '월세 인상', icon: 'trending-up-outline', group: '임대차 분쟁' },
  { id: 'renewal_right', label: '갱신요구권', icon: 'refresh-outline', group: '임대차 분쟁' },

  // 비용 정산
  { id: 'long_term_repair', label: '장기수선충당금', icon: 'construct-outline', group: '비용 정산' },
  { id: 'mgmt_deposit', label: '관리비예치금', icon: 'wallet-outline', group: '비용 정산' },
  { id: 'utility_settle', label: '공과금 정산', icon: 'flash-outline', group: '비용 정산' },

  // 하자·수리
  { id: 'defect', label: '하자 분쟁', icon: 'alert-circle-outline', group: '하자·수리' },
  { id: 'repair', label: '수선 요청', icon: 'hammer-outline', group: '하자·수리' },

  // 기타
  { id: 'moving_company', label: '이사업체 분쟁', icon: 'cube-outline', group: '기타' },
  { id: 'jeonse_fraud', label: '전세사기 의심', icon: 'warning-outline', group: '기타' },
];

export const CONCERN_GROUPS: Array<ConcernOption['group']> = [
  '임대차 분쟁',
  '비용 정산',
  '하자·수리',
  '기타',
];
