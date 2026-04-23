/**
 * 계약 전 체크 (SafeContract) — 등기부등본 해석기.
 * 기획서 3.5 참조: 텍스트/PDF 2가지 입력, 아코디언 결과, 체크리스트 연결.
 */
import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';

import { AppPressable } from '../../components/AppPressable';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  api,
  RiskItem,
  SafeContractResponse,
} from '../../lib/api';
import { Text } from '../../lib/AppText';
import { REGISTRY_SAMPLES, RegistrySample } from '../../lib/sampleRegistry';
import { loadChecklist, savePendingRegion } from '../../lib/storage';
import { useRotatingText } from '../../lib/useRotatingText';
import { colors, radius, spacing, typography } from '../../theme/colors';

const SAFECONTRACT_LOADING_STEPS = [
  '📄 문서 파싱 중...',
  '⚖️ 법령 대조 중...',
  '🔍 위험 요소 추출 중...',
] as const;

type InputMode = 'text' | 'pdf';

interface PickedFile {
  uri: string;
  name: string;
  mimeType?: string;
  size?: number;
}

/** 1,234,567 형식으로 포맷팅 */
/** 주소 문자열에서 '시/도 + 시/군/구' 추출 — backend 의 _parse_region_from_address 와 동기화.
 *  Render(옛 코드)가 inferred_region 응답 안 할 때 frontend fallback. */
function parseRegionFromAddress(address?: string | null): string | null {
  if (!address) return null;
  const text = address.replace(/\s+/g, ' ').trim();
  const re =
    /(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|경기도|강원특별자치도|강원도|충청북도|충청남도|전북특별자치도|전라북도|전라남도|경상북도|경상남도|제주특별자치도)\s+([가-힣]+시\s+[가-힣]+구|[가-힣]+구|[가-힣]+시|[가-힣]+군)/;
  const m = text.match(re);
  return m ? `${m[1]} ${m[2]}` : null;
}

