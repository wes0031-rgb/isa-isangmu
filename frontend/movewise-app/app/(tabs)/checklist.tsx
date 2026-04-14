/**
 * Checklist tab — form + saved result with checkbox completion tracking.
 */
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { DatePickerModal } from '../../components/DatePickerModal';
import { RegionPickerModal } from '../../components/RegionPickerModal';
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
  clearChecklist,
  loadChecklist,
  loadCompletions,
  saveChecklist,
  toggleCompletion,
} from '../../lib/storage';
import { colors, radius, spacing, typography } from '../../theme/colors';

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
  const [concernLabels, setConcernLabels] = useState<string[]>([]);

  // Modals
  const [datePickerOpen, setDatePickerOpen] = useState(false);
  const [regionPickerOpen, setRegionPickerOpen] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ChecklistResponse | null>(null);
  const [completions, setCompletions] = useState<CompletionMap>({});

  // 탭 포커스마다 저장된 체크리스트 복원
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
          setConcernLabels(req.special_concerns ?? []);
          setMode('result');
          const comp = await loadCompletions();
          setCompletions(comp);
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
      special_concerns: concernLabels,
    };
    try {
      const res = await api.checklist(payload);
      setResult(res);
      await saveChecklist(payload, res);
      setCompletions({});
      setMode('result');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleToggle(item: ChecklistItem) {
    const map = await toggleCompletion(itemKey(item));
    setCompletions({ ...map });
  }

  async function handleShare() {
    if (!result) return;
    const lines = [
      `[MoveWise 이사 체크리스트]`,
      `이사일: ${moveDate} · ${region} · ${household} · ${contracts.join('/')}`,
      '',
      ...result.items.map((it, idx) => {
        const done = completions[itemKey(it)] ? '[✔]' : '[ ]';
        const dl = it.deadline_date ? ` ⚠ 마감 ${it.deadline_date}` : '';
        return `${done} ${idx + 1}. ${it.title} (D${it.d_day_offset >= 0 ? '+' : ''}${it.d_day_offset})${dl}`;
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
      '저장된 체크리스트를 지우고 새로 만드시겠어요?',
    );
    if (!confirmed) return;
    await clearChecklist();
    setResult(null);
    setCompletions({});
    setMode('form');
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
              concernLabels={concernLabels}
              toggleConcern={toggleConcern}
              loading={loading}
              error={error}
              submit={submit}
            />
          ) : (
            result && (
              <ResultView
                result={result}
                completions={completions}
                progress={progress}
                completedCount={completedCount}
                onToggle={handleToggle}
                onShare={handleShare}
                onNew={handleNew}
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
    </SafeAreaView>
  );
}

// ===== Form sub-view =====

interface FormViewProps {
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
  concernLabels: string[];
  toggleConcern: (label: string) => void;
  loading: boolean;
  error: string | null;
  submit: () => void;
}

function FormView(props: FormViewProps) {
  const {
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
    concernLabels,
    toggleConcern,
    loading,
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
      <Text style={styles.h1}>이사 체크리스트</Text>
      <Text style={styles.h1Sub}>
        조건을 입력하면 AI가 체크리스트를 만들어줍니다
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
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.submitText}>체크리스트 생성</Text>
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
  completions,
  progress,
  completedCount,
  onToggle,
  onShare,
  onNew,
  onItemPress,
}: {
  result: ChecklistResponse;
  completions: CompletionMap;
  progress: number;
  completedCount: number;
  onToggle: (item: ChecklistItem) => void;
  onShare: () => void;
  onNew: () => void;
  onItemPress: (item: ChecklistItem, idx: number) => void;
}) {
  return (
    <>
      <View style={styles.resultHeaderRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.h1}>체크리스트</Text>
          <Text style={styles.h1Sub}>{result.total_items}개 항목</Text>
        </View>
        <Pressable onPress={onShare} style={styles.iconBtn}>
          <Ionicons name="share-outline" size={22} color={colors.primary} />
        </Pressable>
        <Pressable onPress={onNew} style={styles.iconBtn}>
          <Ionicons name="add-circle-outline" size={22} color={colors.primary} />
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
    </>
  );
}

function ChecklistCard({
  item,
  index,
  done,
  onToggle,
  onPress,
}: {
  item: ChecklistItem;
  index: number;
  done: boolean;
  onToggle: () => void;
  onPress: () => void;
}) {
  const legal = item.has_legal_deadline;
  const dDay =
    item.d_day_offset >= 0
      ? `D+${item.d_day_offset}`
      : `D${item.d_day_offset}`;
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
          <View
            style={[
              styles.dDayBadge,
              { backgroundColor: legal ? colors.warning : colors.primaryLight },
            ]}
          >
            <Text style={styles.dDayText}>{dDay}</Text>
          </View>
          <Text style={[styles.itemTitle, done && styles.strike]}>
            {item.title}
          </Text>
        </View>
        <Text style={styles.itemSubDate}>{item.start_date}</Text>
        {item.deadline_date && (
          <View style={styles.deadlineBox}>
            <Ionicons name="alarm" size={14} color={colors.warning} />
            <Text style={styles.deadlineText}>
              마감 {item.deadline_date} ({item.deadline_days}일 기한)
            </Text>
          </View>
        )}
        {item.region_hint && (
          <View style={styles.metaRow}>
            <Ionicons name="location" size={12} color={colors.primary} />
            <Text style={styles.metaText} numberOfLines={1}>
              {item.region_hint}
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
      <Ionicons name="chevron-forward" size={18} color={colors.textMute} />
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
  },
  submitText: { color: '#fff', fontSize: 17, fontWeight: '800' },
  errorBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: '#FEE',
    padding: spacing.md,
    borderRadius: radius.md,
    marginTop: spacing.md,
  },
  errorText: { color: colors.danger, fontSize: 13, fontWeight: '600', flex: 1 },
  warningBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: '#FFF4E6',
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
  },
  checkbox: { paddingTop: 2 },
  itemHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.xs,
  },
  dDayBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.pill,
  },
  dDayText: { color: '#fff', fontSize: 12, fontWeight: '800' },
  itemTitle: { ...typography.bodyBold, flex: 1 },
  strike: { textDecorationLine: 'line-through' },
  itemSubDate: { ...typography.caption, marginBottom: spacing.xs },
  deadlineBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: spacing.xs,
  },
  deadlineText: { color: colors.warning, fontSize: 13, fontWeight: '700' },
  citationShortRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: spacing.xs,
  },
  citationShort: {
    ...typography.caption,
    flex: 1,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 3,
  },
  metaText: {
    ...typography.caption,
    flex: 1,
    fontWeight: '600',
    color: colors.primary,
  },
  metaContact: {
    ...typography.caption,
    flex: 1,
    fontWeight: '700',
    color: colors.success,
  },
});
