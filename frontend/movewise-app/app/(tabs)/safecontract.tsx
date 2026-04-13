/**
 * 계약 전 체크 (SafeContract) — 등기부등본 해석기.
 * 기획서 3.5 참조: 텍스트/PDF/사진 3가지 입력, 아코디언 결과, 체크리스트 연결.
 */
import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { api, RiskItem, SafeContractResponse } from '../../lib/api';
import { alertAsync } from '../../lib/confirm';
import { colors, radius, spacing, typography } from '../../theme/colors';

type InputMode = 'text' | 'pdf' | 'photo';

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
  const [market, setMarket] = useState('300000000');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SafeContractResponse | null>(null);

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
        const res = await api.safecontractUpload({
          uri: pickedFile.uri,
          name: pickedFile.name,
          mimeType: pickedFile.mimeType,
          deposit_krw: depositN,
          expected_market_price_krw: marketN,
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

  function handlePhotoDisabled() {
    alertAsync(
      '사진 촬영 — 곧 출시',
      '카메라 연동은 현재 준비 중입니다. 우선 PDF 업로드 또는 텍스트 붙여넣기를 이용해주세요.',
    );
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
                  label="PDF 업로드"
                  badge="Azure"
                  active={mode === 'pdf'}
                  onPress={() => setMode('pdf')}
                />
                <ModeButton
                  icon="camera"
                  label="사진 촬영"
                  badge="준비 중"
                  active={false}
                  disabled
                  onPress={handlePhotoDisabled}
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
              {mode === 'text' ? (
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
                </>
              ) : (
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
                  <Text style={styles.sectionLabel}>예상 시세</Text>
                  <TextInput
                    value={formatNumber(market)}
                    onChangeText={(v) => setMarket(v.replace(/\D/g, ''))}
                    keyboardType="numeric"
                    style={styles.input}
                    placeholder="300,000,000"
                  />
                  <Text style={styles.amountHint}>
                    {formatKoreanAmount(market) || '금액 입력'}
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
                  <ActivityIndicator color="#fff" />
                ) : (
                  <>
                    <Ionicons name="shield-checkmark" size={18} color="#fff" />
                    <Text style={styles.submitText}>
                      {mode === 'pdf' ? 'PDF 분석하기' : '분석하기'}
                    </Text>
                  </>
                )}
              </Pressable>

              {error && (
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
  const pct = Math.round(result.jeontse_ratio * 100);
  const color =
    result.jeontse_ratio >= 1.0
      ? colors.danger
      : result.jeontse_ratio >= 0.8
      ? colors.warning
      : colors.success;

  return (
    <View style={styles.resultSection}>
      {/* 깡통전세 비율 Hero */}
      <View style={[styles.ratioCard, { borderColor: color }]}>
        <Text style={styles.ratioLabel}>깡통전세 비율</Text>
        <Text style={[styles.ratioValue, { color }]}>{pct}%</Text>
        <Text style={styles.ratioSummary}>{result.summary}</Text>
      </View>

      {/* 위험 항목 아코디언 */}
      <View style={styles.sectionHRow}>
        <Ionicons name="warning" size={18} color={colors.danger} />
        <Text style={styles.sectionH}>위험 항목</Text>
      </View>
      {result.risks.length === 0 ? (
        <View style={styles.emptyCard}>
          <Text style={{ color: colors.textSub, fontSize: 14 }}>
            감지된 위험 요소가 없습니다.
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
      <Pressable style={styles.nextBtn} onPress={onGoChecklist}>
        <View style={{ flex: 1 }}>
          <Text style={styles.nextBtnLabel}>계약을 진행하기로 했다면</Text>
          <Text style={styles.nextBtnTitle}>이사 체크리스트 만들기 →</Text>
        </View>
        <Ionicons name="arrow-forward-circle" size={32} color="#fff" />
      </Pressable>

      {/* 다시 분석 */}
      <Pressable style={styles.resetBtn} onPress={onReset}>
        <Ionicons name="refresh" size={16} color={colors.primary} />
        <Text style={styles.resetText}>다른 등기부 분석하기</Text>
      </Pressable>

      <Text style={styles.disclaimer}>{result.disclaimer}</Text>
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
                  {c.article_text && (
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
    backgroundColor: '#FEE',
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
  ratioCard: {
    backgroundColor: colors.cardBg,
    padding: spacing.lg + 4,
    borderRadius: radius.lg,
    alignItems: 'center',
    borderWidth: 2,
    marginBottom: spacing.lg,
  },
  ratioLabel: { ...typography.captionBold, color: colors.textSub },
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
    color: '#B8D4EC',
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