function formatNumber(value: string): string {
  const digits = value.replace(/\D/g, '');
  if (!digits) return '';
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** 1억, 3억4천만원 처럼 한국식 단위 표시 */
function formatKoreanAmount(value: string): string {
  const n = parseInt(value.replace(/\D/g, ''), 10);
  if (!n || isNaN(n)) return '';
  const eok = Math.floor(n / 100_000_000);
  const man = Math.floor((n % 100_000_000) / 10_000);
  const parts = [];
  if (eok > 0) parts.push(`${eok}억`);
  if (man > 0) parts.push(`${man.toLocaleString()}만`);
  return parts.length ? `${parts.join(' ')}원` : `${n.toLocaleString()}원`;
}

export default function SafeContractScreen() {
  const router = useRouter();
  const [mode, setMode] = useState<InputMode>('pdf');
  const [text, setText] = useState('');
  const [pickedFile, setPickedFile] = useState<PickedFile | null>(null);
  const [deposit, setDeposit] = useState('100000000');
  const [market, setMarket] = useState('0');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SafeContractResponse | null>(null);
  const [isSelfOwnedUser, setIsSelfOwnedUser] = useState(false);
  const loadingMessage = useRotatingText(SAFECONTRACT_LOADING_STEPS, loading, 2500);

  // form ↔ result 가 같은 ScrollView 를 공유 → form 에서 스크롤한 위치가 result 진입
  // 시 그대로 남아 헤드라인이 화면 위로 잘려 보이는 버그 방지. result 토글마다 최상단 복귀.
  const scrollRef = useRef<ScrollView>(null);
  useEffect(() => {
    scrollRef.current?.scrollTo({ y: 0, animated: false });
  }, [result]);

  // 이미 자가로 저장된 체크리스트가 있으면 안내 배너 표시
  useFocusEffect(
    useCallback(() => {
      (async () => {
        const saved = await loadChecklist();
        const contracts = saved?.request.contracts ?? [];
        const hasSelf =
          contracts.includes('자가') || saved?.request.contract === '자가';
        setIsSelfOwnedUser(hasSelf);
      })();
    }, []),
  );

  async function submit() {
    setError(null);
    const depositN = parseInt(deposit.replace(/\D/g, ''), 10) || 0;
    const marketN = parseInt(market.replace(/\D/g, ''), 10) || 0;

    if (mode === 'text') {
      if (!text.trim()) {
        setError('등기부등본 텍스트를 입력하세요');
        return;
      }
      setLoading(true);
      setResult(null);
      try {
        const res = await api.safecontract({
          text,
          deposit_krw: depositN,
          expected_market_price_krw: marketN,
          region: undefined,
        });
        // 시세 미입력 상태로 분석했는데 백엔드가 국토부 API 로 자동 조회해줬으면
        // 입력창에 중위값 채워서 유저가 "어떤 시세로 계산됐는지" 확인 가능
        if (marketN <= 0 && res.market_estimate?.median_price_krw) {
          setMarket(String(res.market_estimate.median_price_krw));
        }
        setResult(res);
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    } else if (mode === 'pdf') {
      if (!pickedFile) {
        setError('PDF 파일을 먼저 선택하세요');
        return;
      }
      setLoading(true);
      setResult(null);
      try {
        // 시세 미입력 시 백엔드가 PDF 주소 → 국토부 실거래가 API 자동 조회
        const res = await api.safecontractUpload({
          uri: pickedFile.uri,
          name: pickedFile.name,
          mimeType: pickedFile.mimeType,
          deposit_krw: depositN,
          expected_market_price_krw: marketN,
          region: undefined,
        });
        if (marketN <= 0 && res.market_estimate?.median_price_krw) {
          setMarket(String(res.market_estimate.median_price_krw));
        }
        setResult(res);
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    }
  }

  async function pickPdf() {
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: 'application/pdf',
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (res.canceled) return;
      const asset = res.assets[0];
      if (asset.size && asset.size > 20 * 1024 * 1024) {
        setError('파일 크기는 20MB 이하여야 합니다');
        return;
      }
      setPickedFile({
        uri: asset.uri,
        name: asset.name,
        mimeType: asset.mimeType || 'application/pdf',
        size: asset.size,
      });
      setError(null);
    } catch (e: any) {
      setError(`파일 선택 실패: ${e.message}`);
    }
  }

  async function goToChecklist() {
    // 등기부 주소에서 자동 추출한 지역을 체크리스트 폼에 프리필.
    // 우선순위: backend inferred_region → frontend fallback (extraction.address 파싱)
    const ext = result?.extraction as { address?: string | null } | undefined;
    const region =
      result?.inferred_region || parseRegionFromAddress(ext?.address);
    if (region) {
      await savePendingRegion(region).catch(() => {});
    }
    router.push('/(tabs)/checklist');
  }

  function resetForm() {
    setResult(null);
    setText('');
    setPickedFile(null);
    setError(null);
  }

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView ref={scrollRef} contentContainerStyle={styles.container}>
          <Text style={styles.h1}>계약 전 체크</Text>
          <Text style={styles.h1Sub}>
            등기부등본을 쉬운 말로 해석해드립니다
          </Text>

          {isSelfOwnedUser && !result && (
            <View style={styles.selfOwnedBanner}>
              <Ionicons name="home" size={16} color={colors.primary} />
              <Text style={styles.selfOwnedBannerText}>
                본인 소유(자가) 체크리스트가 감지됐어요. 자가는 등기부 확인이 불필요합니다.
                월세·전세 계약 전에만 이용하세요.
              </Text>
            </View>
          )}

          {!result ? (
            <>
              {/* 입력 방식 선택 */}
              <Text style={styles.sectionLabel}>입력 방식</Text>
              <View style={styles.modeRow}>
                <ModeButton
                  icon="cloud-upload"
                  label="PDF"
                  badge="Azure"
                  active={mode === 'pdf'}
                  onPress={() => setMode('pdf')}
                />
                <ModeButton
                  icon="document-text"
                  label="텍스트"
                  badge="즉시"
                  active={mode === 'text'}
                  onPress={() => setMode('text')}
                />
              </View>

              {/* 인터넷등기소 안내 */}
              <View style={styles.helpBox}>
                <Ionicons name="information-circle" size={16} color={colors.primaryLight} />
                <Text style={styles.helpText}>
                  {mode === 'text' ? (
                    <>
                      <Text style={{ fontWeight: '700' }}>인터넷등기소</Text>
                      <Text> → 열람발급 → 본인이 받은 등기부등본에서{' '}</Text>
                      <Text style={{ fontWeight: '700' }}>표제부·갑구·을구 전체를 복사</Text>
                      <Text>해서 아래에 붙여넣으세요. 표제부 주소가 있어야 지역이 자동 인식돼요.</Text>
                    </>
                  ) : (
                    <>
                      <Text style={{ fontWeight: '700' }}>인터넷등기소</Text>
                      <Text>에서 다운받은 등기부등본 PDF 파일을 그대로 업로드하세요.{' '}</Text>
                      <Text style={{ fontWeight: '700' }}>Azure Document Intelligence</Text>
                      <Text>가 자동으로 갑구·을구를 읽어냅니다.</Text>
                    </>
                  )}
                </Text>
              </View>

              {/* 입력 영역 (모드별 분기) */}
              {mode === 'text' && (
                <>
                  <Text style={styles.sectionLabel}>등기부등본 본문</Text>
                  <TextInput
                    value={text}
                    onChangeText={setText}
                    placeholder="[표제부] 서울특별시 강남구 역삼동 123-45 전용면적 84.56㎡&#10;[갑구] 1. 2021-05-12 소유권이전 홍길동&#10;[을구] 1. 근저당권설정 채권최고액 금 2억4천만원 국민은행"
                    placeholderTextColor={colors.textMute}
                    multiline
                    style={styles.textarea}
                    textAlignVertical="top"
                  />

                  {/* 데모용 가상 샘플 로드 */}
                  <View style={styles.sampleRow}>
                    <Text style={styles.sampleLabel}>데모 샘플 (가상 데이터)</Text>
                    <View style={styles.sampleBtnRow}>
                      {REGISTRY_SAMPLES.map((s: RegistrySample) => (
                        <AppPressable
                          key={s.label}
                          style={styles.sampleBtn}
                          onPress={() => {
                            setText(s.text);
                            setDeposit(s.deposit);
                            setMarket(s.market);
                          }}
                        >
                          <Text style={styles.sampleBtnLabel}>{s.label}</Text>
                          <Text style={styles.sampleBtnDesc}>{s.description}</Text>
                        </AppPressable>
                      ))}
                    </View>
                  </View>
                </>
              )}
              {mode === 'pdf' && (
                <>
                  <Text style={styles.sectionLabel}>PDF 파일</Text>
                  <Pressable style={styles.pdfDropzone} onPress={pickPdf}>
                    <Ionicons
                      name={pickedFile ? 'document-attach' : 'cloud-upload-outline'}
                      size={36}
                      color={pickedFile ? colors.success : colors.primaryLight}
                    />
                    {pickedFile ? (
                      <>
                        <Text style={styles.pdfPickedName} numberOfLines={1}>
                          {pickedFile.name}
                        </Text>
                        <Text style={styles.pdfPickedSize}>
                          {pickedFile.size
                            ? `${(pickedFile.size / 1024).toFixed(0)} KB`
                            : ''}
                          {' · 다시 선택하려면 탭'}
                        </Text>
                      </>
                    ) : (
                      <>
                        <Text style={styles.pdfDropzoneTitle}>
                          PDF 파일 선택
                        </Text>
                        <Text style={styles.pdfDropzoneSub}>
                          최대 20MB, .pdf 만 지원
                        </Text>
                      </>
                    )}
                  </Pressable>
                </>
              )}
              {/* PDF 모드 안내 카드 */}
              {mode === 'pdf' && (
                <View style={styles.autoInfoCard}>
                  <Ionicons name="sparkles" size={16} color={colors.primary} />
                  <Text style={styles.autoInfoText}>
                    주소·면적·소유자·근저당·지역 등은 PDF 에서 자동 추출해요.{'\n'}
                    <Text style={{ fontWeight: '800' }}>보증금과 시세</Text>만 입력하시면 돼요.
                  </Text>
                </View>
              )}

              {/* 보증금·시세 */}
              <View style={styles.row}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.sectionLabel}>보증금</Text>
                  <TextInput
                    value={formatNumber(deposit)}
                    onChangeText={(v) => setDeposit(v.replace(/\D/g, ''))}
                    keyboardType="numeric"
                    style={styles.input}
                    placeholder="100,000,000"
                  />
                  <Text style={styles.amountHint}>
                    {formatKoreanAmount(deposit) || '금액 입력'}
                  </Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.sectionLabel}>시세 (선택)</Text>
                  <TextInput
                    value={formatNumber(market)}
                    onChangeText={(v) => setMarket(v.replace(/\D/g, ''))}
                    keyboardType="numeric"
                    style={styles.input}
                    placeholder="비워두면 자동 조회"
                  />
                  <Text style={styles.amountHint}>
                    {parseInt(market, 10) > 0
                      ? formatKoreanAmount(market)
                      : '미입력 시 주소로 국토부 실거래가 자동 조회'}
                  </Text>
                </View>
              </View>

              <Pressable
                style={[
                  styles.submitBtn,
                  (loading ||
                    (mode === 'text' && !text) ||
                    (mode === 'pdf' && !pickedFile)) && { opacity: 0.5 },
                ]}
                onPress={submit}
                disabled={
                  loading ||
                  (mode === 'text' && !text) ||
                  (mode === 'pdf' && !pickedFile)
                }
              >
                {loading ? (
                  <>
                    <ActivityIndicator color="#fff" />
                    <Text style={styles.submitText}>{loadingMessage}</Text>
                  </>
                ) : (
                  <>
                    <Ionicons name="shield-checkmark" size={18} color="#fff" />
                    <Text style={styles.submitText}>
                      {mode === 'pdf' ? 'PDF 분석하기' : '분석하기'}
                    </Text>
                  </>
                )}
              </Pressable>

              {!!error && (
                <View style={styles.errorBox}>
                  <Ionicons name="warning" size={16} color={colors.danger} />
                  <Text style={styles.errorText}>{error}</Text>
                </View>
              )}

              <View style={styles.disclaimerBox}>
                <Ionicons
                  name="alert-circle-outline"
                  size={14}
                  color={colors.textMute}
                />
                <Text style={styles.disclaimerBottom}>
                  본 서비스는 법률 자문이 아닌 참고용 사전 검토 도구입니다.
                  정확한 판단을 위해 전문가 상담을 권합니다.
                </Text>
              </View>
            </>
          ) : (
            <ResultView
              result={result}
              onReset={resetForm}
              onGoChecklist={goToChecklist}
            />
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ===== Mode Button =====

function ModeButton({
  icon,
  label,
  badge,
  active,
  disabled,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  badge: string;
  active: boolean;
  disabled?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={[
        styles.modeBtn,
        active && styles.modeBtnActive,
        disabled && styles.modeBtnDisabled,
      ]}
    >
      <Ionicons
        name={icon}
        size={22}
        color={active ? '#fff' : disabled ? colors.textMute : colors.primary}
      />
      <Text
        style={[
          styles.modeLabel,
          active && { color: '#fff' },
          disabled && { color: colors.textMute },
        ]}
      >
        {label}
      </Text>
      <View
        style={[
          styles.modeBadge,
          active && { backgroundColor: 'rgba(255,255,255,0.2)' },
          disabled && { backgroundColor: colors.borderLight },
        ]}
      >
        <Text
          style={[
            styles.modeBadgeText,
            active && { color: '#fff' },
            disabled && { color: colors.textMute },
          ]}
        >
          {badge}
        </Text>
      </View>
    </Pressable>
  );
}

// ===== Result View Helpers =====

type TopReason = { title: string; sub: string };
type ActionSeverity = 'red' | 'yellow' | 'green';
type ActionCheck = { icon: 'block' | 'warn' | 'check'; label: string; value: string; severity: ActionSeverity };

/**
 * 위험 요소를 가중치로 정렬 → 상위 3개를 hero 카드 "핵심 사유" 영역에 노출.
 * 가중치는 보증금 회수 곤란도 기준 (경매>신탁>가압류>가처분>비주거>근저당>전세가율>기타).
 */
function calcTopReasons(result: SafeContractResponse): TopReason[] {
  const ext = result.extraction as Record<string, unknown>;
  const list: { title: string; sub: string; weight: number }[] = [];
  const num = (k: string): number => (typeof ext[k] === 'number' ? (ext[k] as number) : 0);
  const bool = (k: string): boolean => !!ext[k];
  const str = (k: string): string => (typeof ext[k] === 'string' ? (ext[k] as string) : '');

  if (bool('auction_in_progress'))
    list.push({ title: '임의경매 진행 중', sub: '이미 법원 경매 절차 진입 — 보증금 회수 거의 불가', weight: 100 });
  if (bool('trust_registration'))
    list.push({ title: '신탁 등기', sub: '실소유권이 신탁회사 — 신탁사 동의 없으면 대항력 무효', weight: 95 });
  const sCnt = num('seizure_count');
  if (sCnt > 0)
    list.push({ title: `가압류 ${sCnt}건`, sub: str('seizure_text') || '집주인 채무 신호 — 경매 가능성', weight: 80 });
  if (bool('injunction_registered'))
    list.push({ title: '가처분 등기', sub: '소유권 분쟁 — 계약 후 변동 가능', weight: 75 });
  if (bool('non_residential_use'))
    list.push({ title: '비주거용 건물', sub: '전입신고 거절 가능 → 대항력 확보 어려움', weight: 70 });

  const mortRatio = result.mortgage_ratio ?? 0;
  if (mortRatio > 0) {
    const pct = Math.round(mortRatio * 100);
    const creditor = str('mortgage_creditor');
    list.push({
      title: `근저당 ${pct}%`,
      sub: creditor ? `시세 대비 선순위 · 채권자 ${creditor}` : '시세 대비 선순위 채권자',
      weight: 50 + Math.min(pct, 100) * 0.3,
    });
  }
  if (result.jeontse_ratio >= 0.8) {
    const pct = Math.round(result.jeontse_ratio * 100);
    list.push({ title: `전세가율 ${pct}%`, sub: '깡통전세 가능성 — 시세 하락 시 회수 어려움', weight: 60 });
  }
  if (bool('provisional_registration'))
    list.push({ title: '가등기 존재', sub: '본등기 시 소유권 이전 — 해제 여부 확인', weight: 40 });
  if (bool('jeonse_right_registered'))
    list.push({ title: '선순위 전세권', sub: '경매 시 배당 순위 뒤로 밀림', weight: 35 });
  const ownerChg = num('owner_change_within_2_years');
  if (ownerChg >= 2)
    list.push({ title: `소유권 이전 ${ownerChg}회`, sub: '갭투자·명의신탁 가능성 — 실소유권 확인', weight: 30 });
  const co = ext['co_owners'] as string[] | undefined;
  if (co && co.length > 0)
    list.push({ title: `공동명의 ${1 + co.length}인`, sub: '공유자 전원 동의·인감 필수', weight: 25 });

  list.sort((a, b) => b.weight - a.weight);
  return list.slice(0, 3).map(({ title, sub }) => ({ title, sub }));
}

/**
 * risk_level 별 큰 헤드라인·결론 단어. hero 카드 상단/중단 표기.
 * 옵션 2 (결론 단어) — "23/100" 같은 추상 점수 제거하고 명확한 결론 단어로.
 */
function buildHeadline(result: SafeContractResponse): {
  tag: string;
  headline: string;
} {
  // 판단·권유 문구 제거 — 사실 요약만 제공하고 판단은 사용자가 함.
  if (result.risk_level === 'red') {
    return {
      tag: '🔴 위험 요소 발견',
      headline: '아래 위험 항목을 확인하세요',
    };
  }
  if (result.risk_level === 'yellow') {
    return {
      tag: '🟡 주의 항목 발견',
      headline: '아래 주의 항목을 확인하세요',
    };
  }
  return {
    tag: '🟢 등기부 위험 요소 미발견',
    headline: '추출된 위험 항목이 없습니다',
  };
}

/**
 * "다음 액션" 체크 3개. risk_level + 위험 요소 조합으로 결정.
 * 옵션 3 — 추상 점수 대신 유저가 실제 뭘 못/해야 하는지 명시.
 */
function buildActionChecks(result: SafeContractResponse): ActionCheck[] {
  const ext = result.extraction as Record<string, unknown>;
  const bool = (k: string): boolean => !!ext[k];
  const num = (k: string): number => (typeof ext[k] === 'number' ? (ext[k] as number) : 0);
  const hardHazard =
    bool('auction_in_progress') ||
    bool('trust_registration') ||
    num('seizure_count') > 0 ||
    bool('injunction_registered') ||
    bool('non_residential_use');

  if (result.risk_level === 'red' || hardHazard) {
    return [
      { icon: 'block', label: 'HUG 보증보험 가입', value: '거절 가능성 높음', severity: 'red' },
      { icon: 'block', label: '전세대출 승인', value: '매우 어려움', severity: 'red' },
      { icon: 'warn', label: '전세피해지원센터 1533-8119', value: '강력 권장', severity: 'yellow' },
    ];
  }
  if (result.risk_level === 'yellow') {
    return [
      { icon: 'warn', label: 'HUG 보증보험 가입', value: '필수', severity: 'yellow' },
      { icon: 'warn', label: '전세대출 승인', value: '심사 까다로움', severity: 'yellow' },
      { icon: 'check', label: '대항력 (전입+확정일자)', value: '잔금일 즉시', severity: 'green' },
    ];
  }
  return [
    { icon: 'check', label: 'HUG 보증보험 가입', value: '권장', severity: 'green' },
    { icon: 'check', label: '대항력 (전입+확정일자)', value: '잔금일 즉시', severity: 'green' },
    { icon: 'check', label: '임대차 신고', value: '계약 후 30일 내', severity: 'green' },
  ];
}

// ===== Result View =====

function ResultView({
  result,
  onReset,
  onGoChecklist,
}: {
  result: SafeContractResponse;
  onReset: () => void;
  onGoChecklist: () => void;
}) {
  const jeontsePct = Math.min(Math.round(result.jeontse_ratio * 100), 999);
  const mortgagePct = Math.min(Math.round((result.mortgage_ratio ?? 0) * 100), 999);
  const color =
    result.risk_level === 'red'
      ? colors.danger
      : result.risk_level === 'yellow'
      ? colors.warning
      : colors.success;

  const ext = result.extraction as {
    property_id?: string | null;
    address?: string | null;
    area_m2?: number | null;
    building_use?: string | null;
    owner_name?: string | null;
    owner_registration_front?: string | null;
    co_owner_name?: string | null;
    co_owners?: string[];
    ownership_type?: string | null;
    mortgage_creditor?: string | null;
    mortgage_claim_amount_krw?: number | null;
    seizure_text?: string | null;
    seizure_count?: number;
    special_note?: string | null;
    auction_in_progress?: boolean;
    trust_registration?: boolean;
    injunction_registered?: boolean;
    provisional_registration?: boolean;
    jeonse_right_registered?: boolean;
    non_residential_use?: boolean;
    owner_change_within_2_years?: number;
  };
  const coOwnersList =
    ext.co_owners && ext.co_owners.length > 0
      ? ext.co_owners
      : ext.co_owner_name
      ? [ext.co_owner_name]
      : [];
  const hasPropertyInfo =
    !!ext.address || !!ext.owner_name || !!ext.area_m2 || !!ext.property_id;

  // ===== 새 디자인 헬퍼 (useMemo — result 안 바뀌면 재계산 안 함) =====
  const topReasons = useMemo(() => calcTopReasons(result), [result]);
  const headline = useMemo(() => buildHeadline(result), [result]);
  const actionChecks = useMemo(() => buildActionChecks(result), [result]);
  const heroBgStyle =
    result.risk_level === 'red'
      ? styles.heroBgRed
      : result.risk_level === 'yellow'
      ? styles.heroBgYellow
      : styles.heroBgGreen;
  const propOneLine = useMemo(
    () =>
      [ext.address, ext.area_m2 ? `${ext.area_m2}㎡` : null, ext.owner_name ? `${ext.owner_name}님` : null]
        .filter(Boolean)
        .join(' · '),
    [ext.address, ext.area_m2, ext.owner_name],
  );

  // 위험·주의 통합 (hard hazards + cautions) — useMemo 로 result 변경 시만 재계산
  const { hardHazards, cautions, riskCount } = useMemo(() => {
    const hh: { icon: keyof typeof Ionicons.glyphMap; title: string; sub: string }[] = [];
    if (ext.auction_in_progress)
      hh.push({ icon: 'hammer', title: '임의경매 진행 중', sub: '이미 경매 개시 — 보증금 회수 매우 어려움' });
    if (ext.trust_registration)
      hh.push({ icon: 'document-text', title: '신탁 등기', sub: '실소유권이 신탁회사 — 신탁사 동의 없으면 대항력 무효' });
    if ((ext.seizure_count ?? 0) > 0)
      hh.push({ icon: 'alert-circle', title: `가압류 ${ext.seizure_count}건`, sub: '집주인 채무 신호 — 경매 가능성' });
    // 임계값: 50%+ hard hazard, 30-49 caution, <30 미표시 (백엔드 risk_level 임계값과 일치)
    if (mortgagePct >= 50)
      hh.push({ icon: 'cash', title: `근저당 ${mortgagePct}% (시세 대비)`, sub: '선순위 채권자 — 경매 시 보증금보다 먼저 변제' });
    if (jeontsePct >= 80)
      hh.push({ icon: 'trending-up', title: `전세가율 ${jeontsePct}% (깡통전세 가능)`, sub: '시세 하락 시 보증금 회수 어려움' });

    const cs: { icon: keyof typeof Ionicons.glyphMap; title: string; sub: string }[] = [];
    if (mortgagePct >= 30 && mortgagePct < 50)
      cs.push({ icon: 'cash', title: `근저당 ${mortgagePct}% (시세 대비)`, sub: '선순위 채권 — 보증금 회수 순위 뒤로 밀림' });
    if (jeontsePct >= 70 && jeontsePct < 80)
      cs.push({ icon: 'trending-up', title: `전세가율 ${jeontsePct}%`, sub: '안전 범위(70% 미만) 초과 — HUG 보증보험 가입 검토' });
    if (coOwnersList.length > 0)
      cs.push({ icon: 'people', title: `공동명의 ${1 + coOwnersList.length}인`, sub: '공유자 전원 동의·인감 필수 (민법 265조)' });
    if (ext.provisional_registration)
      cs.push({ icon: 'lock-closed', title: '가등기 존재', sub: '본등기 시 소유권 이전 — 해제 여부 확인' });
    if (ext.jeonse_right_registered)
      cs.push({ icon: 'key', title: '선순위 전세권', sub: '경매 시 배당 순위 뒤로 밀림' });
    if ((ext.owner_change_within_2_years ?? 0) >= 2)
      cs.push({
        icon: 'swap-horizontal',
        title: `소유권 이전 ${ext.owner_change_within_2_years}회 (최근 2년)`,
        sub: '갭투자·명의신탁 가능성 — 실소유권 확인',
      });
    if (ext.building_use && /다세대|빌라|오피스텔|연립/.test(ext.building_use))
      cs.push({
        icon: 'home',
        title: `${ext.building_use} 시세 주의`,
        sub: '아파트 실거래가보다 낮음 — 직접 확인 권장',
      });
    return { hardHazards: hh, cautions: cs, riskCount: hh.length + cs.length };
  }, [result, ext, mortgagePct, coOwnersList]);

  // 스크린리더용 통합 라벨 (Hero 카드 한 번에 읽힘)
  const heroA11yLabel = `${headline.tag}. ${headline.headline}.${
    propOneLine ? ' ' + propOneLine + '.' : ''
  }`;

  return (
    <View style={styles.resultSection}>
      {/* ====== HERO: verdict 카드 (결론 먼저) ====== */}
      <View
        style={[styles.verdictHero, heroBgStyle]}
        accessible
        accessibilityRole="summary"
        accessibilityLabel={heroA11yLabel}
      >
        <View style={styles.verdictTagRow}>
          <Text style={[styles.verdictTag, { color }]}>{headline.tag}</Text>
        </View>
        <Text style={styles.verdictHeadline}>{headline.headline}</Text>
        {!!propOneLine && <Text style={styles.verdictProp}>{propOneLine}</Text>}

        {/* AI 한 줄 요약 — 백엔드 _explain_with_llm summary */}
        {!!result.summary && (
          <Text style={styles.verdictSummary}>{result.summary}</Text>
        )}

        {/* 핵심 사유 Top 3 */}
        {topReasons.length > 0 && (
          <View style={styles.reasonsBox}>
            <Text style={styles.reasonsTitle}>🔍 핵심 사유 (Top {topReasons.length})</Text>
            {topReasons.map((r, i) => (
              <View key={i} style={styles.reasonLine}>
                <Text style={[styles.reasonDot, { color }]}>•</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.reasonTitleText}>{r.title}</Text>
                  <Text style={styles.reasonSubText}>{r.sub}</Text>
                </View>
              </View>
            ))}
          </View>
        )}

        {/* 다음 액션 체크 */}
        <View style={styles.actionChecksBox}>
          <Text style={styles.actionChecksTitle}>📋 다음 액션</Text>
          {actionChecks.map((a, i) => {
            const sevColor =
              a.severity === 'red' ? colors.danger : a.severity === 'yellow' ? colors.warning : colors.success;
            const iconName: keyof typeof Ionicons.glyphMap =
              a.icon === 'block' ? 'close' : a.icon === 'warn' ? 'alert' : 'checkmark';
            return (
              <View key={i} style={styles.actionRow}>
                <View style={[styles.actionIcon, { backgroundColor: sevColor }]}>
                  <Ionicons name={iconName} size={13} color="#fff" />
                </View>
                <Text style={styles.actionLabel} numberOfLines={2}>
                  {a.label}
                </Text>
                <Text style={[styles.actionValue, { color: sevColor }]}>{a.value}</Text>
              </View>
            );
          })}
        </View>

        <Text style={styles.heroDisclaimer}>
          ⚠️ 참고용 분석이에요. 최종 판단 전 전세피해지원센터(1533-8119) 무료 상담을 권합니다.
        </Text>
      </View>

      {/* ====== 숫자로 한눈에 / 시세 미입력 안내 ====== */}
      {(result.jeontse_ratio > 0 || result.mortgage_ratio > 0) ? (
        <View style={styles.statsCard}>
          <Text style={styles.statsTitle}>📊 숫자로 한눈에</Text>
          <View style={styles.statsGrid}>
            <View style={styles.statBlock}>
              <Text style={styles.statLabel}>전세가율</Text>
              <Text
                style={[
                  styles.statValue,
                  {
                    color:
                      jeontsePct >= 80 ? colors.danger : jeontsePct >= 70 ? colors.warning : colors.success,
                  },
                ]}
              >
                {result.jeontse_ratio > 0 ? `${jeontsePct}%` : '—'}
              </Text>
              <Text style={styles.statSub}>
                {jeontsePct >= 80 ? '🔴 깡통전세 가능' : jeontsePct >= 70 ? '🟡 주의' : '🟢 안전'}
              </Text>
            </View>
            <View style={styles.statDivider} />
            <View style={styles.statBlock}>
              <Text style={styles.statLabel}>근저당비율</Text>
              <Text
                style={[
                  styles.statValue,
                  {
                    color:
                      mortgagePct >= 50 ? colors.danger : mortgagePct >= 30 ? colors.warning : colors.success,
                  },
                ]}
              >
                {result.mortgage_ratio > 0 ? `${mortgagePct}%` : '—'}
              </Text>
              <Text style={styles.statSub}>
                {mortgagePct >= 50 ? '🔴 위험' : mortgagePct >= 30 ? '🟡 주의' : '🟢 안전'}
              </Text>
            </View>
          </View>
          {result.market_estimate && (result.market_estimate.median_price_krw ?? 0) > 0 && (
            <Text style={styles.statExplain}>
              시세 {fmtKoreanAmount(result.market_estimate.median_price_krw ?? 0)} (자동 조회 ·{' '}
              {result.market_estimate.total_count}건 평균)
            </Text>
          )}
        </View>
      ) : (
        <View style={styles.marketMissingCard}>
          <Text style={styles.marketMissingTitle}>📊 시세 평가 제외</Text>
          <Text style={styles.marketMissingBody}>
            실거래가가 입력되지 않아 깡통전세 위험(전세가율·근저당비율)은 평가하지 못했어요.
            아래 등기부 위험만 분석한 결과입니다.
          </Text>
          {result.market_estimate?.error ? (
            <Text style={styles.marketMissingReason}>
              🔍 국토부 자동 조회: {result.market_estimate.error}
            </Text>
          ) : !result.market_estimate ? (
            <Text style={styles.marketMissingReason}>
              🔍 국토부 자동 조회: 주소가 인식되지 않아 자동 조회를 시도하지 못했습니다.
            </Text>
          ) : (
            <Text style={styles.marketMissingReason}>
              🔍 국토부 자동 조회: 해당 지역·기간 거래 내역이 없어 시세를 확인하지 못했습니다.
            </Text>
          )}
          <Text style={styles.marketMissingAction}>
            💡 네이버부동산·KB부동산 등에서 같은 단지·평형의 최근 시세를 확인해 위
            "예상 시세" 칸에 입력하고 다시 분석하면 깡통전세 위험까지 정확히 평가됩니다.
          </Text>
        </View>
      )}

      {/* ====== 위험·주의 통합 (펼침 default) ====== */}
      {riskCount > 0 ? (
        <Accordion
          icon="warning"
          iconBg={colors.dangerBg}
          iconColor={colors.danger}
          title="위험·주의"
          count={riskCount}
          countColor={colors.danger}
          defaultOpen
        >
          {hardHazards.map((h, i) => (
            <ReasonRow
              key={`h-${i}`}
              severity="red"
              icon={h.icon}
              title={h.title}
              sub={h.sub}
            />
          ))}
          {cautions.map((c, i) => (
            <ReasonRow
              key={`c-${i}`}
              severity="yellow"
              icon={c.icon}
              title={c.title}
              sub={c.sub}
            />
          ))}
        </Accordion>
      ) : (
        <View style={styles.noRiskCard}>
          <Image
            source={require('../../assets/duck-celebrate.png')}
            style={styles.noRiskDuck}
            resizeMode="contain"
          />
          <Text style={styles.noRiskTitle}>이상 무! 🎉</Text>
          <Text style={styles.noRiskDesc}>
            감지된 위험 요소가 없어요{'\n'}안전한 계약입니다
          </Text>
        </View>
      )}

      {/* ====== 등기부 추출 정보 (접힘 default) ====== */}
      {hasPropertyInfo && (
        <Accordion
          icon="document-text"
          title="등기부 추출 정보"
          defaultOpen={false}
        >
          {!!ext.address && <PropertyRow icon="location" label="주소" value={ext.address} />}
          {(!!ext.area_m2 || !!ext.building_use) && (
            <PropertyRow
              icon="resize"
              label="건물"
              value={[ext.building_use, ext.area_m2 ? `${ext.area_m2} m²` : null]
                .filter(Boolean)
                .join(' · ')}
            />
          )}
          {!!ext.owner_name && (
            <PropertyRow
              icon="person"
              label={coOwnersList.length > 0 ? `소유자 ${1 + coOwnersList.length}명` : '소유자'}
              value={`${ext.owner_name}${
                ext.owner_registration_front ? ` (${ext.owner_registration_front}-)` : ''
              }${coOwnersList.length > 0 ? `, ${coOwnersList.join(', ')}` : ''}${
                ext.ownership_type ? ` · ${ext.ownership_type}` : ''
              }`}
            />
          )}
          {(!!ext.mortgage_creditor || (ext.mortgage_claim_amount_krw ?? 0) > 0) && (
            <PropertyRow
              icon="cash"
              label="근저당"
              value={[
                ext.mortgage_claim_amount_krw ? fmtKoreanAmount(ext.mortgage_claim_amount_krw) : null,
                ext.mortgage_creditor,
              ]
                .filter(Boolean)
                .join(' · ')}
            />
          )}
          {!!ext.seizure_text && <PropertyRow icon="warning" label="가압류" value={ext.seizure_text} />}
          {!!ext.special_note && <PropertyRow icon="alert-circle" label="특이사항" value={ext.special_note} />}
          {!!ext.property_id && (
            <Text style={styles.propertyIdLine}>등기 고유번호: {ext.property_id}</Text>
          )}
        </Accordion>
      )}

      {/* ====== 법령 + 외부 도움 (접힘 default) ====== */}
      {(result.risks.length > 0 || result.referrals.length > 0) && (
        <Accordion
          icon="library"
          title="법령 근거 + 외부 도움"
          count={result.risks.length + result.referrals.length}
          defaultOpen={false}
        >
          {result.risks.length > 0 && (
            <>
              <Text style={styles.subsectionLabel}>⚖️ 위험 항목별 법령</Text>
              {result.risks.map((r, idx) => (
                <RiskAccordion key={idx} risk={r} />
              ))}
            </>
          )}
          {result.referrals.length > 0 && (
            <>
              <Text style={[styles.subsectionLabel, { marginTop: 12 }]}>🔗 외부 기관·도움</Text>
              {result.referrals.map((rf, idx) => (
                <Pressable
                  key={idx}
                  style={styles.referralCard}
                  onPress={() => Linking.openURL(rf.url)}
                >
                  <Text style={styles.referralIcon}>{rf.icon}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.referralName}>{rf.name}</Text>
                    <Text style={styles.referralDesc}>{rf.description}</Text>
                  </View>
                  <Ionicons name="open-outline" size={18} color={colors.textSub} />
                </Pressable>
              ))}
            </>
          )}
        </Accordion>
      )}

      {/* ====== 다음 액션 CTA ====== */}
      <AppPressable style={styles.nextBtn} onPress={onGoChecklist}>
        <View style={{ flex: 1 }}>
          <Text style={styles.nextBtnLabel}>
            {result.risk_level === 'red' ? '위험 인지 후에도 진행한다면' : '계약을 진행하기로 했다면'}
          </Text>
          <Text style={styles.nextBtnTitle}>이사 체크리스트 만들기 →</Text>
          {(() => {
            const ext2 = result.extraction as { address?: string | null };
            const hintRegion =
              result.inferred_region || parseRegionFromAddress(ext2.address);
            return hintRegion ? (
              <Text style={styles.nextBtnHint}>📍 {hintRegion} 지역으로 자동 설정</Text>
            ) : null;
          })()}
        </View>
        <Ionicons name="arrow-forward-circle" size={32} color="#fff" />
      </AppPressable>

      {/* 다시 분석 */}
      <AppPressable style={styles.resetBtn} onPress={onReset}>
        <Ionicons name="refresh" size={16} color={colors.primary} />
        <Text style={styles.resetText}>다른 등기부 분석하기</Text>
      </AppPressable>
    </View>
  );
}

// ===== 결과 화면 신규 컴포넌트 =====

function Accordion({
  icon,
  iconBg,
  iconColor,
  title,
  count,
  countColor,
  defaultOpen = false,
  children,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  iconBg?: string;
  iconColor?: string;
  title: string;
  count?: number;
  countColor?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <View style={styles.accordion}>
      <Pressable
        onPress={() => setOpen((o) => !o)}
        style={styles.accordionHead}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
      >
        <View style={[styles.accordionIcon, iconBg ? { backgroundColor: iconBg } : null]}>
          <Ionicons name={icon} size={14} color={iconColor || colors.primary} />
        </View>
        <Text style={styles.accordionTitle}>{title}</Text>
        {count != null && count > 0 && (
          <View style={[styles.accordionCount, countColor ? { backgroundColor: countColor } : null]}>
            <Text style={styles.accordionCountText}>{count}</Text>
          </View>
        )}
        <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={18} color={colors.textMute} />
      </Pressable>
      {open && <View style={styles.accordionBody}>{children}</View>}
    </View>
  );
}

function ReasonRow({
  severity,
  icon,
  title,
  sub,
}: {
  severity: 'red' | 'yellow' | 'green';
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  sub: string;
}) {
  const sevColor =
    severity === 'red' ? colors.danger : severity === 'yellow' ? colors.warning : colors.success;
  const sevBg =
    severity === 'red' ? colors.dangerBg : severity === 'yellow' ? colors.warningBg : colors.successBg;
  return (
    <View style={styles.reasonRow}>
      <View style={[styles.reasonRowIcon, { backgroundColor: sevBg }]}>
        <Ionicons name={icon} size={14} color={sevColor} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.reasonRowTitle}>{title}</Text>
        <Text style={styles.reasonRowSub}>{sub}</Text>
      </View>
    </View>
  );
}

