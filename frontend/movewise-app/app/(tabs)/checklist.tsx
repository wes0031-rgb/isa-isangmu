/**
 * Checklist tab — form + saved result with checkbox completion tracking.
 */
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { DatePickerModal } from '../../components/DatePickerModal';
import { RegionPickerModal } from '../../components/RegionPickerModal';
import { Text } from '../../lib/AppText';
import { alertAsync, confirmAsync } from '../../lib/confirm';
import {
  api,
  ChecklistItem,
  ChecklistRequest,
  ChecklistResponse,
  ContractType,
  HouseholdType,
  MovingStyle,
  SchoolLevel,
} from '../../lib/api';
import { CONCERN_OPTIONS } from '../../lib/specialConcerns';
import {
  CompletionMap,
  addCustomItem,
  clearChecklist,
  clearCompletions,
  consumePendingRegion,
  loadChecklist,
  loadCompletions,
  loadCustomItems,
  removeCustomItem,
  saveChecklist,
  setCompletion,
} from '../../lib/storage';
import { useRotatingText } from '../../lib/useRotatingText';
import { colors, radius, spacing, typography } from '../../theme/colors';

const CHECKLIST_LOADING_STEPS = [
  '📋 조건 분석 중...',
  '⚖️ 법령 조항 검색 중...',
  '📅 D-day 타임라인 구성 중...',
] as const;

const HOUSEHOLDS: HouseholdType[] = ['자취', '가족'];
const CONTRACTS: ContractType[] = ['월세', '전세', '자가'];
const SCHOOL_LEVELS: SchoolLevel[] = ['초등', '중등', '고등'];
const MOVING_STYLES: { value: MovingStyle; label: string; icon: string }[] = [
  { value: 'company', label: '이사 업체', icon: 'cube' },
  { value: 'self', label: '셀프 이사', icon: 'person' },
];

// 2단계 체크박스들 — special_concerns 라벨로 전송, 로드 시 역복원
const EXTRA_LABELS = {
  student: '학생',
  militaryDuty: '병역 대상자',
  highFloor: '고층 이사 (엘베·곤도라)',
  largeWaste: '대형 폐기물 배출',
  internet: '인터넷 이전',
  tvTransfer: 'TV 이전',
} as const;
const EXTRA_KEYS = Object.keys(EXTRA_LABELS) as (keyof typeof EXTRA_LABELS)[];

function todayPlus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

/** 이사일 기준 오프셋 → 사용자 친화적 라벨 ("이사 14일 전" / "이사 당일" / "이사 3일 후"). */
function formatMoveOffsetLabel(offset: number): string {
  if (offset === 0) return '이사 당일';
  if (offset < 0) return `이사 ${-offset}일 전`;
  return `이사 ${offset}일 후`;
}

function formatDateLabel(ymd: string): string {
  if (!ymd) return '날짜 선택';
  const [y, m, d] = ymd.split('-');
  const dateObj = new Date(Number(y), Number(m) - 1, Number(d));
  const dow = ['일', '월', '화', '수', '목', '금', '토'][dateObj.getDay()];
  return `${y}년 ${Number(m)}월 ${Number(d)}일 (${dow})`;
}

function normalizeKey(k: string): string {
  return k.replace(/\s/g, '');
}

function itemKey(it: ChecklistItem): string {
  return `${it.category}::${it.title}`;
}

