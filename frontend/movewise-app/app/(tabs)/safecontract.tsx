/**
 * SafeContract — 등기부등본 텍스트 분석.
 */
import { Ionicons } from '@expo/vector-icons';
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
import { colors, radius, spacing, typography } from '../../theme/colors';

export default function SafeContractScreen() {
  const [text, setText] = useState('');
  const [deposit, setDeposit] = useState('100000000');
  const [market, setMarket] = useState('300000000');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SafeContractResponse | null>(null);

  async function submit() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.safecontract({
        text,
        deposit_krw: parseInt(deposit, 10) || 0,
        expected_market_price_krw: parseInt(market, 10) || 0,
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.container}>
          <Text style={styles.h1}>SafeContract</Text>
          <Text style={styles.h1Sub}>
            등기부등본을 쉬운 말로 해석해드립니다
          </Text>

          <Text style={styles.label}>등기부등본 텍스트</Text>
          <TextInput
            value={text}
            onChangeText={setText}
            placeholder="인터넷등기소에서 복사한 갑구/을구 텍스트 붙여넣기"
            multiline
            style={styles.textarea}
            textAlignVertical="top"
          />

          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>보증금 (원)</Text>
              <TextInput
                value={deposit}
                onChangeText={setDeposit}
                keyboardType="numeric"
                style={styles.input}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>예상 시세 (원)</Text>
              <TextInput
                value={market}
                onChangeText={setMarket}
                keyboardType="numeric"
                style={styles.input}
              />
            </View>
          </View>

          <Pressable
            style={[
              styles.submitBtn,
              (loading || !text) && { opacity: 0.6 },
            ]}
            onPress={submit}
            disabled={loading || !text}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.submitText}>분석하기</Text>
            )}
          </Pressable>

          {error && (
            <View style={styles.errorBox}>
              <Ionicons name="warning" size={16} color={colors.danger} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          )}

          {result && <ResultView result={result} />}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function ResultView({ result }: { result: SafeContractResponse }) {
  const pct = Math.round(result.jeontse_ratio * 100);
  const color =
    result.jeontse_ratio >= 1.0
      ? colors.danger
      : result.jeontse_ratio >= 0.8
      ? colors.warning
      : colors.success;

  return (
    <View style={styles.resultSection}>
      <View style={styles.ratioCard}>
        <Text style={styles.ratioLabel}>깡통전세 비율</Text>
        <Text style={[styles.ratioValue, { color }]}>{pct}%</Text>
        <Text style={styles.ratioSummary}>{result.summary}</Text>
      </View>

      <Text style={styles.sectionH}>🚨 위험 항목</Text>
      {result.risks.length === 0 ? (
        <View style={styles.emptyCard}>
          <Text style={{ color: colors.textSub }}>
            감지된 위험 요소가 없습니다.
          </Text>
        </View>
      ) : (
        result.risks.map((r, idx) => <RiskCard key={idx} risk={r} />)
      )}

      <Text style={styles.sectionH}>🔗 다음에 확인하세요</Text>
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

      <Text style={styles.disclaimer}>{result.disclaimer}</Text>
    </View>
  );
}

function RiskCard({ risk }: { risk: RiskItem }) {
  const color =
    risk.severity === 'red'
      ? colors.danger
      : risk.severity === 'yellow'
      ? colors.warning
      : colors.success;
  const emoji = risk.severity === 'red' ? '🔴' : risk.severity === 'yellow' ? '🟡' : '🟢';

  return (
    <View style={[styles.riskCard, { borderLeftColor: color }]}>
      <Text style={styles.riskLabel}>
        {emoji} {risk.label}
      </Text>
      <Text style={styles.riskExplain}>{risk.explanation_plain}</Text>
      {risk.related_laws.map((c, i) => (
        <Text key={i} style={styles.riskCite}>
          📖 {c.law_name} {c.article}
        </Text>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.lg, paddingBottom: spacing.xxl },
  h1: { ...typography.display, fontSize: 26 },
  h1Sub: {
    ...typography.caption,
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  label: {
    ...typography.caption,
    fontSize: 13,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.sm,
    marginTop: spacing.sm,
  },
  textarea: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    fontSize: 13,
    minHeight: 160,
    borderWidth: 1,
    borderColor: colors.border,
  },
  input: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    fontSize: 14,
    borderWidth: 1,
    borderColor: colors.border,
  },
  row: { flexDirection: 'row', gap: spacing.sm },
  submitBtn: {
    backgroundColor: colors.primary,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    alignItems: 'center',
    marginTop: spacing.lg,
  },
  submitText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
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
  errorText: { color: colors.danger, fontSize: 12, flex: 1 },
  resultSection: { marginTop: spacing.xl },
  ratioCard: {
    backgroundColor: colors.cardBg,
    padding: spacing.lg,
    borderRadius: radius.lg,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.lg,
  },
  ratioLabel: { ...typography.caption },
  ratioValue: {
    fontSize: 48,
    fontWeight: '800',
    marginVertical: spacing.sm,
  },
  ratioSummary: { ...typography.body, fontWeight: '600' },
  sectionH: {
    ...typography.subtitle,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  emptyCard: {
    backgroundColor: colors.cardBg,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  riskCard: {
    backgroundColor: colors.cardBg,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: spacing.sm,
    borderLeftWidth: 4,
    borderWidth: 1,
    borderColor: colors.border,
  },
  riskLabel: { ...typography.subtitle, fontSize: 14, marginBottom: spacing.xs },
  riskExplain: { ...typography.body, fontSize: 13 },
  riskCite: {
    ...typography.caption,
    fontSize: 11,
    marginTop: spacing.xs,
  },
  referralCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.cardBg,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  referralIcon: { fontSize: 24 },
  referralName: { ...typography.subtitle, fontSize: 14 },
  referralDesc: { ...typography.caption, marginTop: 2 },
  disclaimer: {
    ...typography.caption,
    fontSize: 11,
    textAlign: 'center',
    marginTop: spacing.lg,
    color: colors.textMute,
  },
});
