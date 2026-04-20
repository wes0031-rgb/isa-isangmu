/**
 * 계약 전 체크 (SafeContract) — 등기부등본 해석기.
 * 기획서 3.5 참조: 텍스트/PDF 2가지 입력, 아코디언 결과, 체크리스트 연결.
 */
import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
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

import { RegionPickerModal } from '../../components/RegionPickerModal';
import {
  api,
  MarketEstimate,
  RiskItem,
  SafeContractResponse,
} from '../../lib/api';
import { Text } from '../../lib/AppText';
import { alertAsync } from '../../lib/confirm';
import { REGISTRY_SAMPLES, RegistrySample } from '../../lib/sampleRegistry';
import { loadChecklist } from '../../lib/storage';
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
  const [mode, setMode] = useState<InputMode>('text');
  const [text, setText] = useState('');
  const [pickedFile, setPickedFile] = useState<PickedFile | null>(null);
  const [deposit, setDeposit] = useState('100000000');
  const [market, setMarket] = useState('0');
  const [region, setRegion] = useState<string>('');
  const [regionPickerOpen, setRegionPickerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SafeContractResponse | null>(null);
  const loadingMessage = useRotatingText(SAFECONTRACT_LOADING_STEPS, loading, 2500);

  // 체크리스트에 저장된 region 을 기본값으로 자동 불러옴
  useFocusEffect(
    useCallback(() => {
      (async () => {
        if (region) return;
        const saved = await loadChecklist();
        if (saved?.request.region) {
          setRegion(saved.request.region);
        }
      })();
    }, [region]),
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
          region: region || undefined,
        });
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
        // PDF 모드는 region·market 전부 서버가 주소/실거래가로 자동 유도 → 빈 값으로 전달
        const res = await api.safecontractUpload({
          uri: pickedFile.uri,
          name: pickedFile.name,
          mimeType: pickedFile.mimeType,
          deposit_krw: depositN,
          expected_market_price_krw: 0,
          region: undefined,
        });
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

  function goToChecklist() {
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
        <ScrollView contentContainerStyle={styles.container}>
          <Text style={styles.h1}>계약 전 체크</Text>
          <Text style={styles.h1Sub}>
            등기부등본을 쉬운 말로 해석해드립니다
          </Text>

          {!result ? (
            <>
              {/* 입력 방식 선택 */}
              <Text style={styles.sectionLabel}>입력 방식</Text>
              <View style={styles.modeRow}>
                <ModeButton
                  icon="document-text"
                  label="텍스트"
                  badge="즉시"
                  active={mode === 'text'}
                  onPress={() => setMode('text')}
                />
                <ModeButton
                  icon="cloud-upload"
                  label="PDF"
                  badge="Azure"
                  active={mode === 'pdf'}
                  onPress={() => setMode('pdf')}
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
                      <Text style={{ fontWeight: '700' }}>갑구·을구 영역 전체를 복사</Text>
                      <Text>해서 아래에 붙여넣으세요.</Text>
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
                    placeholder="[갑구] 1. 2021-05-12 소유권이전 홍길동&#10;[을구] 1. 근저당권설정 채권최고액 금 2억4천만원 국민은행"
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
                            setRegion(s.region);
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
              {/* 지역 — 텍스트 모드일 때만 표시 (PDF 는 주소에서 자동 파싱) */}
              {mode === 'text' && (
                <>
                  <Text style={styles.sectionLabel}>지역 (자동 시세 조회)</Text>
                  <Pressable
                    style={styles.regionSelector}
                    onPress={() => setRegionPickerOpen(true)}
                  >
                    <Ionicons name="location-outline" size={18} color={colors.primary} />
                    <Text
                      style={[
                        styles.regionText,
                        !region && { color: colors.textMute },
                      ]}
                      numberOfLines={1}
                    >
                      {region || '지역을 선택하면 국토부 실거래가 자동 조회'}
                    </Text>
                    <Ionicons name="chevron-forward" size={16} color={colors.textMute} />
                  </Pressable>
                </>
              )}

              {/* PDF 모드는 자동 안내 카드 */}
              {mode === 'pdf' && (
                <View style={styles.autoInfoCard}>
                  <Ionicons name="sparkles" size={16} color={colors.primary} />
                  <Text style={styles.autoInfoText}>
                    주소·면적·소유자·시세 전부 PDF 에서 자동 추출해요.{'\n'}
                    <Text style={{ fontWeight: '800' }}>보증금만 입력</Text>하시면 돼요.
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
                {/* 텍스트 모드만 직접 시세 입력, PDF 는 자동 */}
                {mode === 'text' && (
                  <View style={{ flex: 1 }}>
                    <Text style={styles.sectionLabel}>시세 (모르면 비워두세요)</Text>
                    <TextInput
                      value={formatNumber(market)}
                      onChangeText={(v) => setMarket(v.replace(/\D/g, ''))}
                      keyboardType="numeric"
                      style={styles.input}
                      placeholder="자동 조회"
                    />
                    <Text style={styles.amountHint}>
                      {parseInt(market, 10) > 0
                        ? formatKoreanAmount(market)
                        : region
                        ? '📍 국토부 실거래가 자동 조회'
                        : '지역 선택하면 자동 조회'}
                    </Text>
                  </View>
                )}
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

      <RegionPickerModal
        visible={regionPickerOpen}
        value={region}
        onClose={() => setRegionPickerOpen(false)}
        onSelect={setRegion}
      />
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
    special_note?: string | null;
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

  return (
    <View style={styles.resultSection}>
      {/* 추출된 부동산 정보 카드 */}
      {hasPropertyInfo && (
        <View style={styles.propertyCard}>
          <View style={styles.propertyHeaderRow}>
            <Ionicons name="document-text" size={16} color={colors.primary} />
            <Text style={styles.propertyHeader}>AI 추출 정보</Text>
          </View>
          {!!ext.address && (
            <PropertyRow icon="location" label="주소" value={ext.address} />
          )}
          {(!!ext.area_m2 || !!ext.building_use) && (
            <PropertyRow
              icon="resize"
              label="건물"
              value={[
                ext.building_use,
                ext.area_m2 ? `${ext.area_m2} m²` : null,
              ]
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
          {(!!ext.mortgage_creditor || ext.mortgage_claim_amount_krw > 0) && (
            <PropertyRow
              icon="cash"
              label="근저당"
              value={[
                ext.mortgage_claim_amount_krw
                  ? fmtKoreanAmount(ext.mortgage_claim_amount_krw)
                  : null,
                ext.mortgage_creditor,
              ]
                .filter(Boolean)
                .join(' · ')}
            />
          )}
          {!!ext.seizure_text && (
            <PropertyRow
              icon="warning"
              label="가압류"
              value={ext.seizure_text}
            />
          )}
          {!!ext.special_note && (
            <PropertyRow
              icon="alert-circle"
              label="특이사항"
              value={ext.special_note}
            />
          )}
          {!!ext.property_id && (
            <Text style={styles.propertyIdLine}>
              등기 고유번호: {ext.property_id}
            </Text>
          )}
        </View>
      )}

      {/* 1. 전세가율 평가 — 수치 자체만 (다른 위험요소 섞지 않음) */}
      {(() => {
        const jVerdict =
          jeontsePct < 70
            ? { c: colors.success, t: '🟢 안전 범위' }
            : jeontsePct < 80
            ? { c: colors.warning, t: '🟡 주의' }
            : { c: colors.danger, t: '🔴 위험 (깡통전세 가능)' };
        return (
          <View style={[styles.ratioCard, { borderColor: jVerdict.c }]}>
            <Text style={styles.ratioLabel}>전세가율 평가</Text>
            <Text style={[styles.ratioValue, { color: jVerdict.c }]}>
              {jeontsePct}%
            </Text>
            {result.mortgage_ratio > 0 && (
              <Text style={styles.ratioSubLabel}>근저당비율 {mortgagePct}%</Text>
            )}
            <Text style={[styles.ratioSummary, { color: jVerdict.c }]}>
              {jVerdict.t}
            </Text>
            <Text style={styles.ratioExplainSmall}>
              시세 대비 보증금 비율만 본 평가예요. 아래 위험 요소와 종합 판정을 꼭 함께 확인하세요.
            </Text>
          </View>
        );
      })()}

      {/* 2. 위험 요소 — 신탁·경매·가압류·근저당 분리 표시 (있을 때만) */}
      {(() => {
        const ex = result.extraction as {
          auction_in_progress?: boolean;
          trust_registration?: boolean;
          seizure_count?: number;
        };
        const hasHazard =
          !!ex.auction_in_progress ||
          !!ex.trust_registration ||
          (ex.seizure_count ?? 0) > 0 ||
          (result.mortgage_ratio ?? 0) > 0;
        if (!hasHazard) return null;
        return (
          <View style={styles.hazardCard}>
            <View style={styles.hazardHeaderRow}>
              <Ionicons name="warning" size={16} color={colors.danger} />
              <Text style={styles.hazardHeader}>감지된 위험 요소</Text>
            </View>
            {ex.auction_in_progress && (
              <HazardLine
                icon="hammer"
                text="임의경매 진행 중"
                sub="이미 경매 개시 — 계약 시 보증금 회수 매우 어려움"
              />
            )}
            {ex.trust_registration && (
              <HazardLine
                icon="document-text"
                text="신탁 등기"
                sub="실소유권이 신탁회사에 있음 — 신탁사 동의 없으면 대항력 무효"
              />
            )}
            {(ex.seizure_count ?? 0) > 0 && (
              <HazardLine
                icon="alert-circle"
                text={`가압류 ${ex.seizure_count}건`}
                sub="집주인 채무 신호 — 경매 넘어갈 가능성"
              />
            )}
            {result.mortgage_ratio > 0 && (
              <HazardLine
                icon="cash"
                text={`근저당 ${mortgagePct}% (시세 대비)`}
                sub="선순위 채권자 존재 — 경매 시 보증금보다 먼저 변제됨"
              />
            )}
          </View>
        );
      })()}

      {/* 2.5 주의사항 (YELLOW 단계) — 확인·조치 필요 */}
      {(() => {
        const cautions: { icon: keyof typeof Ionicons.glyphMap; title: string; sub: string }[] = [];
        if (coOwnersList.length > 0) {
          const n = 1 + coOwnersList.length;
          cautions.push({
            icon: 'people',
            title: `공동명의 ${n}인`,
            sub: '공유자 전원의 동의서·인감증명서 필수 (민법 265조). 대리인 계약 시 위임장 반드시 확인.',
          });
        }
        if (ext.provisional_registration) {
          cautions.push({
            icon: 'document-lock',
            title: '가등기 존재',
            sub: '본등기 완료 시 소유권 이전 가능. 가등기 해제 여부 확인 권장.',
          });
        }
        if (ext.jeonse_right_registered) {
          cautions.push({
            icon: 'key',
            title: '선순위 전세권',
            sub: '이미 전세권자 존재. 경매 시 배당 순위 뒤로 밀릴 수 있음.',
          });
        }
        if ((ext.owner_change_within_2_years ?? 0) >= 2) {
          cautions.push({
            icon: 'swap-horizontal',
            title: `소유권 이전 ${ext.owner_change_within_2_years}회 (최근 2년)`,
            sub: '투자·명의신탁·갭투자 가능성. 집주인 실소유권·재정상태 확인 권장.',
          });
        }
        if (ext.building_use && /다세대|빌라|오피스텔|연립/.test(ext.building_use)) {
          cautions.push({
            icon: 'home',
            title: `${ext.building_use} 시세 주의`,
            sub: '아파트 실거래가보다 낮게 거래됨. 동일 지역 다세대 실거래 직접 확인 권장.',
          });
        }
        if (cautions.length === 0) return null;
        return (
          <View style={styles.cautionCard}>
            <View style={styles.cautionHeaderRow}>
              <Ionicons name="alert-circle" size={16} color={colors.warning} />
              <Text style={styles.cautionHeader}>주의사항 · 확인 권장</Text>
            </View>
            {cautions.map((c, i) => (
              <View key={i} style={styles.cautionLine}>
                <Ionicons name={c.icon} size={14} color={colors.warning} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.cautionLineText}>{c.title}</Text>
                  <Text style={styles.cautionLineSub}>{c.sub}</Text>
                </View>
              </View>
            ))}
            <Text style={styles.cautionFooter}>
              ※ 계약 자체를 피할 수준은 아니지만 추가 확인·조치로 안전을 확보하세요.
            </Text>
          </View>
        );
      })()}

      {/* 3. 종합 판정 — 전세가율 + 위험요소 통합 결론 */}
      <View style={[styles.verdictCard, { borderLeftColor: color }]}>
        <Text style={styles.verdictTitle}>종합 판정</Text>
        <Text style={[styles.verdictBig, { color }]}>
          {result.risk_level === 'red'
            ? '🔴 위험 — 계약 비권장'
            : result.risk_level === 'yellow'
            ? '🟡 주의 — HUG 보증보험 필수'
            : '🟢 안전 — 대항력 확보만 하세요'}
        </Text>
        <Text style={styles.verdictBody}>{result.summary}</Text>
      </View>

      {/* 전세가율 기준 안내 */}
      <View style={styles.thresholdCard}>
        <View style={styles.thresholdHeaderRow}>
          <Ionicons name="information-circle" size={14} color={colors.primaryLight} />
          <Text style={styles.thresholdHeader}>전세가율 기준</Text>
        </View>
        <ThresholdRow
          color={colors.success}
          range="~ 70%"
          label="🟢 안전"
          active={jeontsePct < 70}
        />
        <ThresholdRow
          color={colors.warning}
          range="70 ~ 80%"
          label="🟡 주의"
          active={jeontsePct >= 70 && jeontsePct < 80}
        />
        <ThresholdRow
          color={colors.danger}
          range="80% 이상"
          label="🔴 위험 (깡통전세 가능)"
          active={jeontsePct >= 80}
        />
        <Text style={styles.thresholdNote}>
          ※ 전세가율이 낮아도 경매·가압류·신탁 등기가 있으면 위험 매물이에요.
          근저당비율 50% 이상이거나 두 비율 합이 100% 넘으면 보증금 회수가 어려울 수 있어요.
        </Text>
      </View>

      {/* 실거래가 자동 조회 결과 */}
      {result.market_estimate && (
        <MarketEstimateCard estimate={result.market_estimate} />
      )}

      {/* 위험 항목 아코디언 */}
      <View style={styles.sectionHRow}>
        <Ionicons name="warning" size={18} color={colors.danger} />
        <Text style={styles.sectionH}>위험 항목</Text>
      </View>
      {result.risks.length === 0 ? (
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
      ) : (
        result.risks.map((r, idx) => <RiskAccordion key={idx} risk={r} />)
      )}

      {/* 다음에 확인하세요 */}
      <View style={styles.sectionHRow}>
        <Ionicons name="link" size={18} color={colors.primaryLight} />
        <Text style={styles.sectionH}>다음에 확인하세요</Text>
      </View>
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

      {/* 계약 진행 버튼 */}
      <AppPressable style={styles.nextBtn} onPress={onGoChecklist}>
        <View style={{ flex: 1 }}>
          <Text style={styles.nextBtnLabel}>계약을 진행하기로 했다면</Text>
          <Text style={styles.nextBtnTitle}>이사 체크리스트 만들기 →</Text>
        </View>
        <Ionicons name="arrow-forward-circle" size={32} color="#fff" />
      </AppPressable>

      {/* 다시 분석 */}
      <AppPressable style={styles.resetBtn} onPress={onReset}>
        <Ionicons name="refresh" size={16} color={colors.primary} />
        <Text style={styles.resetText}>다른 등기부 분석하기</Text>
      </AppPressable>

      <Text style={styles.disclaimer}>{result.disclaimer}</Text>
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

function HazardLine({
  icon,
  text,
  sub,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  text: string;
  sub: string;
}) {
  return (
    <View style={styles.hazardLine}>
      <Ionicons name={icon} size={14} color={colors.danger} />
      <View style={{ flex: 1 }}>
        <Text style={styles.hazardLineText}>{text}</Text>
        <Text style={styles.hazardLineSub}>{sub}</Text>
      </View>
    </View>
  );
}

function ThresholdRow({
  color,
  range,
  label,
  active,
}: {
  color: string;
  range: string;
  label: string;
  active: boolean;
}) {
  return (
    <View style={[styles.thresholdRow, active && { backgroundColor: color + '15' }]}>
      <View style={[styles.thresholdDot, { backgroundColor: color }]} />
      <Text style={[styles.thresholdRange, active && { fontWeight: '800' }]}>
        {range}
      </Text>
      <Text style={[styles.thresholdLabel, active && { fontWeight: '800', color }]}>
        {label}
      </Text>
      {active && <Text style={[styles.thresholdActive, { color }]}>현재</Text>}
    </View>
  );
}

function MarketEstimateCard({ estimate }: { estimate: MarketEstimate }) {
  if (estimate.error) {
    return (
      <View style={styles.marketCardError}>
        <Ionicons name="information-circle-outline" size={16} color={colors.warning} />
        <Text style={styles.marketErrorText}>{estimate.error}</Text>
      </View>
    );
  }
  if (!estimate.median_price_krw) return null;

  return (
    <View style={styles.marketCard}>
      <View style={styles.marketHeader}>
        <Ionicons name="trending-up" size={16} color={colors.primary} />
        <Text style={styles.marketHeaderText}>
          국토부 실거래가 자동 조회
        </Text>
        <Text style={styles.marketBadge}>{estimate.query_ym.slice(0, 4)}.{estimate.query_ym.slice(4)}</Text>
      </View>
      <Text style={styles.marketRegion}>{estimate.region}</Text>
      <View style={styles.marketStats}>
        <View style={styles.marketStatItem}>
          <Text style={styles.marketStatLabel}>중위가</Text>
          <Text style={styles.marketStatValue}>
            {fmtKoreanAmount(estimate.median_price_krw)}
          </Text>
        </View>
        <View style={styles.marketStatDivider} />
        <View style={styles.marketStatItem}>
          <Text style={styles.marketStatLabel}>범위</Text>
          <Text style={styles.marketStatRange}>
            {fmtKoreanAmount(estimate.min_price_krw || 0)} ~{' '}
            {fmtKoreanAmount(estimate.max_price_krw || 0)}
          </Text>
        </View>
      </View>
      <Text style={styles.marketTotalText}>
        이번 달 거래 {estimate.total_count}건 · 아파트 매매 기준
      </Text>
      <View style={styles.marketBadgeRow}>
        <Ionicons name="calculator" size={11} color={colors.success} />
        <Text style={styles.marketBadgeText}>
          이 값으로 전세가율 자동 계산됨
        </Text>
      </View>
      {estimate.recent_deals.length > 0 && (
        <View style={styles.marketDealsBox}>
          <Text style={styles.marketDealsTitle}>최근 거래 상위 {estimate.recent_deals.length}</Text>
          {estimate.recent_deals.slice(0, 5).map((d, i) => (
            <View key={i} style={styles.marketDealRow}>
              <Text style={styles.marketDealDate}>{d.deal_date.slice(5)}</Text>
              <Text style={styles.marketDealName} numberOfLines={1}>
                {d.apt_name}
              </Text>
              <Text style={styles.marketDealArea}>
                {d.area_m2.toFixed(0)}㎡ {d.floor}층
              </Text>
              <Text style={styles.marketDealPrice}>
                {fmtKoreanAmount(d.deal_amount_krw)}
              </Text>
            </View>
          ))}
        </View>
      )}
      <Text style={styles.marketSourceNote}>
        출처: 공공데이터포털 · 국토교통부 아파트 매매 실거래가 API
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
  h1Sub: {
    ...typography.caption,
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  sectionLabel: {
    ...typography.captionBold,
    color: colors.text,
    marginBottom: spacing.sm,
    marginTop: spacing.md,
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
  ratioExplainSmall: {
    ...typography.caption,
    fontSize: 11,
    color: colors.textMute,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 15,
  },
  hazardCard: {
    backgroundColor: colors.dangerBg,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.danger,
  },
  hazardHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: spacing.sm,
  },
  hazardHeader: {
    ...typography.captionBold,
    color: colors.danger,
    fontSize: 13,
  },
  hazardLine: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
    backgroundColor: colors.cardBg,
    borderRadius: radius.sm,
    marginBottom: 6,
  },
  hazardLineText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.danger,
    marginBottom: 2,
  },
  hazardLineSub: {
    fontSize: 11,
    color: colors.textSub,
    lineHeight: 15,
  },
  cautionCard: {
    backgroundColor: colors.warningBg,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.warning,
  },
  cautionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: spacing.sm,
  },
  cautionHeader: {
    ...typography.captionBold,
    color: colors.warning,
    fontSize: 13,
  },
  cautionLine: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
    backgroundColor: colors.cardBg,
    borderRadius: radius.sm,
    marginBottom: 6,
  },
  cautionLineText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.warning,
    marginBottom: 2,
  },
  cautionLineSub: {
    fontSize: 11,
    color: colors.textSub,
    lineHeight: 15,
  },
  cautionFooter: {
    ...typography.caption,
    fontSize: 11,
    lineHeight: 15,
    color: colors.textMute,
    marginTop: spacing.xs,
    paddingTop: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  verdictCard: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderLeftWidth: 4,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  verdictTitle: {
    ...typography.captionBold,
    fontSize: 12,
    color: colors.textSub,
    marginBottom: spacing.xs,
  },
  verdictBig: {
    fontSize: 18,
    fontWeight: '800',
    marginBottom: spacing.sm,
  },
  verdictBody: {
    ...typography.body,
    fontSize: 13,
    lineHeight: 19,
    color: colors.text,
  },
  thresholdCard: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  thresholdHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginBottom: spacing.sm,
  },
  thresholdHeader: {
    ...typography.captionBold,
    fontSize: 12,
    color: colors.textSub,
  },
  thresholdRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: 5,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.sm,
    marginBottom: 3,
  },
  thresholdDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  thresholdRange: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.textSub,
    minWidth: 75,
  },
  thresholdLabel: {
    flex: 1,
    fontSize: 12,
    fontWeight: '600',
    color: colors.text,
  },
  thresholdActive: {
    fontSize: 11,
    fontWeight: '800',
  },
  thresholdNote: {
    ...typography.caption,
    fontSize: 11,
    lineHeight: 16,
    color: colors.textMute,
    marginTop: spacing.xs,
    paddingTop: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
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
  marketBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: spacing.xs,
    paddingTop: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  marketBadgeText: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.success,
  },
  marketCard: {
    backgroundColor: colors.primaryBg,
    borderRadius: radius.md,
    padding: spacing.md + 2,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.primaryLight,
  },
  marketCardError: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.warningBg,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  marketErrorText: {
    ...typography.caption,
    color: colors.warning,
    flex: 1,
  },
  marketHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: spacing.xs,
  },
  marketHeaderText: {
    ...typography.captionBold,
    color: colors.primary,
    flex: 1,
  },
  marketBadge: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.primary,
    backgroundColor: 'rgba(0, 58, 117, 0.08)',
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.pill,
  },
  marketRegion: {
    ...typography.subtitle,
    fontSize: 15,
    marginBottom: spacing.sm,
  },
  marketStats: {
    flexDirection: 'row',
    backgroundColor: colors.cardBg,
    borderRadius: radius.sm,
    padding: spacing.sm + 2,
    marginBottom: spacing.sm,
  },
  marketStatItem: {
    flex: 1,
  },
  marketStatDivider: {
    width: 1,
    backgroundColor: colors.border,
    marginHorizontal: spacing.sm,
  },
  marketStatLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.textSub,
    marginBottom: 2,
  },
  marketStatValue: {
    fontSize: 18,
    fontWeight: '800',
    color: colors.primary,
    letterSpacing: -0.5,
  },
  marketStatRange: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.text,
  },
  marketTotalText: {
    ...typography.caption,
    marginBottom: spacing.sm,
  },
  marketDealsBox: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.sm,
    padding: spacing.sm + 2,
    marginTop: spacing.xs,
  },
  marketDealsTitle: {
    ...typography.captionBold,
    color: colors.primary,
    marginBottom: spacing.xs,
  },
  marketDealRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingVertical: 3,
  },
  marketDealDate: {
    fontSize: 11,
    color: colors.textSub,
    width: 38,
  },
  marketDealName: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.text,
    flex: 1,
  },
  marketDealArea: {
    fontSize: 10,
    color: colors.textMute,
    width: 50,
  },
  marketDealPrice: {
    fontSize: 11,
    fontWeight: '800',
    color: colors.primary,
    textAlign: 'right',
    minWidth: 60,
  },
  marketSourceNote: {
    fontSize: 10,
    color: colors.textMute,
    marginTop: spacing.xs,
    textAlign: 'right',
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
  propertyCard: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.primaryLight,
    borderLeftWidth: 4,
  },
  propertyHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: spacing.sm,
  },
  propertyHeader: {
    ...typography.captionBold,
    color: colors.primary,
    fontSize: 12,
  },
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
  ratioCard: {
    backgroundColor: colors.cardBg,
    padding: spacing.lg + 4,
    borderRadius: radius.lg,
    alignItems: 'center',
    borderWidth: 2,
    marginBottom: spacing.lg,
  },
  ratioLabel: { ...typography.captionBold, color: colors.textSub },
  ratioSubLabel: {
    ...typography.caption,
    color: colors.textSub,
    marginTop: spacing.xs,
  },
  ratioValue: {
    fontSize: 64,
    fontWeight: '900',
    marginVertical: spacing.xs,
    letterSpacing: -2,
  },
  ratioSummary: {
    ...typography.bodyBold,
    textAlign: 'center',
    marginTop: spacing.xs,
  },
  sectionHRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  sectionH: {
    ...typography.subtitle,
  },
  emptyCard: {
    backgroundColor: colors.cardBg,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
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

  disclaimer: {
    ...typography.caption,
    textAlign: 'center',
    marginTop: spacing.lg,
    color: colors.textMute,
    lineHeight: 18,
  },
});