export default function ChecklistScreen() {
  const router = useRouter();
  const [mode, setMode] = useState<'form' | 'result'>('form');

  // Form state
  const [household, setHousehold] = useState<HouseholdType>('자취');
  const [contracts, setContracts] = useState<ContractType[]>(['월세']);
  const [region, setRegion] = useState('경기도 성남시 분당구');
  const [moveDate, setMoveDate] = useState(todayPlus(14));
  const [hasPet, setHasPet] = useState(false);
  const [hasCar, setHasCar] = useState(false);
  const [carCount, setCarCount] = useState(1);
  const [hasChildren, setHasChildren] = useState(false);
  const [schoolLevel, setSchoolLevel] = useState<SchoolLevel | null>(null);
  const [isForeigner, setIsForeigner] = useState(false);
  const [isApartment, setIsApartment] = useState(false);
  const [isEmployed, setIsEmployed] = useState(false);
  const [receivesWelfare, setReceivesWelfare] = useState(false);
  const [needsIdReissue, setNeedsIdReissue] = useState(false);
  const [concernLabels, setConcernLabels] = useState<string[]>([]);
  const [freeText, setFreeText] = useState('');
  const [movingStyle, setMovingStyle] = useState<MovingStyle>('company');
  // 2단계 체크박스 (special_concerns 로 전송)
  const [extra, setExtra] = useState<Record<keyof typeof EXTRA_LABELS, boolean>>({
    student: false,
    militaryDuty: false,
    highFloor: false,
    largeWaste: false,
    internet: false,
    tvTransfer: false,
  });
  const toggleExtra = (k: keyof typeof EXTRA_LABELS) =>
    setExtra((prev) => ({ ...prev, [k]: !prev[k] }));

  // Modals
  const [datePickerOpen, setDatePickerOpen] = useState(false);
  const [regionPickerOpen, setRegionPickerOpen] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ChecklistResponse | null>(null);
  const [completions, setCompletions] = useState<CompletionMap>({});
  const [customItems, setCustomItems] = useState<ChecklistItem[]>([]);
  const [addItemOpen, setAddItemOpen] = useState(false);
  const loadingMessage = useRotatingText(CHECKLIST_LOADING_STEPS, loading, 2500);

  // 탭 포커스마다 저장된 체크리스트 복원 (또는 마이에서 삭제된 경우 상태 초기화)
  // 가드: 첫 focus 만 saved 자동 복원. 이후 focus 는 pending region 만 처리해서
  // SafeContract 에서 "체크리스트 만들기" → form 진입 후 다른 탭 갔다 와도
  // pending region 이 saved 의 옛 region 으로 덮어써지지 않도록.
  const isFirstFocusRef = useRef(true);
  useFocusEffect(
    useCallback(() => {
      (async () => {
        const pending = await consumePendingRegion();

        // pending region 있으면 무조건 form 모드 + region 적용 (focus 횟수 무관).
        if (pending) {
          isFirstFocusRef.current = false;
          setRegion(pending);
          setMode('form');
          setResult(null);
          // saved 있으면 region 외 다른 필드는 prefill (사용자 편의)
          const savedForPrefill = await loadChecklist();
          if (savedForPrefill) {
            const req = savedForPrefill.request;
            setHousehold(req.household);
            setContracts(req.contracts && req.contracts.length > 0 ? req.contracts : [req.contract]);
            setMoveDate(req.move_date);
            setHasPet(req.has_pet);
            setHasCar(req.has_car);
            setCarCount(req.car_count ?? 1);
            setHasChildren(req.has_children);
            setSchoolLevel(req.children_school_level ?? null);
            setIsForeigner(req.is_foreigner ?? false);
            setIsApartment(req.is_apartment ?? false);
            setIsEmployed(req.is_employed ?? false);
            setReceivesWelfare(req.receives_welfare ?? false);
            setNeedsIdReissue(req.needs_id_reissue ?? false);
            setMovingStyle(req.moving_style ?? 'company');
            const allConcerns = req.special_concerns ?? [];
            const extraState = { ...extra };
            const restConcerns: string[] = [];
            for (const lbl of allConcerns) {
              const key = EXTRA_KEYS.find((k) => EXTRA_LABELS[k] === lbl);
              if (key) extraState[key] = true;
              else restConcerns.push(lbl);
            }
            setExtra(extraState);
            setConcernLabels(restConcerns);
            setFreeText(req.free_text ?? '');
            const customs = await loadCustomItems();
            setCustomItems(customs);
          }
          return;
        }

        // 첫 focus 가 아니면 자동 복원 안 함 (사용자가 form 작업 중일 수 있음)
        if (!isFirstFocusRef.current) return;
        isFirstFocusRef.current = false;

        const saved = await loadChecklist();
        if (saved) {
          // 기존 체크리스트 복원 (result 모드)
          setResult(saved.response);
          const req = saved.request;
          setHousehold(req.household);
          setContracts(
            req.contracts && req.contracts.length > 0
              ? req.contracts
              : [req.contract],
          );
          setRegion(req.region);
          setMoveDate(req.move_date);
          setHasPet(req.has_pet);
          setHasCar(req.has_car);
          setCarCount(req.car_count ?? 1);
          setHasChildren(req.has_children);
          setSchoolLevel(req.children_school_level ?? null);
          setIsForeigner(req.is_foreigner ?? false);
          setIsApartment(req.is_apartment ?? false);
          setIsEmployed(req.is_employed ?? false);
          setReceivesWelfare(req.receives_welfare ?? false);
          setNeedsIdReissue(req.needs_id_reissue ?? false);
          setMovingStyle(req.moving_style ?? 'company');
          // special_concerns 에서 EXTRA 라벨 분리
          const allConcerns = req.special_concerns ?? [];
          const extraState = { ...extra };
          const restConcerns: string[] = [];
          for (const lbl of allConcerns) {
            const key = EXTRA_KEYS.find((k) => EXTRA_LABELS[k] === lbl);
            if (key) extraState[key] = true;
            else restConcerns.push(lbl);
          }
          setExtra(extraState);
          setConcernLabels(restConcerns);
          setFreeText(req.free_text ?? '');
          setMode('result');
          const comp = await loadCompletions();
          setCompletions(comp);
          const customs = await loadCustomItems();
          setCustomItems(customs);
        } else {
          // saved 없음 → 빈 form
          setResult(null);
          setCompletions({});
          setCustomItems([]);
          setMode('form');
        }
      })();
    }, []),
  );

  function toggleContract(c: ContractType) {
    // 단일 선택 모드 (라디오 버튼 동작):
    // - 이미 선택된 항목 클릭 → 아무 반응 없음 (최소 1개 유지)
    // - 다른 항목 클릭 → 그것만 선택 (기존 선택 자동 해제)
    setContracts((prev) => {
      if (prev.length === 1 && prev[0] === c) return prev;
      return [c];
    });
  }

  function toggleConcern(label: string) {
    setConcernLabels((prev) =>
      prev.includes(label) ? prev.filter((x) => x !== label) : [...prev, label],
    );
  }

  async function submit() {
    if (contracts.length === 0) {
      setError('계약 유형을 하나 이상 선택하세요');
      return;
    }
    const isRegenerating = result !== null;  // 기존 결과 있으면 재생성 모드
    setLoading(true);
    setError(null);
    // EXTRA 체크박스들을 special_concerns 라벨로 병합 (중복 방지)
    const extraLabels = EXTRA_KEYS.filter((k) => extra[k]).map(
      (k) => EXTRA_LABELS[k],
    );
    const mergedConcerns = Array.from(
      new Set([...concernLabels, ...extraLabels]),
    );
    const payload: ChecklistRequest = {
      household,
      contract: contracts[0],
      contracts,
      region,
      move_date: moveDate,
      has_pet: hasPet,
      has_car: hasCar,
      car_count: hasCar ? carCount : 1,
      has_children: hasChildren,
      children_school_level: hasChildren ? schoolLevel : null,
      is_foreigner: isForeigner,
      is_apartment: isApartment,
      is_employed: isEmployed,
      receives_welfare: receivesWelfare,
      needs_id_reissue: needsIdReissue,
      moving_style: movingStyle,
      special_concerns: mergedConcerns,
      free_text: freeText.trim() || null,
    };
    try {
      const res = await api.checklist(payload);
      // 재생성 시 완료 상태 마이그레이션 (title 공백 차이로 유실 방지) + 구 key 정리
      if (isRegenerating) {
        const oldComp = await loadCompletions();
        const oldKeys = Object.keys(oldComp);
        const freshComp: CompletionMap = {};
        for (const oldKey of oldKeys) {
          if (!oldComp[oldKey]) continue;
          const normOld = normalizeKey(oldKey);
          const match = res.items.find(
            (it) => normalizeKey(itemKey(it)) === normOld,
          );
          if (match) {
            freshComp[itemKey(match)] = true;
          }
        }
        // storage 를 새 key 셋으로 완전 교체 (구 key 잔류 방지)
        await clearCompletions();
        for (const [k, v] of Object.entries(freshComp)) {
          await setCompletion(k, v);
        }
        setCompletions(freshComp);
      } else {
        setCompletions({});
      }
      setResult(res);
      await saveChecklist(payload, res);
      setMode('result');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleToggle(item: ChecklistItem) {
    // Optimistic UI — state 먼저 업데이트하고 저장은 백그라운드로
    const key = itemKey(item);
    setCompletions((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      setCompletion(key, next[key]).catch(() => {
        // 저장 실패 시 상태 롤백
        setCompletions((p) => ({ ...p, [key]: !next[key] }));
      });
      return next;
    });
  }

  async function handleShare() {
    if (!result) return;
    const lines = [
      `[이사이상무 이사 체크리스트]`,
      `이사일: ${moveDate} · ${region} · ${household} · ${contracts.join('/')}`,
      '',
      ...result.items.map((it, idx) => {
        const done = completions[itemKey(it)] ? '[✔]' : '[ ]';
        const dl = it.deadline_date ? ` ⚠ 마감 ${it.deadline_date}` : '';
        const dday = formatMoveOffsetLabel(it.d_day_offset);
        return `${done} ${idx + 1}. ${it.title} (${dday})${dl}`;
      }),
      '',
      `생성: ${result.generated_at}`,
    ];
    try {
      await Share.share({ message: lines.join('\n') });
    } catch (e: any) {
      alertAsync('공유 실패', e.message);
    }
  }

  // 폼 state 를 기본값으로 되돌림 (storage 는 건드리지 않음)
  function resetFormState() {
    setHousehold('자취');
    setContracts(['월세']);
    setRegion('경기도 성남시 분당구');
    setMoveDate(todayPlus(14));
    setHasPet(false);
    setHasCar(false);
    setCarCount(1);
    setHasChildren(false);
    setSchoolLevel(null);
    setIsForeigner(false);
    setIsApartment(false);
    setIsEmployed(false);
    setReceivesWelfare(false);
    setNeedsIdReissue(false);
    setMovingStyle('company');
    setExtra({
      student: false,
      militaryDuty: false,
      highFloor: false,
      largeWaste: false,
      internet: false,
      tvTransfer: false,
    });
    setConcernLabels([]);
    setFreeText('');
    setError(null);
  }

  async function handleNew() {
    const confirmed = await confirmAsync(
      '새 체크리스트',
      '저장된 체크리스트를 지우고 새로 만드시겠어요? (수동 추가 항목·메모·폼 입력값도 모두 초기화됩니다)',
    );
    if (!confirmed) return;
    await clearChecklist();
    setResult(null);
    setCompletions({});
    setCustomItems([]);
    resetFormState();
    setMode('form');
  }

  // form 모드에서 폼만 초기화 (result 있을 땐 확인창, 없을 땐 즉시)
  async function handleResetForm() {
    if (result) {
      await handleNew();
      return;
    }
    const confirmed = await confirmAsync(
      '입력 초기화',
      '선택한 조건을 모두 기본값으로 되돌릴까요?',
    );
    if (!confirmed) return;
    resetFormState();
  }

  function handleEditConditions() {
    // 폼 상태는 useFocusEffect 에서 이미 복원된 상태 → 그대로 form 모드 전환
    // submit 시 saveChecklist 가 덮어쓰고 완료 상태는 유지
    setMode('form');
  }

  async function handleAddCustomItem(draft: {
    title: string;
    category: string;
    description: string;
    start_date: string; // YYYY-MM-DD — 사용자가 달력에서 고른 날짜
  }) {
    // 이사일 기준 offset 계산 (카드의 "이사 N일 전/후" 라벨에 사용)
    const [sy, sm, sd] = draft.start_date.split('-').map(Number);
    const [my, mm, md] = moveDate.split('-').map(Number);
    const startDate = new Date(sy, sm - 1, sd);
    const moveDateObj = new Date(my, mm - 1, md);
    const offset = Math.round(
      (startDate.getTime() - moveDateObj.getTime()) / (1000 * 60 * 60 * 24),
    );
    const newItem: ChecklistItem = {
      category: draft.category || '내가 추가',
      title: draft.title,
      description: draft.description,
      d_day_offset: offset,
      start_date: draft.start_date,
      has_legal_deadline: false,
      deadline_date: null,
      deadline_days: null,
      penalty: null,
      method: null,
      contact: null,
      region_hint: null,
      citations: [],
    };
    await addCustomItem(newItem);
    setCustomItems((prev) => [...prev, newItem]);
    setAddItemOpen(false);
  }

  async function handleRemoveCustomItem(item: ChecklistItem) {
    const key = itemKey(item);
    const confirmed = await confirmAsync(
      '항목 삭제',
      `"${item.title}" 을(를) 삭제할까요?`,
    );
    if (!confirmed) return;
    await removeCustomItem(key);
    setCustomItems((prev) =>
      prev.filter((it) => itemKey(it) !== key),
    );
  }

  const completedCount = result
    ? result.items.filter((it) => completions[itemKey(it)]).length
    : 0;
  const progress =
    result && result.items.length > 0
      ? Math.round((completedCount / result.items.length) * 100)
      : 0;

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.container}>
          {mode === 'form' ? (
            <FormView
              editing={result !== null}
              onCancelEdit={() => setMode('result')}
              household={household}
              setHousehold={(v) => {
                setHousehold(v);
                if (v === '자취') {
                  // 자취 전환 시 자녀 관련 상태 자동 리셋
                  setHasChildren(false);
                  setSchoolLevel(null);
                }
              }}
              contracts={contracts}
              toggleContract={toggleContract}
              region={region}
              openRegionPicker={() => setRegionPickerOpen(true)}
              moveDate={moveDate}
              openDatePicker={() => setDatePickerOpen(true)}
              hasPet={hasPet}
              setHasPet={setHasPet}
              hasCar={hasCar}
              setHasCar={(v) => {
                setHasCar(v);
                if (!v) setCarCount(1); // 자동차 해제 시 대수 리셋
              }}
              carCount={carCount}
              setCarCount={setCarCount}
              hasChildren={hasChildren}
              setHasChildren={setHasChildren}
              schoolLevel={schoolLevel}
              setSchoolLevel={setSchoolLevel}
              isForeigner={isForeigner}
              setIsForeigner={setIsForeigner}
              isApartment={isApartment}
              setIsApartment={setIsApartment}
              isEmployed={isEmployed}
              setIsEmployed={setIsEmployed}
              receivesWelfare={receivesWelfare}
              setReceivesWelfare={setReceivesWelfare}
              needsIdReissue={needsIdReissue}
              setNeedsIdReissue={setNeedsIdReissue}
              concernLabels={concernLabels}
              toggleConcern={toggleConcern}
              freeText={freeText}
              setFreeText={setFreeText}
              movingStyle={movingStyle}
              setMovingStyle={setMovingStyle}
              extra={extra}
              toggleExtra={toggleExtra}
              loading={loading}
              loadingMessage={loadingMessage}
              error={error}
              submit={submit}
              onResetForm={handleResetForm}
            />
          ) : (
            result && (
              <ResultView
                result={result}
                region={region}
                customItems={customItems}
                completions={completions}
                progress={progress}
                completedCount={completedCount}
                onToggle={handleToggle}
                onShare={handleShare}
                onNew={handleNew}
                onEditConditions={handleEditConditions}
                onAddCustomItem={() => setAddItemOpen(true)}
                onRemoveCustomItem={handleRemoveCustomItem}
                onItemPress={(item, _idx) =>
                  router.push({
                    pathname: '/checklist/[id]',
                    params: { id: itemKey(item) },
                  })
                }
              />
            )
          )}
        </ScrollView>
      </KeyboardAvoidingView>

      <DatePickerModal
        visible={datePickerOpen}
        value={moveDate}
        minDate={today()}
        onClose={() => setDatePickerOpen(false)}
        onSelect={setMoveDate}
      />
      <RegionPickerModal
        visible={regionPickerOpen}
        value={region}
        onClose={() => setRegionPickerOpen(false)}
        onSelect={setRegion}
      />
      <AddItemModal
        visible={addItemOpen}
        onClose={() => setAddItemOpen(false)}
        onSubmit={handleAddCustomItem}
        moveDate={moveDate}
      />
    </SafeAreaView>
  );
}

