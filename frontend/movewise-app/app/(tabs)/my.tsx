/**
 * 마이 — 시스템 상태 + 서비스 정보 + 데이터 초기화.
 */
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { api } from '../../lib/api';
import { Text } from '../../lib/AppText';
import { alertAsync, confirmAsync } from '../../lib/confirm';
import {
  FontScaleLevel,
  SCALE_LABELS,
  useFontScaleLevel,
} from '../../lib/fontScale';
import { clearChecklist } from '../../lib/storage';
import { colors, radius, spacing, typography } from '../../theme/colors';

export default function MyScreen() {
  const [health, setHealth] = useState<
    { service: string; version: string; azure_ready: boolean } | null
  >(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [fontLevel, setFontLevel] = useFontScaleLevel();

  // 탭 진입 시 health 체크. AbortController 로 언마운트 시 진짜 취소해서
  // context-cancel 로 인한 false-positive "연결 실패" 방지. 3회 재시도까지 조용히
  // 넘기고 최종 실패 시에만 경고 톤으로 표시.
  useFocusEffect(
    useCallback(() => {
      const controller = new AbortController();
      let attempts = 0;
      async function check() {
        if (controller.signal.aborted) return;
        attempts += 1;
        try {
          const h = await api.health();
          if (controller.signal.aborted) return;
          setHealth(h);
          setHealthError(null);
        } catch (e: any) {
          if (controller.signal.aborted) return;
          if (e?.name === 'AbortError') return;
          if (attempts < 3) {
            setTimeout(check, 3000);
            return;
          }
          setHealthError('상태 확인 중...');
        }
      }
      check();
      return () => {
        controller.abort();
      };
    }, []),
  );

  async function handleClearData() {
    const confirmed = await confirmAsync(
      '데이터 초기화',
      '저장된 체크리스트와 완료 상태가 모두 삭제됩니다. 계속할까요?',
      '삭제',
    );
    if (!confirmed) return;
    await clearChecklist();
    alertAsync('완료', '저장 데이터가 초기화되었습니다.');
  }

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.h1}>마이</Text>
        <Text style={styles.h1Sub}>시스템 상태 · 서비스 정보</Text>

        {/* 글자 크기 설정 (접근성) */}
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>글자 크기</Text>
          <Text style={styles.label}>아이·노약자 분은 글자를 크게 설정하세요</Text>
          <View style={styles.scaleRow}>
            {(['normal', 'large', 'xlarge'] as FontScaleLevel[]).map((lv) => (
              <Pressable
                key={lv}
                style={[
                  styles.scaleBtn,
                  fontLevel === lv && styles.scaleBtnActive,
                ]}
                onPress={() => setFontLevel(lv)}
              >
                <Text
                  style={[
                    styles.scaleBtnText,
                    fontLevel === lv && styles.scaleBtnTextActive,
                    lv === 'large' && { fontSize: 15 },
                    lv === 'xlarge' && { fontSize: 17 },
                  ]}
                >
                  {SCALE_LABELS[lv]}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>

        {/* 시스템 상태 (읽기 전용) */}
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>시스템 상태</Text>
          <View style={styles.statusRow}>
            {healthError ? (
              <>
                <Ionicons
                  name="sync"
                  size={18}
                  color={colors.textSub}
                />
                <Text style={[styles.statusText, { color: colors.textSub }]}>
                  {healthError}
                </Text>
              </>
            ) : health ? (
              <>
                <Ionicons
                  name={health.azure_ready ? 'sparkles' : 'construct'}
                  size={18}
                  color={health.azure_ready ? colors.primary : colors.textSub}
                />
                <Text style={styles.statusText}>
                  {health.azure_ready
                    ? 'Azure LLM 모드 · 고도화된 RAG'
                    : 'Local fallback 모드 · 데이터 기반 자동 응답'}
                </Text>
              </>
            ) : (
              <Text style={styles.statusText}>확인 중...</Text>
            )}
          </View>
        </View>

        {/* 서비스 정보 */}
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>서비스 정보</Text>
          <InfoRow
            icon="information-circle"
            label="버전"
            value="v0.1.0"
          />
          <InfoRow
            icon="people"
            label="소속"
            value="MSAI09 2차 프로젝트"
          />
        </View>

        {/* 개인정보 처리 방침 */}
        <View style={styles.card}>
          <View style={styles.policyHeader}>
            <Ionicons name="shield-checkmark" size={18} color={colors.primary} />
            <Text style={styles.sectionTitle}>개인정보 처리 방침</Text>
          </View>
          <Text style={styles.policyBody}>
            본 서비스는 <Text style={{ fontWeight: '800' }}>비로그인</Text>으로 동작하며, 이름·연락처·주민번호 등 식별 정보를 수집하지 않습니다. 체크리스트 조건·등기부등본 본문·챗봇 질문은 <Text style={{ fontWeight: '800' }}>서버에 저장되지 않고 응답 생성 직후 즉시 파기</Text>됩니다. 저장되는 것은 사용자가 기기에 직접 저장한 체크리스트뿐이며, 이 데이터는 아래 "체크리스트 초기화" 버튼으로 언제든 삭제할 수 있습니다.
          </Text>
        </View>

        {/* 법적 면책 고지 */}
        <View style={styles.card}>
          <View style={styles.policyHeader}>
            <Ionicons name="document-text" size={18} color={colors.warning} />
            <Text style={styles.sectionTitle}>법적 면책 고지</Text>
          </View>
          <Text style={styles.policyBody}>
            본 서비스는 <Text style={{ fontWeight: '800' }}>이사 절차에 대한 참고용 사전 검토 도구</Text>이며, 변호사·법무사 등 전문가의 법률 자문이 아닙니다. AI 모델 특성상 검색 결과에 포함되지 않은 정보는 답변에 제공되지 않으며, 법 개정·최신 판례 미반영 등으로 오차가 있을 수 있습니다. 실제 계약·분쟁·행정 처리는 반드시 해당 기관(주민센터·법률구조공단 132·변호사) 에 확인하시기 바랍니다.
          </Text>
        </View>

        {/* 데이터 출처 */}
        <View style={styles.card}>
          <View style={styles.policyHeader}>
            <Ionicons name="library" size={18} color={colors.primary} />
            <Text style={styles.sectionTitle}>데이터 출처</Text>
          </View>
          <View style={styles.sourceRow}>
            <Text style={styles.sourceLabel}>법률 인용</Text>
            <Text style={styles.sourceValue}>
              국가법령정보(law.go.kr) · 찾기쉬운 생활법령(easylaw.go.kr)
            </Text>
          </View>
          <View style={styles.sourceRow}>
            <Text style={styles.sourceLabel}>행정 절차</Text>
            <Text style={styles.sourceValue}>
              정부24 · 공공데이터포털 · 각 부처 고시
            </Text>
          </View>
          <View style={styles.sourceRow}>
            <Text style={styles.sourceLabel}>지역 매핑</Text>
            <Text style={styles.sourceValue}>
              도로명주소 API · 행정표준코드
            </Text>
          </View>
        </View>

        {/* 데이터 관리 */}
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>데이터 관리</Text>
          <Pressable style={styles.dangerBtn} onPress={handleClearData}>
            <Ionicons name="trash" size={16} color={colors.danger} />
            <Text style={styles.dangerText}>
              체크리스트 · 완료 상태 초기화
            </Text>
          </Pressable>
        </View>

        <Text style={styles.footer}>
          © 2026 MSAI09 2차 프로젝트 · 이사이상무
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function InfoRow({
  icon,
  label,
  value,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
}) {
  return (
    <View style={styles.infoRow}>
      <Ionicons name={icon} size={18} color={colors.primaryLight} />
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.lg, paddingBottom: spacing.xxl },
  h1: { ...typography.display },
  h1Sub: {
    ...typography.caption,
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  card: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md + 2,
    borderWidth: 1,
    borderColor: colors.borderLight,
    marginBottom: spacing.md,
  },
  sectionTitle: {
    ...typography.subtitle,
    marginBottom: spacing.md,
  },
  policyHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  policyBody: {
    ...typography.caption,
    fontSize: 12,
    lineHeight: 19,
    color: colors.textSub,
  },
  sourceRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    paddingVertical: 6,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  sourceLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
    width: 64,
  },
  sourceValue: {
    flex: 1,
    fontSize: 12,
    color: colors.textSub,
    lineHeight: 18,
  },
  sourceFooter: {
    marginTop: spacing.sm,
    fontSize: 11,
    color: colors.textMute,
    fontStyle: 'italic',
  },
  label: {
    ...typography.captionBold,
    color: colors.text,
    marginBottom: spacing.xs,
  },
  scaleRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  scaleBtn: {
    flex: 1,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.cardBg,
    alignItems: 'center',
  },
  scaleBtnActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  scaleBtnText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.text,
  },
  scaleBtnTextActive: {
    color: '#fff',
  },
  input: {
    backgroundColor: colors.bg,
    borderRadius: radius.sm,
    padding: spacing.sm + 4,
    fontSize: 14,
    fontWeight: '500',
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  saveBtn: {
    backgroundColor: colors.primary,
    paddingVertical: spacing.sm + 4,
    borderRadius: radius.sm,
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  saveText: { color: '#fff', fontSize: 14, fontWeight: '800' },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.sm,
  },
  statusText: { ...typography.caption, flex: 1 },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm + 2,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  infoLabel: { ...typography.captionBold, color: colors.text, flex: 1 },
  infoValue: { ...typography.caption, color: colors.textSub },
  dangerBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm + 4,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.danger,
  },
  dangerText: {
    color: colors.danger,
    fontSize: 14,
    fontWeight: '700',
  },
  footer: {
    ...typography.caption,
    textAlign: 'center',
    marginTop: spacing.md,
  },
});