function fmtKoreanAmount(krw: number): string {
  if (!krw) return '-';
  const eok = Math.floor(krw / 100_000_000);
  const man = Math.floor((krw % 100_000_000) / 10_000);
  if (eok > 0 && man > 0) return `${eok}억 ${man.toLocaleString()}만원`;
  if (eok > 0) return `${eok}억원`;
  return `${man.toLocaleString()}만원`;
}

function PropertyRow({
  icon,
  label,
  value,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
}) {
  return (
    <View style={styles.propertyRow}>
      <Ionicons name={icon} size={14} color={colors.primaryLight} />
      <Text style={styles.propertyRowLabel}>{label}</Text>
      <Text style={styles.propertyRowValue} numberOfLines={2}>
        {value}
      </Text>
    </View>
  );
}

function RiskAccordion({ risk }: { risk: RiskItem }) {
  const [expanded, setExpanded] = useState(risk.severity === 'red');
  const color =
    risk.severity === 'red'
      ? colors.danger
      : risk.severity === 'yellow'
      ? colors.warning
      : colors.success;

  return (
    <View style={[styles.riskCard, { borderLeftColor: color }]}>
      <Pressable
        onPress={() => setExpanded(!expanded)}
        style={styles.riskHeader}
      >
        <View style={[styles.severityDot, { backgroundColor: color }]} />
        <Text style={styles.riskLabel}>{risk.label}</Text>
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={18}
          color={colors.textMute}
        />
      </Pressable>
      {expanded && (
        <View style={styles.riskBody}>
          <Text style={styles.riskExplain}>{risk.explanation_plain}</Text>
          {risk.related_laws.length > 0 && (
            <View style={styles.riskLawBox}>
              {risk.related_laws.map((c, i) => (
                <View key={i} style={{ marginBottom: spacing.xs }}>
                  <View style={styles.riskLawTitleRow}>
                    <Ionicons
                      name="library"
                      size={12}
                      color={colors.primary}
                    />
                    <Text style={styles.riskLawTitle}>
                      {c.law_name} {c.article}
                      {c.article_title ? ` — ${c.article_title}` : ''}
                    </Text>
                  </View>
                  {!!c.article_text && (
                    <Text style={styles.riskLawText}>{c.article_text}</Text>
                  )}
                </View>
              ))}
            </View>
          )}
        </View>
      )}
    </View>
  );
}