// ===== Add Custom Item Modal =====

function AddItemModal({
  visible,
  onClose,
  onSubmit,
  moveDate,
}: {
  visible: boolean;
  onClose: () => void;
  onSubmit: (draft: {
    title: string;
    category: string;
    description: string;
    start_date: string;
  }) => void;
  moveDate: string;
}) {
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('');
  const [description, setDescription] = useState('');
  const [startDate, setStartDate] = useState<string>(moveDate);
  const [datePickerOpen, setDatePickerOpen] = useState(false);

  // 모달이 열릴 때마다 이사일 기준으로 startDate 초기화
  React.useEffect(() => {
    if (visible) setStartDate(moveDate);
  }, [visible, moveDate]);

  function reset() {
    setTitle('');
    setCategory('');
    setDescription('');
    setStartDate(moveDate);
  }

  function submit() {
    if (!title.trim()) return;
    onSubmit({
      title: title.trim(),
      category: category.trim() || '내가 추가',
      description: description.trim(),
      start_date: startDate,
    });
    reset();
  }

  // 이사일 대비 offset 계산 (미리보기 라벨용)
  const offsetLabel = (() => {
    if (!startDate || !moveDate) return '';
    const [sy, sm, sd] = startDate.split('-').map(Number);
    const [my, mm, md] = moveDate.split('-').map(Number);
    const s = new Date(sy, sm - 1, sd).getTime();
    const m = new Date(my, mm - 1, md).getTime();
    const offset = Math.round((s - m) / (1000 * 60 * 60 * 24));
    return formatMoveOffsetLabel(offset);
  })();

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <View style={styles.modalBackdrop}>
          {/* 카드 위 빈 영역 — 탭하면 닫힘 */}
          <Pressable style={{ flex: 1 }} onPress={onClose} />
          {/* 카드 본체 */}
          <View style={styles.modalCard}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>항목 추가</Text>
              <Pressable onPress={onClose} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.textMute} />
              </Pressable>
            </View>
            <ScrollView
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              <Text style={styles.modalLabel}>제목 *</Text>
              <TextInput
                value={title}
                onChangeText={setTitle}
                placeholder="예: 새집 커튼 주문"
                placeholderTextColor={colors.textMute}
                style={styles.modalInput}
              />

              <Text style={styles.modalLabel}>카테고리 (선택)</Text>
              <TextInput
                value={category}
                onChangeText={setCategory}
                placeholder="예: 가전·가구 / 인테리어"
                placeholderTextColor={colors.textMute}
                style={styles.modalInput}
              />

              <Text style={styles.modalLabel}>설명 (선택)</Text>
              <TextInput
                value={description}
                onChangeText={setDescription}
                placeholder="간단한 메모"
                placeholderTextColor={colors.textMute}
                style={[styles.modalInput, { height: 70 }]}
                multiline
                textAlignVertical="top"
              />

              <Text style={styles.modalLabel}>할 일 날짜 *</Text>
              <Pressable
                style={styles.selector}
                onPress={() => setDatePickerOpen(true)}
              >
                <Ionicons
                  name="calendar-outline"
                  size={18}
                  color={colors.primary}
                />
                <Text style={styles.selectorText}>
                  {formatDateLabel(startDate)}
                </Text>
                <Ionicons
                  name="chevron-forward"
                  size={18}
                  color={colors.textMute}
                />
              </Pressable>
              {!!offsetLabel && (
                <Text style={styles.modalHint}>
                  📅 이사일({moveDate}) 기준 · {offsetLabel}
                </Text>
              )}

              <Pressable
                style={[
                  styles.submitBtn,
                  (!title.trim() || !startDate) && { opacity: 0.5 },
                ]}
                onPress={submit}
                disabled={!title.trim() || !startDate}
              >
                <Text style={styles.submitText}>추가</Text>
              </Pressable>
            </ScrollView>
          </View>
        </View>
      </KeyboardAvoidingView>

      <DatePickerModal
        visible={datePickerOpen}
        value={startDate}
        onClose={() => setDatePickerOpen(false)}
        onSelect={setStartDate}
      />
    </Modal>
  );
}

