/**
 * MY page — 서비스 정보 + 설정 (API URL, 사용자 이름).
 */
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { api, getApiUrl, setApiUrl } from '../../lib/api';
import { alertAsync, confirmAsync } from '../../lib/confirm';
import {
  clearChecklist,
  loadApiUrl,
  loadUserName,
  saveApiUrl,
  saveUserName,
} from '../../lib/storage';
import { colors, radius, spacing, typography } from '../../theme/colors';

export default function MyScreen() {
  const [apiInput, setApiInput] = useState(getApiUrl());
  const [userName, setUserName] = useState('');
  const [health, setHealth] = useState<
    { service: string; version: string; azure_ready: boolean } | null
  >(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Load persisted settings once
  useEffect(() => {
    (async () => {
      const savedUrl = await loadApiUrl();
      if (savedUrl) {
        setApiInput(savedUrl);
        setApiUrl(savedUrl);
      }
      const savedName = await loadUserName();
      if (savedName) setUserName(savedName);
    })();
  }, []);

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

  async function handleSaveApi() {
    setSaving(true);
    setApiUrl(apiInput);
    await saveApiUrl(apiInput);
    try {
      const h = await api.health();
      setHealth(h);
      setHealthError(null);
      alertAsync('저장 완료', `${h.service} v${h.version} 연결 확인됨`);
    } catch (e: any) {
      setHealthError(e.message);
      alertAsync('연결 실패', e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveName() {
    await saveUserName(userName);
    alertAsync('저장됨', `이름: ${userName || '(빈 값)'}`);
  }

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
        <Text style={styles.h1}>MY</Text>
        <Text style={styles.h1Sub}>계정 · 설정</Text>

        {/* 프로필 */}
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>프로필</Text>
          <Text style={styles.label}>이름</Text>
          <TextInput
            value={userName}
            onChangeText={setUserName}
            placeholder="이름 입력 (선택)"
            style={styles.input}
          />
          <Pressable style={styles.saveBtn} onPress={handleSaveName}>
            <Text style={styles.saveText}>저장</Text>
          </Pressable>
        </View>

        {/* 백엔드 설정 */}
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>백엔드 설정</Text>
          <Text style={styles.label}>API URL</Text>
          <TextInput
            value={apiInput}
            onChangeText={setApiInput}
            placeholder="https://..."
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.input}
          />
          <Pressable
            style={[styles.saveBtn, saving && { opacity: 0.6 }]}
            onPress={handleSaveApi}
            disabled={saving}
          >
            <Text style={styles.saveText}>
              {saving ? '확인 중...' : '저장 & 연결 확인'}
            </Text>
          </Pressable>
          <View style={styles.statusRow}>
            {healthError ? (
              <>
                <Ionicons
                  name="alert-circle"
                  size={16}
                  color={colors.danger}
                />
                <Text style={[styles.statusText, { color: colors.danger }]}>
                  {healthError}
                </Text>
              </>
            ) : health ? (
              <>
                <Ionicons
                  name={health.azure_ready ? 'sparkles' : 'construct'}
                  size={16}
                  color={colors.success}
                />
                <Text style={styles.statusText}>
                  {health.service} v{health.version} ·{' '}
                  {health.azure_ready ? 'Azure' : 'Local fallback'}
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
