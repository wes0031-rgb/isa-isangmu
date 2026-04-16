/**
 * Checklist tab — form + saved result with checkbox completion tracking.
 */
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
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
  SchoolLevel,
} from '../../lib/api';
import { CONCERN_GROUPS, CONCERN_OPTIONS } from '../../lib/specialConcerns';
import {
  CompletionMap,
  addCustomItem,
  clearChecklist,
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

const HOUSEHOLDS: HouseholdType[] = ['자취', '신혼', '가족'];
const CONTRACTS: ContractType[] = ['월세', '전세', '자가'];
const SCHOOL_LEVELS: SchoolLevel[] = ['초등', '중등', '고등'];

function todayPlus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

/** 오늘 → start_date 까지의 일수 기반 D-day 문자열 (YYYY-MM-DD, 로컬 기준). */
function computeDDayLabel(startDate: string | null | undefined): string {
  if (!startDate) return '';
  const parts = startDate.split('-').map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return '';
  const [y, m, d] = parts;
  const start = new Date(y, m - 1, d);
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const days = Math.round((start.getTime() - now.getTime()) / 86400000);
  if (days === 0) return 'D-DAY';
  if (days > 0) return `D-${days}`;
  return `D+${-days}`;
}

function formatDateLabel(ymd: string): string {
  if (!ymd) return '날짜 선택';
  const [y, m, d] = ymd.split('-');
  const dateObj = new Date(Number(y), Number(m) - 1, Number(d));
  const dow = ['일', '월', '화', '수', '목', '금', '토'][dateObj.getDay()];
  return `${y}년 ${Number(m)}월 ${Number(d)}일 (${dow})`;
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
  const [hasChildren, setHasChildren] = useState(false);
  const [schoolLevel, setSchoolLevel] = useState<SchoolLevel | null>(null);
  const [isForeigner, setIsForeigner] = useState(false);
  const [isApartment, setIsApartment] = useState(false);
  const [isEmployed, setIsEmployed] = useState(false);
  const [receivesWelfare, setReceivesWelfare] = useState(false);
  const [needsIdReissue, setNeedsIdReissue] = useState(false);
  const [concernLabels, setConcernLabels] = useState<string[]>([]);

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
  useFocusEffect(
    useCallback(() => {
      (async () => {
        const saved = await loadChecklist();
        if (saved) {
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
          setHasChildren(req.has_children);
          setSchoolLevel(req.children_school_level ?? null);
          setIsForeigner(req.is_foreigner ?? false);
          setIsApartment(req.is_apartment ?? false);
          setIsEmployed(req.is_employed ?? false);
          setReceivesWelfare(req.receives_welfare ?? false);
          setNeedsIdReissue(req.needs_id_reissue ?? false);
          setConcernLabels(req.special_concerns ?? []);
          setMode('result');
          const comp = await loadCompletions();
          setCompletions(comp);
          const customs = await loadCustomItems();
          setCustomItems(customs);
        } else {
          // 마이 탭에서 초기화된 직후 → 로컬 state 도 리셋하고 form 모드로
          setResult(null);
          setCompletions({});
          setCustomItems([]);
          setMode('form');
        }
      })();
    }, []),
  );

  function toggleContract(c: ContractType) {
    setContracts((prev) => {
      if (prev.includes(c)) {
        if (prev.length === 1) return prev; // 최소 1개 유지
        return prev.filter((x) => x !== c);
      }
      return [...prev, c];
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
    const payload: ChecklistRequest = {
      household,
      contract: contracts[0],
      contracts,
      region,
      move_date: moveDate,
      has_pet: hasPet,
      has_car: hasCar,
      has_children: hasChildren,
      children_school_level: hasChildren ? schoolLevel : null,
      is_foreigner: isForeigner,
      is_apartment: isApartment,
      is_employed: isEmployed,
      receives_welfare: receivesWelfare,
      needs_id_reissue: needsIdReissue,
      special_concerns: concernLabels,
    };
    try {
      const res = await api.checklist(payload);
      setResult(res);
      await saveChecklist(payload, res);
      // 재생성 시엔 기존 완료 상태 유지 (key 일치하는 항목은 체크된 채로 복원됨)
      if (!isRegenerating) setCompletions({});
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
        const dday = computeDDayLabel(it.start_date);
        return `${done} ${idx + 1}. ${it.title}${dday ? ` (${dday})` : ''}${dl}`;
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

  async function handleNew() {
    const confirmed = await confirmAsync(
      '새 체크리스트',
      '저장된 체크리스트를 지우고 새로 만드시겠어요? (수동 추가 항목·메모도 함께 삭제됩니다)',
    );
    if (!confirmed) return;
    await clearChecklist();
    setResult(null);
    setCompletions({});
    setCustomItems([]);
    setMode('form');
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
    days_from_today: number;
  }) {
    // 사용자가 "며칠 뒤" 로 입력 → 오늘 + N 의 실제 날짜로 저장
    const start = todayPlus(draft.days_from_today);
    const newItem: ChecklistItem = {
      category: draft.category || '내가 추가',
      title: draft.title,
      description: draft.description,
      d_day_offset: draft.days_from_today, // 하위 스키마 호환용 (표시엔 사용 안 함)
      start_date: start,
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
              setHousehold={setHousehold}
              contracts={contracts}
              toggleContract={toggleContract}
              region={region}
              openRegionPicker={() => setRegionPickerOpen(true)}
              moveDate={moveDate}
              openDatePicker={() => setDatePickerOpen(true)}
              hasPet={hasPet}
              setHasPet={setHasPet}
              hasCar={hasCar}
              setHasCar={setHasCar}
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
              loading={loading}
              loadingMessage={loadingMessage}
              error={error}
              submit={submit}
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
                onItemPress={(_item, idx) =>
                  router.push({
                    pathname: '/checklist/[id]',
                    params: { id: String(idx) },
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
      />
    </SafeAreaView>
  );
}

// ===== Add Custom Item Modal =====

function AddItemModal({
  visible,
  onClose,
  onSubmit,
}: {
  visible: boolean;
  onClose: () => void;
  onSubmit: (draft: {
    title: string;
    category: string;
    description: string;
    days_from_today: number;
  }) => void;
}) {
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('');
  const [description, setDescription] = useState('');
  const [days, setDays] = useState('0');

  function reset() {
    setTitle('');
    setCategory('');
    setDescription('');
    setDays('0');
  }

  function submit() {
    if (!title.trim()) return;
    onSubmit({
      title: title.trim(),
      category: category.trim() || '내가 추가',
      description: description.trim(),
      days_from_today: Math.max(0, parseInt(days, 10) || 0),
    });
    reset();
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.modalBackdrop}
      >
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
        <ScrollView
          contentContainerStyle={styles.modalCard}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>항목 추가</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.textMute} />
            </Pressable>
          </View>

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

          <Text style={styles.modalLabel}>며칠 뒤에 할 일인가요? (오늘=0)</Text>
          <TextInput
            value={days}
            onChangeText={(v) => setDays(v.replace(/[^0-9]/g, ''))}
            placeholder="0"
            placeholderTextColor={colors.textMute}
            keyboardType="number-pad"
            style={styles.modalInput}
          />

          <Pressable
            style={[styles.submitBtn, !title.trim() && { opacity: 0.5 }]}
            onPress={submit}
            disabled={!title.trim()}
          >
            <Text style={styles.submitText}>추가</Text>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
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
  loading: boolean;
  loadingMessage: string;
  error: string | null;
  submit: () => void;
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
    loading,
    loadingMessage,
    error,
    submit,
  } = props;

  const concernsByGroup = useMemo(() => {
    const map: Record<string, typeof CONCERN_OPTIONS> = {};
    for (const g of CONCERN_GROUPS) map[g] = [];
    for (const opt of CONCERN_OPTIONS) map[opt.group].push(opt);
    return map;
  }, []);

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
      <Text style={styles.h1}>이사 체크리스트</Text>
      <Text style={styles.h1Sub}>
        {editing
          ? '조건을 바꾼 뒤 아래 버튼을 눌러 재생성하세요'
          : '조건을 입력하면 AI가 체크리스트를 만들어줍니다'}
      </Text>

      <Section label="세대 유형">
        <SegmentGroup
          options={HOUSEHOLDS}
          value={household}
          onChange={setHousehold}
        />
      </Section>

      <Section label="계약 유형 (중복 선택 가능)">
        <View style={styles.multiRow}>
          {CONTRACTS.map((c) => {
            const active = contracts.includes(c);
            return (
              <Pressable
                key={c}
                onPress={() => toggleContract(c)}
                style={[
                  styles.multiBtn,
                  active && styles.multiBtnActive,
                ]}
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

      <Section label="이사 예정일">
        <Pressable style={styles.selector} onPress={openDatePicker}>
          <Ionicons name="calendar-outline" size={18} color={colors.primary} />
          <Text style={styles.selectorText}>{formatDateLabel(moveDate)}</Text>
          <Ionicons name="chevron-forward" size={18} color={colors.textMute} />
        </Pressable>
      </Section>

      <Section label="추가 조건">
        <View style={styles.toggles}>
          <ToggleChip
            icon="paw"
            label="반려동물"
            active={hasPet}
            onPress={() => setHasPet(!hasPet)}
          />
          <ToggleChip
            icon="car"
            label="자동차"
            active={hasCar}
            onPress={() => setHasCar(!hasCar)}
          />
          <ToggleChip
            icon="happy"
            label="자녀"
            active={hasChildren}
            onPress={() => setHasChildren(!hasChildren)}
          />
          <ToggleChip
            icon="globe"
            label="외국인"
            active={isForeigner}
            onPress={() => setIsForeigner(!isForeigner)}
          />
          <ToggleChip
            icon="business"
            label="아파트·오피스텔"
            active={isApartment}
            onPress={() => setIsApartment(!isApartment)}
          />
        </View>
      </Section>

      {hasChildren && (
        <Section label="자녀 학교급">
          <SegmentGroup
            options={SCHOOL_LEVELS}
            value={schoolLevel ?? '초등'}
            onChange={(v: SchoolLevel) => setSchoolLevel(v)}
          />
        </Section>
      )}

      <Section label="선택 항목 (해당자만)">
        <View style={styles.toggles}>
          <ToggleChip
            icon="briefcase"
            label="직장인"
            active={isEmployed}
            onPress={() => setIsEmployed(!isEmployed)}
          />
          <ToggleChip
            icon="heart"
            label="복지급여 수급자"
            active={receivesWelfare}
            onPress={() => setReceivesWelfare(!receivesWelfare)}
          />
          <ToggleChip
            icon="card"
            label="신분증 재발급 필요"
            active={needsIdReissue}
            onPress={() => setNeedsIdReissue(!needsIdReissue)}
          />
        </View>
      </Section>

      <Section label={`특이 상황${concernLabels.length > 0 ? ` · ${concernLabels.length}개 선택됨` : ''}`}>
        <View style={styles.concernGroups}>
          {CONCERN_GROUPS.map((group) => (
            <View key={group} style={styles.concernGroup}>
              <Text style={styles.concernGroupLabel}>{group}</Text>
              <View style={styles.toggles}>
                {concernsByGroup[group].map((opt) => {
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
            </View>
          ))}
        </View>
      </Section>

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

      {result.items.map((it, idx) => (
        <ChecklistCard
          key={`${it.category}-${idx}`}
          item={it}
          index={idx}
          done={!!completions[itemKey(it)]}
          onToggle={() => onToggle(it)}
          onPress={() => onItemPress(it, idx)}
        />
      ))}

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
  const dDay = computeDDayLabel(item.start_date);
  return (
    <View
      style={[
        styles.itemCard,
        { borderLeftColor: legal ? colors.warning : colors.primaryLight },
        done && { opacity: 0.5 },
      ]}
    >
      <Pressable onPress={onToggle} hitSlop={8} style={styles.checkbox}>
        <Ionicons
          name={done ? 'checkmark-circle' : 'ellipse-outline'}
          size={24}
          color={done ? colors.success : colors.textMute}
        />
      </Pressable>
      <Pressable style={{ flex: 1 }} onPress={onPress}>
        <View style={styles.itemHeader}>
          {dDay ? (
            <View
              style={[
                styles.dDayBadge,
                { backgroundColor: legal ? colors.warning : colors.primaryLight },
              ]}
            >
              <Text style={styles.dDayText}>{dDay}</Text>
            </View>
          ) : null}
          <Text
            style={[styles.itemTitle, done && styles.strike]}
          >
            {item.title}
          </Text>
        </View>
        {item.start_date ? (
          <Text style={styles.itemSubDate}>{item.start_date}</Text>
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
      </Pressable>
      {onRemove ? (
        <Pressable onPress={onRemove} hitSlop={8} style={styles.removeBtn}>
          <Ionicons name="trash-outline" size={18} color={colors.danger} />
        </Pressable>
      ) : (
        <Ionicons name="chevron-forward" size={18} color={colors.textMute} />
      )}
    </View>
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
    ...typography.captionBold,
    color: colors.text,
    marginBottom: spacing.sm,
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
  multiRow: { flexDirection: 'row', gap: spacing.xs },
  multiBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
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
  itemSubDate: {
    fontSize: 11,
    color: colors.textMute,
    fontWeight: '600',
    marginBottom: 6,
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
    fontSize: 11,
    color: colors.primary,
    fontWeight: '700',
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 3,
  },
  metaText: {
    fontSize: 11,
    flex: 1,
    fontWeight: '600',
    color: colors.textSub,
  },
  metaContact: {
    fontSize: 11,
    flex: 1,
    fontWeight: '700',
    color: colors.success,
  },
});