// ===== Form sub-view =====

interface FormViewProps {
  editing: boolean;
  onCancelEdit: () => void;
  household: HouseholdType;
  setHousehold: (v: HouseholdType) => void;
  contracts: ContractType[];
  toggleContract: (v: ContractType) => void;
  region: string;
  openRegionPicker: () => void;
  moveDate: string;
  openDatePicker: () => void;
  hasPet: boolean;
  setHasPet: (v: boolean) => void;
  hasCar: boolean;
  setHasCar: (v: boolean) => void;
  carCount: number;
  setCarCount: (v: number) => void;
  hasChildren: boolean;
  setHasChildren: (v: boolean) => void;
  schoolLevel: SchoolLevel | null;
  setSchoolLevel: (v: SchoolLevel | null) => void;
  isForeigner: boolean;
  setIsForeigner: (v: boolean) => void;
  isApartment: boolean;
  setIsApartment: (v: boolean) => void;
  isEmployed: boolean;
  setIsEmployed: (v: boolean) => void;
  receivesWelfare: boolean;
  setReceivesWelfare: (v: boolean) => void;
  needsIdReissue: boolean;
  setNeedsIdReissue: (v: boolean) => void;
  concernLabels: string[];
  toggleConcern: (label: string) => void;
  freeText: string;
  setFreeText: (v: string) => void;
  movingStyle: MovingStyle;
  setMovingStyle: (v: MovingStyle) => void;
  extra: Record<keyof typeof EXTRA_LABELS, boolean>;
  toggleExtra: (k: keyof typeof EXTRA_LABELS) => void;
  loading: boolean;
  loadingMessage: string;
  error: string | null;
  submit: () => void;
  onResetForm: () => void;
}

