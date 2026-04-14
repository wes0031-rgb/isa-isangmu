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
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { api } from '../../lib/api';
import { alertAsync, confirmAsync } from '../../lib/confirm';
import { clearChecklist } from '../../lib/storage';
import { colors, radius, spacing, typography } from '../../theme/colors';

export default function MyScreen() {
  const [health, setHealth] = useState<
    { service: string; version: string; azure_ready: boolean } | null
  >(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      api
        .health()
        .then((h) => {
          setHealth(h);
          setHealthError(null);
        })
        .catch((e) => setHealthError(e.message));
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

        {/* 시스템 상태 (읽기 전용) */}
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>시스템 상태</Text>
          <View style={styles.statusRow}>
            {healthError ? (
              <>
                <Ionicons
                  name="alert-circle"
                  size={18}
                  color={colors.danger}
                />
                <Text style={[styles.statusText, { color: colors.danger }]}>
                  서버 연결 실패
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
            icon="shield-checkmark"
            label="개인정보"
            value="즉시 파기 · 비로그인"
          />
          <InfoRow
            icon="document-text"
            label="법적 면책"
            value="참고용 도구, 법률 자문 아님"
          />
          <InfoRow
            icon="people"
            label="소속"
            value="MSAI09 2차 프로젝트"
          />
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
          © 2026 MSAI09 2차 프로젝트 · MoveWise
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
  label: {
    ...typography.captionBold,
    color: colors.text,
    marginBottom: spacing.xs,
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