// ===== Styles =====

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.lg, paddingBottom: spacing.xxl },
  h1: { ...typography.display },
  selfOwnedBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    padding: spacing.md,
    marginBottom: spacing.md,
    backgroundColor: colors.primary + '12',
    borderLeftWidth: 3,
    borderLeftColor: colors.primary,
    borderRadius: radius.sm,
  },
  selfOwnedBannerText: {
    flex: 1,
    fontSize: 12,
    color: colors.textSub,
    lineHeight: 18,
  },
  h1Sub: {
    ...typography.caption,
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  sectionLabel: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.sm,
    marginTop: spacing.md,
    letterSpacing: -0.2,
  },

  // Mode selector
  modeRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  modeBtn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.md - 2,
    borderRadius: radius.md,
    backgroundColor: colors.cardBg,
    borderWidth: 1,
    borderColor: colors.borderLight,
    gap: 4,
    minHeight: 90,
  },
  modeBtnActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  modeBtnDisabled: {
    opacity: 0.7,
    borderStyle: 'dashed',
  },
  modeLabel: {
    ...typography.captionBold,
    color: colors.text,
    marginTop: 2,
  },
  modeBadge: {
    backgroundColor: colors.primaryBg,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.pill,
    marginTop: 2,
  },
  modeBadgeText: {
    fontSize: 10,
    fontWeight: '800',
    color: colors.primary,
  },

  // Help
  helpBox: {
    flexDirection: 'row',
    gap: spacing.sm,
    alignItems: 'flex-start',
    backgroundColor: colors.primaryBg,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: spacing.sm,
  },
  helpText: {
    flex: 1,
    fontSize: 12,
    lineHeight: 18,
    color: colors.primary,
  },

  // Inputs
  textarea: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    fontSize: 14,
    lineHeight: 20,
    minHeight: 140,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  sampleRow: {
    marginTop: spacing.sm,
  },
  sampleLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.textMute,
    marginBottom: spacing.xs,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  sampleBtnRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  sampleBtn: {
    flex: 1,
    backgroundColor: colors.accentBg,
    borderWidth: 1,
    borderColor: colors.accent,
    borderRadius: radius.md,
    padding: spacing.sm + 2,
    alignItems: 'flex-start',
  },
  sampleBtnLabel: {
    fontSize: 13,
    fontWeight: '800',
    color: colors.primary,
    marginBottom: 2,
  },
  sampleBtnDesc: {
    fontSize: 11,
    color: colors.textSub,
    fontWeight: '500',
  },
  pdfDropzone: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.xl,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: colors.primaryBg,
    borderStyle: 'dashed',
    minHeight: 140,
    gap: spacing.xs,
  },
  pdfDropzoneTitle: {
    ...typography.subtitle,
    color: colors.primary,
    marginTop: spacing.xs,
  },
  pdfDropzoneSub: {
    ...typography.caption,
    color: colors.textMute,
  },
  pdfPickedName: {
    ...typography.bodyBold,
    color: colors.text,
    marginTop: spacing.xs,
    maxWidth: 240,
  },
  pdfPickedSize: {
    ...typography.caption,
    color: colors.textSub,
    marginTop: 2,
  },
  regionSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
    marginBottom: spacing.md,
  },
  regionText: {
    flex: 1,
    fontSize: 14,
    fontWeight: '600',
    color: colors.text,
  },
  autoInfoCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    backgroundColor: colors.primaryBg,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.primaryLight,
    marginBottom: spacing.md,
  },
  autoInfoText: {
    flex: 1,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '500',
    color: colors.primary,
  },
  input: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    fontSize: 15,
    fontWeight: '600',
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  amountHint: {
    ...typography.caption,
    color: colors.primaryLight,
    marginTop: 4,
    fontWeight: '600',
  },
  row: { flexDirection: 'row', gap: spacing.sm },

  // Submit
  submitBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    backgroundColor: colors.primary,
    paddingVertical: spacing.md + 2,
    borderRadius: radius.md,
    marginTop: spacing.lg,
  },
  submitText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '800',
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
  errorText: {
    color: colors.danger,
    fontSize: 13,
    fontWeight: '600',
    flex: 1,
  },
  disclaimerBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.xs,
    marginTop: spacing.xl,
    paddingHorizontal: spacing.md,
  },
  disclaimerBottom: {
    ...typography.caption,
    flex: 1,
    lineHeight: 18,
  },

  // Result
  resultSection: { marginTop: spacing.sm },
  propertyRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.xs,
    marginBottom: 4,
  },
  propertyRowLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.textSub,
    minWidth: 50,
  },
  propertyRowValue: {
    flex: 1,
    fontSize: 13,
    fontWeight: '600',
    color: colors.text,
    lineHeight: 18,
  },
  propertyIdLine: {
    fontSize: 10,
    color: colors.textMute,
    marginTop: spacing.xs,
    paddingTop: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  noRiskCard: {
    backgroundColor: colors.cardBg,
    padding: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.success,
    borderStyle: 'dashed',
    alignItems: 'center',
  },
  noRiskDuck: {
    width: 120,
    height: 140,
    marginBottom: spacing.sm,
  },
  noRiskTitle: {
    ...typography.subtitle,
    color: colors.success,
    marginBottom: spacing.xs,
  },
  noRiskDesc: {
    ...typography.caption,
    textAlign: 'center',
    lineHeight: 20,
  },

  // Risk accordion
  riskCard: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    marginBottom: spacing.sm,
    borderLeftWidth: 4,
    borderWidth: 1,
    borderColor: colors.borderLight,
    overflow: 'hidden',
  },
  riskHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md + 2,
  },
  severityDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  riskLabel: {
    ...typography.subtitle,
    fontSize: 15,
    flex: 1,
  },
  riskBody: {
    padding: spacing.md + 2,
    paddingTop: 0,
  },
  riskExplain: {
    ...typography.body,
    color: colors.textSub,
    marginBottom: spacing.sm,
  },
  riskLawBox: {
    backgroundColor: colors.bg,
    padding: spacing.sm + 2,
    borderRadius: radius.sm,
    marginTop: spacing.xs,
  },
  riskLawTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginBottom: 2,
  },
  riskLawTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
    flex: 1,
  },
  riskLawText: {
    fontSize: 12,
    lineHeight: 18,
    color: colors.textSub,
  },

  // Referral
  referralCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.cardBg,
    padding: spacing.md + 2,
    borderRadius: radius.md,
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  referralIcon: { fontSize: 26 },
  referralName: { ...typography.bodyBold },
  referralDesc: { ...typography.caption, marginTop: 2 },

  // Next CTA
  nextBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.primary,
    padding: spacing.lg,
    borderRadius: radius.lg,
    marginTop: spacing.lg,
  },
  nextBtnLabel: {
    color: colors.primaryMute,
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 2,
  },
  nextBtnTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '800',
  },
  nextBtnHint: {
    color: colors.primaryMute,
    fontSize: 11,
    fontWeight: '600',
    marginTop: 4,
  },

  // Reset
  resetBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.md,
    marginTop: spacing.sm,
  },
  resetText: {
    color: colors.primary,
    fontSize: 14,
    fontWeight: '700',
  },

  // ============ Hero verdict 카드 ============
  verdictHero: {
    borderRadius: 18,
    padding: spacing.lg - 4,
    marginBottom: spacing.md,
    borderWidth: 1,
  },
  heroBgRed: {
    backgroundColor: colors.dangerBg,
    borderColor: '#f3a7a1',
  },
  heroBgYellow: {
    backgroundColor: colors.warningBg,
    borderColor: '#f3c976',
  },
  heroBgGreen: {
    backgroundColor: colors.successBg,
    borderColor: '#82d39c',
  },
  verdictTagRow: {
    marginBottom: spacing.sm,
  },
  verdictTag: {
    alignSelf: 'flex-start',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.3,
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(255,255,255,0.75)',
    overflow: 'hidden',
  },
  verdictHeadline: {
    fontSize: 22,
    fontWeight: '800',
    color: colors.text,
    letterSpacing: -0.3,
    marginBottom: 4,
    lineHeight: 30,
  },
  verdictProp: {
    fontSize: 13,
    color: colors.textSub,
    marginBottom: spacing.md,
    lineHeight: 19,
  },
  verdictSummary: {
    fontSize: 14,
    color: colors.text,
    lineHeight: 22,
    marginTop: -spacing.sm + 2,
    marginBottom: spacing.md,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: radius.sm,
  },
  reasonsBox: {
    backgroundColor: 'rgba(255,255,255,0.7)',
    borderRadius: radius.md,
    padding: spacing.md - 2,
    marginVertical: spacing.sm,
  },
  reasonsTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.textSub,
    letterSpacing: 0.3,
    marginBottom: spacing.sm,
  },
  reasonLine: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingVertical: 5,
  },
  reasonDot: {
    fontSize: 16,
    fontWeight: '800',
    width: 10,
    lineHeight: 20,
  },
  reasonTitleText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.text,
    lineHeight: 20,
  },
  reasonSubText: {
    fontSize: 12,
    color: colors.textSub,
    lineHeight: 18,
    marginTop: 2,
  },
  actionChecksBox: {
    backgroundColor: 'rgba(255,255,255,0.7)',
    borderRadius: radius.md,
    padding: spacing.md - 2,
    marginVertical: spacing.sm,
  },
  actionChecksTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.textSub,
    letterSpacing: 0.3,
    marginBottom: 8,
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: 7,
  },
  actionIcon: {
    width: 24,
    height: 24,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionLabel: {
    flex: 1,
    fontSize: 13,
    color: colors.text,
    lineHeight: 18,
  },
  actionValue: {
    fontSize: 13,
    fontWeight: '800',
  },
  heroDisclaimer: {
    fontSize: 12,
    color: colors.textSub,
    lineHeight: 19,
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.08)',
  },

  // ============ 신규: 숫자 한눈에 카드 ============
  statsCard: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  statsTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.primary,
    marginBottom: spacing.sm,
  },
  statsGrid: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  statBlock: {
    flex: 1,
    paddingVertical: 4,
  },
  statLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.textSub,
    marginBottom: 6,
  },
  statValue: {
    fontSize: 26,
    fontWeight: '800',
    letterSpacing: -0.5,
    lineHeight: 30,
  },
  statSub: {
    fontSize: 12,
    color: colors.textMute,
    marginTop: 6,
    lineHeight: 17,
  },
  statDivider: {
    width: 1,
    backgroundColor: colors.border,
    marginHorizontal: spacing.md,
    alignSelf: 'stretch',
  },
  statExplain: {
    fontSize: 12,
    color: colors.textSub,
    marginTop: spacing.sm + 2,
    paddingTop: spacing.sm + 2,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
    lineHeight: 19,
  },
  marketMissingCard: {
    backgroundColor: colors.warningBg,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.warning,
  },
  marketMissingTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.warning,
    marginBottom: spacing.sm,
  },
  marketMissingBody: {
    fontSize: 13,
    color: colors.text,
    lineHeight: 20,
    marginBottom: spacing.sm,
  },
  marketMissingReason: {
    fontSize: 12,
    color: colors.textSub,
    lineHeight: 18,
    marginBottom: spacing.sm,
  },
  marketMissingAction: {
    fontSize: 13,
    color: colors.text,
    lineHeight: 20,
    fontWeight: '600',
  },

  // ============ 신규: Accordion ============
  accordion: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    marginBottom: spacing.sm + 2,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
  },
  accordionHead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm + 2,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 4,
  },
  accordionIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.primaryBg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  accordionTitle: {
    flex: 1,
    fontSize: 14,
    fontWeight: '700',
    color: colors.text,
  },
  accordionCount: {
    backgroundColor: colors.primary,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radius.pill,
    marginRight: 4,
  },
  accordionCountText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '700',
  },
  accordionBody: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
    paddingTop: spacing.sm,
  },

  // ============ 신규: ReasonRow (위험·주의 통합 리스트) ============
  reasonRow: {
    flexDirection: 'row',
    gap: spacing.sm + 2,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  reasonRowIcon: {
    width: 26,
    height: 26,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  reasonRowTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.text,
    lineHeight: 20,
  },
  reasonRowSub: {
    fontSize: 12,
    color: colors.textSub,
    marginTop: 3,
    lineHeight: 18,
  },

  // ============ 신규: Subsection label (아코디언 내부) ============
  subsectionLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.textSub,
    marginTop: spacing.xs,
    marginBottom: spacing.xs + 2,
  },
});