function FormView(props: FormViewProps) {
  const {
    editing,
    onCancelEdit,
    household,
    setHousehold,
    contracts,
    toggleContract,
    region,
    openRegionPicker,
    moveDate,
    openDatePicker,
    hasPet,
    setHasPet,
    hasCar,
    setHasCar,
    carCount,
    setCarCount,
    hasChildren,
    setHasChildren,
    schoolLevel,
    setSchoolLevel,
    isForeigner,
    setIsForeigner,
    isApartment,
    setIsApartment,
    isEmployed,
    setIsEmployed,
    receivesWelfare,
    setReceivesWelfare,
    needsIdReissue,
    setNeedsIdReissue,
    concernLabels,
    toggleConcern,
    freeText,
    setFreeText,
    movingStyle,
    setMovingStyle,
    extra,
    toggleExtra,
    loading,
    loadingMessage,
    error,
    submit,
    onResetForm,
  } = props;

  const isSelfOwned = contracts.includes('자가');

  return (
    <>
      {editing ? (
        <View style={styles.editingBanner}>
          <Ionicons name="options" size={16} color={colors.primary} />
          <Text style={styles.editingBannerText}>
            조건 수정 중 — 제출하면 체크리스트를 재생성해요. 완료 상태는 유지돼요.
          </Text>
          <Pressable onPress={onCancelEdit} hitSlop={8}>
            <Ionicons name="close" size={18} color={colors.textMute} />
          </Pressable>
        </View>
      ) : null}
      <View style={styles.formTitleRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.h1}>이사 체크리스트</Text>
          <Text style={styles.h1Sub}>
            {editing
              ? '조건을 바꾼 뒤 아래 버튼을 눌러 재생성하세요'
              : '조건을 입력하면 AI가 체크리스트를 만들어줍니다'}
          </Text>
        </View>
        <Pressable
          onPress={onResetForm}
          style={styles.formResetBtn}
          hitSlop={8}
        >
          <Ionicons name="refresh" size={18} color={colors.primary} />
          <Text style={styles.formResetText}>초기화</Text>
        </Pressable>
      </View>

      {/* ───────── 1단계. 기본 정보 (필수) ───────── */}
      <View style={styles.stepHeader}>
        <View style={styles.stepBadge}><Text style={styles.stepBadgeText}>1</Text></View>
        <Text style={styles.stepTitle}>기본 정보</Text>
        <Text style={styles.stepHint}>필수</Text>
      </View>

      <Section label="이사 예정일">
        <Pressable style={styles.selector} onPress={openDatePicker}>
          <Ionicons name="calendar-outline" size={18} color={colors.primary} />
          <Text style={styles.selectorText}>{formatDateLabel(moveDate)}</Text>
          <Ionicons name="chevron-forward" size={18} color={colors.textMute} />
        </Pressable>
      </Section>

      <Section label="지역">
        <Pressable style={styles.selector} onPress={openRegionPicker}>
          <Ionicons name="location-outline" size={18} color={colors.primary} />
          <Text style={styles.selectorText} numberOfLines={1}>
            {region || '지역 선택'}
          </Text>
          <Ionicons name="chevron-forward" size={18} color={colors.textMute} />
        </Pressable>
      </Section>

      <Section label="계약 유형">
        <View style={styles.multiRow}>
          {CONTRACTS.map((c) => {
            const active = contracts.includes(c);
            return (
              <Pressable
                key={c}
                onPress={() => toggleContract(c)}
                style={[styles.multiBtn, active && styles.multiBtnActive]}
              >
                <Ionicons
                  name={active ? 'checkmark-circle' : 'ellipse-outline'}
                  size={16}
                  color={active ? '#fff' : colors.textMute}
                />
                <Text
                  style={[
                    styles.multiBtnText,
                    active && styles.multiBtnTextActive,
                  ]}
                >
                  {c}
                </Text>
              </Pressable>
            );
          })}
        </View>
        {isSelfOwned && (
          <View style={styles.inlineHint}>
            <Ionicons name="information-circle" size={14} color={colors.primaryLight} />
            <Text style={styles.inlineHintText}>
              자가는 등기부 확인이 불필요해요. 체크리스트는 이사 행정·생활 절차 중심으로 나와요.
            </Text>
          </View>
        )}
      </Section>

      <Section label="세대 유형">
        <SegmentGroup options={HOUSEHOLDS} value={household} onChange={setHousehold} />
      </Section>

      {household === '가족' && (
        <Section label="자녀 유무">
          <View style={styles.multiRow}>
            <Pressable
              onPress={() => setHasChildren(false)}
              style={[styles.multiBtn, !hasChildren && styles.multiBtnActive]}
            >
              <Ionicons
                name={!hasChildren ? 'checkmark-circle' : 'ellipse-outline'}
                size={16}
                color={!hasChildren ? '#fff' : colors.textMute}
              />
              <Text
                style={[
                  styles.multiBtnText,
                  !hasChildren && styles.multiBtnTextActive,
                ]}
              >
                없음
              </Text>
            </Pressable>
            <Pressable
              onPress={() => setHasChildren(true)}
              style={[styles.multiBtn, hasChildren && styles.multiBtnActive]}
            >
              <Ionicons
                name={hasChildren ? 'checkmark-circle' : 'ellipse-outline'}
                size={16}
                color={hasChildren ? '#fff' : colors.textMute}
              />
              <Text
                style={[
                  styles.multiBtnText,
                  hasChildren && styles.multiBtnTextActive,
                ]}
              >
                있음
              </Text>
            </Pressable>
          </View>
          {hasChildren && (
            <View style={{ marginTop: spacing.sm }}>
              <Text style={styles.subLabel}>자녀 학교급</Text>
              <SegmentGroup
                options={SCHOOL_LEVELS}
                value={schoolLevel ?? '초등'}
                onChange={(v: SchoolLevel) => setSchoolLevel(v)}
              />
            </View>
          )}
        </Section>
      )}

      <Section label="이사 스타일">
        <View style={styles.multiRow}>
          {MOVING_STYLES.map((m) => {
            const active = movingStyle === m.value;
            return (
              <Pressable
                key={m.value}
                onPress={() => setMovingStyle(m.value)}
                style={[styles.multiBtn, active && styles.multiBtnActive]}
              >
                <Ionicons
                  name={m.icon as any}
                  size={16}
                  color={active ? '#fff' : colors.textMute}
                />
                <Text
                  style={[
                    styles.multiBtnText,
                    active && styles.multiBtnTextActive,
                  ]}
                >
                  {m.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </Section>

      {/* ───────── 2단계. 해당 사항 체크 ───────── */}
      <View style={styles.stepHeader}>
        <View style={styles.stepBadge}><Text style={styles.stepBadgeText}>2</Text></View>
        <Text style={styles.stepTitle}>해당 사항 체크</Text>
        <Text style={styles.stepHint}>다중 선택</Text>
      </View>

      <SubSection icon="person" label="나의 상황">
        <View style={styles.toggles}>
          {/* 사용 빈도 순: 직장인 → 학생 → 외국인 → 병역 → 복지 → 주민등록 재발급 */}
          <ToggleChip
            icon="briefcase"
            label="직장인"
            active={isEmployed}
            onPress={() => setIsEmployed(!isEmployed)}
          />
          <ToggleChip
            icon="school"
            label="학생"
            active={extra.student}
            onPress={() => toggleExtra('student')}
          />
          <ToggleChip
            icon="globe"
            label="외국인"
            active={isForeigner}
            onPress={() => setIsForeigner(!isForeigner)}
          />
          <ToggleChip
            icon="shield"
            label="병역 대상자"
            active={extra.militaryDuty}
            onPress={() => toggleExtra('militaryDuty')}
          />
          <ToggleChip
            icon="heart"
            label="복지급여 수급"
            active={receivesWelfare}
            onPress={() => setReceivesWelfare(!receivesWelfare)}
          />
          <ToggleChip
            icon="card"
            label="주민등록증 재발급"
            active={needsIdReissue}
            onPress={() => setNeedsIdReissue(!needsIdReissue)}
          />
        </View>
      </SubSection>

      <SubSection icon="people" label="함께 이동">
        <View style={styles.toggles}>
          {/* 사용 빈도 순: 자동차 → 반려동물 */}
          <ToggleChip
            icon="car"
            label="자동차"
            active={hasCar}
            onPress={() => setHasCar(!hasCar)}
          />
          <ToggleChip
            icon="paw"
            label="반려동물"
            active={hasPet}
            onPress={() => setHasPet(!hasPet)}
          />
        </View>
        {hasCar && (
          <View style={styles.subOption}>
            <View style={styles.subOptionBranch} />
            <View style={{ flex: 1 }}>
              <Text style={styles.subLabel}>대수</Text>
              <View style={styles.multiRow}>
                {[1, 2, 3, 4].map((n) => {
                  const active = carCount === n;
                  const label = n === 4 ? '4대+' : `${n}대`;
                  return (
                    <Pressable
                      key={n}
                      onPress={() => setCarCount(n)}
                      style={[
                        styles.multiBtn,
                        active && styles.multiBtnActive,
                      ]}
                    >
                      <Text
                        style={[
                          styles.multiBtnText,
                          active && styles.multiBtnTextActive,
                        ]}
                      >
                        {label}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          </View>
        )}
      </SubSection>

      <SubSection icon="business" label="집 형태">
        <View style={styles.toggles}>
          <ToggleChip
            icon="business"
            label="아파트·오피스텔"
            active={isApartment}
            onPress={() => setIsApartment(!isApartment)}
          />
          <ToggleChip
            icon="trending-up"
            label="고층 이사 (엘베·곤도라)"
            active={extra.highFloor}
            onPress={() => toggleExtra('highFloor')}
          />
        </View>
      </SubSection>

      <SubSection icon="cube" label="이사 시 처리할 것">
        <View style={styles.toggles}>
          {/* 사용 빈도 순: 인터넷 이전 → 대형 폐기물 */}
          <ToggleChip
            icon="wifi"
            label="인터넷 이전"
            active={extra.internet}
            onPress={() => {
              // 인터넷 이전 끄면 하위 TV 이전도 같이 리셋 (일관성)
              if (extra.internet && extra.tvTransfer) {
                toggleExtra('tvTransfer');
              }
              toggleExtra('internet');
            }}
          />
          <ToggleChip
            icon="trash"
            label="대형 폐기물"
            active={extra.largeWaste}
            onPress={() => toggleExtra('largeWaste')}
          />
        </View>
        {extra.internet && (
          <View style={styles.subOption}>
            <View style={styles.subOptionBranch} />
            <ToggleChip
              icon="tv"
              label="TV도 같이 이전"
              active={extra.tvTransfer}
              onPress={() => toggleExtra('tvTransfer')}
            />
          </View>
        )}
      </SubSection>

      {/* ───────── 3단계. 걱정거리 (선택) ───────── */}
      <View style={styles.stepHeader}>
        <View style={styles.stepBadge}><Text style={styles.stepBadgeText}>3</Text></View>
        <Text style={styles.stepTitle}>이사 관련 걱정거리</Text>
        <Text style={styles.stepHint}>선택 · 다중</Text>
      </View>
      {concernLabels.length > 0 && (
        <Text style={styles.stepCount}>· {concernLabels.length}개 선택됨</Text>
      )}
      <View style={styles.toggles}>
        {CONCERN_OPTIONS.map((opt) => {
          const active = concernLabels.includes(opt.label);
          return (
            <ToggleChip
              key={opt.id}
              icon={opt.icon as any}
              label={opt.label}
              active={active}
              onPress={() => toggleConcern(opt.label)}
            />
          );
        })}
      </View>

      {/* ───────── 4단계. 기타 특이사항 (자유 텍스트, AI 만 호출) ───────── */}
      <View style={styles.stepHeader}>
        <View style={styles.stepBadge}><Text style={styles.stepBadgeText}>4</Text></View>
        <Text style={styles.stepTitle}>기타 특이사항</Text>
        <Text style={styles.stepHint}>선택 · AI 가 자유 텍스트만 분석</Text>
      </View>
      <Text style={styles.stepCount}>
        토글로 못 잡는 상황을 적으면 AI 가 추가 항목을 찾아드려요. (예: "전세금 미반환", "신축 입주 하자 점검", "해외에서 귀국")
      </Text>
      <TextInput
        value={freeText}
        onChangeText={setFreeText}
        placeholder="비워두면 AI 호출 없이 빠르게 진행돼요 (선택)"
        placeholderTextColor={colors.textMute}
        multiline
        textAlignVertical="top"
        maxLength={500}
        style={styles.freeTextInput}
      />
      {freeText.length > 0 && (
        <Text style={styles.stepCount}>{freeText.length} / 500자 · AI 분석 포함됨</Text>
      )}

      <Pressable
        style={[styles.submitBtn, loading && { opacity: 0.6 }]}
        onPress={submit}
        disabled={loading}
      >
        {loading ? (
          <>
            <ActivityIndicator color="#fff" />
            <Text style={styles.submitText}>{loadingMessage}</Text>
          </>
        ) : (
          <Text style={styles.submitText}>
            {editing ? '체크리스트 재생성' : '체크리스트 생성'}
          </Text>
        )}
      </Pressable>

      {error && (
        <View style={styles.errorBox}>
          <Ionicons name="warning" size={16} color={colors.danger} />
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}
    </>
  );
}

// Step/Sub 섹션 컴포넌트
function SubSection({
  icon,
  label,
  children,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.subSection}>
      <View style={styles.subSectionHeader}>
        <Ionicons name={icon} size={14} color={colors.primary} />
        <Text style={styles.subSectionLabel}>{label}</Text>
      </View>
      {children}
    </View>
  );
}

// ===== Result sub-view =====

function ResultView({
  result,
  region,
  customItems,
  completions,
  progress,
  completedCount,
  onToggle,
  onShare,
  onNew,
  onEditConditions,
  onAddCustomItem,
  onRemoveCustomItem,
  onItemPress,
}: {
  result: ChecklistResponse;
  region: string;
  customItems: ChecklistItem[];
  completions: CompletionMap;
  progress: number;
  completedCount: number;
  onToggle: (item: ChecklistItem) => void;
  onShare: () => void;
  onNew: () => void;
  onEditConditions: () => void;
  onAddCustomItem: () => void;
  onRemoveCustomItem: (item: ChecklistItem) => void;
  onItemPress: (item: ChecklistItem, idx: number) => void;
}) {
  const aiCount = result.items.length;
  const [collapsedPhases, setCollapsedPhases] = useState<Record<string, boolean>>({});
  const togglePhase = (k: string) =>
    setCollapsedPhases((p) => ({ ...p, [k]: !p[k] }));
  return (
    <>
      <View style={styles.resultHeaderRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.h1}>체크리스트</Text>
          <View style={styles.resultMetaRow}>
            <Ionicons name="location" size={13} color={colors.primary} />
            <Text style={styles.resultRegionText} numberOfLines={1}>
              {region}
            </Text>
          </View>
          <Text style={styles.h1Sub}>
            AI {aiCount}개{customItems.length > 0 ? ` + 내 ${customItems.length}개` : ''}
          </Text>
        </View>
        <Pressable onPress={onEditConditions} style={styles.iconBtn}>
          <Ionicons name="options-outline" size={22} color={colors.primary} />
        </Pressable>
        <Pressable onPress={onShare} style={styles.iconBtn}>
          <Ionicons name="share-outline" size={22} color={colors.primary} />
        </Pressable>
        <Pressable onPress={onNew} style={styles.iconBtn}>
          <Ionicons name="refresh" size={22} color={colors.primary} />
        </Pressable>
      </View>

      {result.warning && (
        <View style={styles.warningBox}>
          <Ionicons name="construct" size={14} color={colors.warning} />
          <Text style={styles.warningText}>{result.warning}</Text>
        </View>
      )}

      <View style={styles.progressCard}>
        <View style={styles.progressHeader}>
          <Text style={styles.progressLabel}>진행률</Text>
          <Text style={styles.progressValue}>
            {completedCount} / {result.items.length} · {progress}%
          </Text>
        </View>
        <View style={styles.progressBar}>
          <View style={[styles.progressFill, { width: `${progress}%` }]} />
        </View>
      </View>

      {(() => {
        // 4 phase 분류: 이사 전 / 당일 / 후 / 참고·안내
        type Phase = 'before' | 'day' | 'after' | 'reference';
        const REFERENCE_PAT = /(안내|방법|기준|분쟁|수선의무|증감|갱신요구권|주의사항)/;
        const classify = (it: ChecklistItem): Phase => {
          const t = `${it.title || ''} ${it.category || ''}`;
          if (REFERENCE_PAT.test(t)) return 'reference';
          if (it.d_day_offset < 0) return 'before';
          if (it.d_day_offset === 0) return 'day';
          return 'after';
        };
        const groups: Record<Phase, { it: ChecklistItem; idx: number }[]> = {
          before: [],
          day: [],
          after: [],
          reference: [],
        };
        result.items.forEach((it, idx) => groups[classify(it)].push({ it, idx }));
        const phaseMeta: {
          key: Phase;
          label: string;
          sub: string;
          emoji: string;
        }[] = [
          { key: 'before', label: '이사 전', sub: '준비·예약·포장', emoji: '📦' },
          { key: 'day', label: '이사 당일', sub: '명의변경·이사 작업', emoji: '🚚' },
          { key: 'after', label: '이사 후', sub: '행정 신고·등록', emoji: '✅' },
          {
            key: 'reference',
            label: '참고·안내',
            sub: '분쟁 대응·법적 권리 참고',
            emoji: '📖',
          },
        ];
        return phaseMeta.map((p) => {
          const list = groups[p.key];
          if (list.length === 0) return null;
          const doneInPhase = list.filter(
            ({ it }) => !!completions[itemKey(it)]
          ).length;
          const allDone = doneInPhase === list.length && list.length > 0;
          const collapsed = !!collapsedPhases[p.key];
          return (
            <View key={p.key}>
              <Pressable
                onPress={() => togglePhase(p.key)}
                style={styles.phaseHeader}
                hitSlop={4}
                accessibilityRole="button"
                accessibilityLabel={`${p.label} 섹션, ${doneInPhase}/${list.length} 완료`}
                accessibilityState={{ expanded: !collapsed }}
              >
                <Text style={styles.phaseEmoji}>{p.emoji}</Text>
                <Text style={styles.phaseLabel}>{p.label}</Text>
                <Text
                  style={[
                    styles.phaseCount,
                    allDone && styles.phaseCountDone,
                  ]}
                >
                  {doneInPhase}/{list.length}
                </Text>
                <Text style={styles.phaseSub}>{p.sub}</Text>
                <Ionicons
                  name={collapsed ? 'chevron-down' : 'chevron-up'}
                  size={18}
                  color={colors.textMute}
                />
              </Pressable>
              {!collapsed &&
                list.map(({ it, idx }) => (
                  <ChecklistCard
                    key={`${it.category}-${idx}`}
                    item={it}
                    index={idx}
                    done={!!completions[itemKey(it)]}
                    onToggle={() => onToggle(it)}
                    onPress={() => onItemPress(it, idx)}
                  />
                ))}
            </View>
          );
        });
      })()}

      {/* 내가 추가한 항목 섹션 */}
      {customItems.length > 0 && (
        <View style={styles.customSectionHeader}>
          <Ionicons name="person-circle" size={16} color={colors.accent} />
          <Text style={styles.customSectionTitle}>내가 추가한 항목</Text>
        </View>
      )}
      {customItems.map((it, cIdx) => {
        const combinedIdx = aiCount + cIdx;
        return (
          <ChecklistCard
            key={`custom-${it.category}-${cIdx}`}
            item={it}
            index={combinedIdx}
            done={!!completions[itemKey(it)]}
            onToggle={() => onToggle(it)}
            onPress={() => onItemPress(it, combinedIdx)}
            onRemove={() => onRemoveCustomItem(it)}
          />
        );
      })}

      {/* 항목 추가 버튼 */}
      <Pressable style={styles.addItemBtn} onPress={onAddCustomItem}>
        <Ionicons name="add-circle" size={20} color={colors.primary} />
        <Text style={styles.addItemText}>항목 직접 추가하기</Text>
      </Pressable>
    </>
  );
}

function ChecklistCard({
  item,
  index,
  done,
  onToggle,
  onPress,
  onRemove,
}: {
  item: ChecklistItem;
  index: number;
  done: boolean;
  onToggle: () => void;
  onPress: () => void;
  onRemove?: () => void;
}) {
  const legal = item.has_legal_deadline;
  // D-day 배지는 "이사일 기준" offset 으로 통일 (각 카드마다 고정 값)
  // 예: d_day_offset=-7 → "이사 7일 전", 0 → "이사 당일", +1 → "이사 1일 후"
  const dDay = formatMoveOffsetLabel(item.d_day_offset);
  // 3단계 우선순위 (2026-04-21 직관 단순화):
  //   🔴 필수 — 법정기한 있음 (과태료·페널티 위험)
  //   🟠 중요 — 법정기한 없지만 이사일 ±7일 임박
  //   🔷 참고 — 그 외 (법적 권리 안내 / 장기 준비 / 사후)
  const urgencyColor = legal
    ? colors.danger
    : item.d_day_offset >= -7 && item.d_day_offset <= 7
      ? colors.warning
      : colors.primaryLight;
  return (
    <Pressable
      onPress={onPress}
      android_ripple={{ color: colors.primaryBg }}
      accessibilityRole="button"
      accessibilityLabel={`${item.title} 상세 보기`}
      style={({ pressed }) => [
        styles.itemCard,
        { borderLeftColor: urgencyColor },
        done && styles.itemCardDone,
        pressed && { opacity: 0.7 },
      ]}
    >
      <Pressable onPress={onToggle} hitSlop={12} style={styles.checkbox}>
        <Ionicons
          name={done ? 'checkmark-circle' : 'ellipse-outline'}
          size={24}
          color={done ? colors.success : colors.textMute}
        />
      </Pressable>
      <View style={{ flex: 1 }}>
        <View style={styles.itemHeader}>
          {dDay ? (
            <View
              style={[
                styles.dDayBadge,
                { backgroundColor: done ? colors.textMute : urgencyColor },
              ]}
            >
              <Text style={styles.dDayText}>{dDay}</Text>
            </View>
          ) : null}
          <Text
            style={[
              styles.itemTitle,
              done && styles.strike,
              done && styles.itemTitleDone,
            ]}
          >
            {item.title}
          </Text>
        </View>
        {item.start_date ? (
          <Text style={styles.itemSubDate}>
            시작일: {item.start_date}
          </Text>
        ) : null}
        {item.deadline_date && (
          <View style={styles.deadlineBox}>
            <Ionicons name="alarm" size={14} color={colors.warning} />
            <Text style={styles.deadlineText}>
              마감 {item.deadline_date} ({item.deadline_days}일 기한)
            </Text>
          </View>
        )}
        {item.contact && (
          <View style={styles.metaRow}>
            <Ionicons name="call" size={12} color={colors.success} />
            <Text style={styles.metaContact} numberOfLines={1}>
              {item.contact}
            </Text>
          </View>
        )}
        {item.citations.length > 0 && (
          <View style={styles.citationShortRow}>
            <Ionicons name="library" size={12} color={colors.primaryLight} />
            <Text style={styles.citationShort}>
              {item.citations[0].law_name} {item.citations[0].article}
              {item.citations.length > 1 && ` 외 ${item.citations.length - 1}건`}
            </Text>
          </View>
        )}
      </View>
      {onRemove ? (
        <Pressable onPress={onRemove} hitSlop={12} style={styles.removeBtn}>
          <Ionicons name="trash-outline" size={18} color={colors.danger} />
        </Pressable>
      ) : (
        <Ionicons name="chevron-forward" size={18} color={colors.textMute} />
      )}
    </Pressable>
  );
}

// ===== Reusable bits =====

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionLabel}>{label}</Text>
      {children}
    </View>
  );
}

function SegmentGroup<T extends string>({
  options,
  value,
  onChange,
}: {
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <View style={styles.segment}>
      {options.map((o) => (
        <Pressable
          key={o}
          onPress={() => onChange(o)}
          style={[styles.segmentBtn, value === o && styles.segmentBtnActive]}
        >
          <Text
            style={[
              styles.segmentText,
              value === o && styles.segmentTextActive,
            ]}
          >
            {o}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

function ToggleChip({
  icon,
  label,
  active,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.chip, active && styles.chipActive]}
    >
      <Ionicons
        name={icon}
        size={16}
        color={active ? '#fff' : colors.textSub}
      />
      <Text style={[styles.chipText, active && { color: '#fff' }]}>
        {label}
      </Text>
    </Pressable>
  );
}

// ===== Styles =====

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.lg, paddingBottom: spacing.xxl },
  editingBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: colors.primaryBg,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.primaryLight,
  },
  editingBannerText: {
    ...typography.caption,
    flex: 1,
    color: colors.primary,
    fontWeight: '600',
  },
  h1: { ...typography.display },
  h1Sub: {
    ...typography.caption,
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  formTitleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  formResetBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: radius.sm,
    backgroundColor: colors.primary + '10',
  },
  formResetText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  // 3단계 섹션 헤더
  stepHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.xl,
    marginBottom: spacing.sm,
    paddingBottom: spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  stepBadge: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepBadgeText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '800',
  },
  stepTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.text,
    flex: 1,
  },
  stepHint: {
    fontSize: 11,
    color: colors.textMute,
    fontWeight: '600',
  },
  stepCount: {
    fontSize: 12,
    color: colors.primary,
    marginBottom: spacing.sm,
    lineHeight: 17,
  },
  freeTextInput: {
    minHeight: 80,
    backgroundColor: colors.cardBg,
    borderWidth: 1,
    borderColor: colors.borderLight,
    borderRadius: radius.md,
    padding: spacing.md,
    fontSize: 14,
    lineHeight: 20,
    color: colors.text,
    marginBottom: spacing.sm,
  },
  // 2단계 서브 섹션 (나의 상황/함께 이동 등)
  subSection: {
    marginTop: spacing.md,
  },
  subSectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: spacing.xs,
  },
  subSectionLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.primary,
  },
  subLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.textSub,
    marginBottom: 4,
  },
  inlineHint: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    marginTop: spacing.xs,
    padding: spacing.sm,
    backgroundColor: colors.primary + '10',
    borderRadius: radius.sm,
  },
  inlineHintText: {
    flex: 1,
    fontSize: 12,
    color: colors.textSub,
    lineHeight: 18,
  },
  // 계층형 하위 옵션 (예: 인터넷 → TV, 자녀 → 학교급)
  // 좌측 들여쓰기 제거 — 상위 라벨("대수")만으로 계층 표현 충분.
  subOption: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xs,
  },
  subOptionBranch: {
    // branch 선 제거 — 들여쓰기 공백이 넓어 UX 해침.
    width: 0,
    height: 0,
  },
  // result view phase 헤더
  phaseHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
    paddingBottom: spacing.xs,
    borderBottomWidth: 2,
    borderBottomColor: colors.primary,
  },
  phaseEmoji: {
    fontSize: 18,
  },
  phaseLabel: {
    fontSize: 15,
    fontWeight: '800',
    color: colors.text,
  },
  phaseCount: {
    fontSize: 12,
    fontWeight: '700',
    color: '#fff',
    backgroundColor: colors.primary,
    paddingHorizontal: 9,
    paddingVertical: 3,
    borderRadius: 11,
    minWidth: 36,
    textAlign: 'center',
    overflow: 'hidden',
  },
  phaseCountDone: {
    backgroundColor: colors.success,
  },
  phaseSub: {
    fontSize: 12,
    color: colors.textMute,
    marginLeft: 'auto',
    lineHeight: 17,
  },
  resultHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  resultMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: spacing.xs,
  },
  resultRegionText: {
    ...typography.captionBold,
    color: colors.primary,
    fontSize: 12,
    flex: 1,
  },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.cardBg,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
  },
  section: { marginBottom: spacing.lg },
  sectionLabel: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.sm,
    letterSpacing: -0.2,
  },
  selector: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md + 2,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  selectorText: {
    flex: 1,
    ...typography.bodyBold,
  },
  segment: { flexDirection: 'row', gap: spacing.xs },
  segmentBtn: {
    flex: 1,
    paddingVertical: spacing.md - 2,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.cardBg,
    alignItems: 'center',
  },
  segmentBtnActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  segmentText: { ...typography.body, fontWeight: '600' },
  segmentTextActive: { color: '#fff' },
  multiRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  multiBtn: {
    // flexBasis 가 화면 너비 나눗셈으로 4버튼 한 줄 균등 배치. 공간 부족하면 flexWrap 이
    // 자연스럽게 줄바꿈. flex:1 단독이면 subOption padding·branch 12px 와 조합돼 우측 overflow.
    flexGrow: 1,
    flexBasis: 56,
    minWidth: 56,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.md - 2,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.cardBg,
  },
  multiBtnActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  multiBtnText: { ...typography.body, fontWeight: '600' },
  multiBtnTextActive: { color: '#fff' },
  toggles: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.cardBg,
  },
  chipActive: {
    backgroundColor: colors.primaryLight,
    borderColor: colors.primaryLight,
  },
  chipText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textSub,
  },
  concernGroups: { gap: spacing.md },
  concernGroup: {},
  concernGroupLabel: {
    ...typography.captionBold,
    color: colors.primary,
    marginBottom: spacing.xs,
  },
  submitBtn: {
    backgroundColor: colors.primary,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    alignItems: 'center',
    marginTop: spacing.md,
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  submitText: { color: '#fff', fontSize: 17, fontWeight: '800' },

  // Custom items 섹션
  customSectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
    paddingHorizontal: spacing.xs,
  },
  customSectionTitle: {
    ...typography.captionBold,
    color: colors.accent,
    fontSize: 13,
  },
  addItemBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.primaryLight,
    borderStyle: 'dashed',
    backgroundColor: colors.cardBg,
    marginTop: spacing.sm,
  },
  addItemText: {
    color: colors.primary,
    fontSize: 14,
    fontWeight: '700',
  },
  removeBtn: {
    padding: spacing.xs,
  },

  // Add Item Modal
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'flex-end',
  },
  modalCard: {
    backgroundColor: colors.cardBg,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    maxHeight: '85%',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  modalTitle: { ...typography.subtitle },
  modalLabel: {
    ...typography.captionBold,
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
  },
  modalInput: {
    backgroundColor: colors.bg,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    fontSize: 14,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
  },
  modalHint: {
    fontSize: 12,
    color: colors.primary,
    marginTop: spacing.xs,
    fontWeight: '600',
  },
  errorBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.dangerBg,
    padding: spacing.md,
    borderRadius: radius.md,
    marginTop: spacing.md,
  },
  errorText: { color: colors.danger, fontSize: 13, fontWeight: '600', flex: 1 },
  warningBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.warningBg,
    padding: spacing.sm,
    borderRadius: radius.sm,
    marginBottom: spacing.md,
  },
  warningText: { color: colors.warning, fontSize: 12, fontWeight: '600', flex: 1 },
  progressCard: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.md,
  },
  progressHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  progressLabel: { ...typography.caption, fontWeight: '700' },
  progressValue: { ...typography.caption, fontWeight: '700', color: colors.primary },
  progressBar: {
    height: 8,
    backgroundColor: colors.border,
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: colors.primary,
  },
  itemCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    borderLeftWidth: 4,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: colors.primary,
    shadowOpacity: 0.06,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },
  checkbox: { paddingTop: 2 },
  itemHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: 6,
  },
  dDayBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.pill,
  },
  dDayText: { color: '#fff', fontSize: 12, fontWeight: '800' },
  itemTitle: {
    flex: 1,
    fontSize: 16,
    fontWeight: '800',
    color: colors.text,
    lineHeight: 22,
  },
  strike: { textDecorationLine: 'line-through' },
  itemCardDone: {
    backgroundColor: colors.bg,
    borderLeftColor: colors.border,
    borderColor: colors.border,
    shadowOpacity: 0,
    elevation: 0,
  },
  itemTitleDone: {
    color: colors.textMute,
    fontWeight: '600',
  },
  itemSubDate: {
    fontSize: 12,
    color: colors.textMute,
    fontWeight: '600',
    marginBottom: 6,
    lineHeight: 17,
  },
  deadlineBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: 6,
  },
  deadlineText: { color: colors.warning, fontSize: 12, fontWeight: '700' },
  citationShortRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 8,
    alignSelf: 'flex-start',
    backgroundColor: colors.primaryBg,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radius.sm,
  },
  citationShort: {
    fontSize: 12,
    color: colors.primary,
    fontWeight: '700',
    lineHeight: 17,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 4,
  },
  metaText: {
    fontSize: 12,
    flex: 1,
    fontWeight: '600',
    color: colors.textSub,
    lineHeight: 17,
  },
  metaContact: {
    fontSize: 12,
    flex: 1,
    fontWeight: '700',
    color: colors.success,
    lineHeight: 17,
  },
});
