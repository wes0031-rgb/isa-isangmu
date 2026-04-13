/**
 * Task Detail screen — 체크리스트 항목 클릭 시 상세 화면.
 */
import { Ionicons } from '@expo/vector-icons';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  Alert,
  Linking,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ChecklistItem } from '../../lib/api';
import {
  CompletionMap,
  loadChecklist,
  loadCompletions,
  toggleCompletion,
} from '../../lib/storage';
import { colors, radius, spacing, typography } from '../../theme/colors';

function itemKey(it: ChecklistItem): string {
  return `${it.category}::${it.title}`;
}

export default function TaskDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [item, setItem] = useState<ChecklistItem | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [completions, setCompletions] = useState<CompletionMap>({});

  useEffect(() => {
    (async () => {
      const saved = await loadChecklist();
      if (!saved) {
        setNotFound(true);
        return;
      }
      const idx = parseInt(String(id ?? '0'), 10);
      const it = saved.response.items[idx];
      if (!it) {
        setNotFound(true);
        return;
      }
      setItem(it);
      const c = await loadCompletions();
      setCompletions(c);
    })();
  }, [id]);

  if (notFound) {
    return (
      <SafeAreaView style={styles.root}>
        <Stack.Screen options={{ title: '항목 상세' }} />
        <View style={styles.emptyBox}>
          <Ionicons name="search-outline" size={48} color={colors.textMute} />
          <Text style={styles.emptyText}>항목을 찾을 수 없습니다</Text>
          <Pressable style={styles.backBtn} onPress={() => router.back()}>
            <Text style={styles.backBtnText}>돌아가기</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  if (!item) {
    return (
      <SafeAreaView style={styles.root}>
        <Stack.Screen options={{ title: '항목 상세' }} />
      </SafeAreaView>
    );
  }

  const done = !!completions[itemKey(item)];

  async function handleToggle() {
    if (!item) return;
    const map = await toggleCompletion(itemKey(item));
    setCompletions({ ...map });
  }

  async function handleShare() {
    if (!item) return;
    const lines = [
      `📌 ${item.title}`,
      `카테고리: ${item.category}`,
      `시작일: ${item.start_date} (D${item.d_day_offset >= 0 ? '+' : ''}${item.d_day_offset})`,
      item.deadline_date ? `마감: ${item.deadline_date} (${item.deadline_days}일 기한)` : '',
      item.penalty ? `과태료: ${item.penalty}` : '',
      '',
      item.description,
      '',
      ...item.citations.map((c) => `📖 ${c.law_name} ${c.article}`),
    ].filter(Boolean);
    try {
      await Share.share({ message: lines.join('\n') });
    } catch (e: any) {
      Alert.alert('공유 실패', e.message);
    }
  }

  function openLaw(lawName: string) {
    const query = encodeURIComponent(lawName);
    const url = `https://www.law.go.kr/법령/${query}`;
    Linking.openURL(url).catch(() =>
      Alert.alert('링크 열기 실패', '기본 브라우저로 열어주세요.'),
    );
  }

  return (
    <SafeAreaView style={styles.root}>
      <Stack.Screen options={{ title: '항목 상세' }} />
      <ScrollView contentContainerStyle={styles.container}>
        {/* D-day 배지 */}
        <View
          style={[
            styles.badge,
            {
              backgroundColor: item.has_legal_deadline
                ? colors.warning
                : colors.primaryLight,
            },
          ]}
        >
          <Text style={styles.badgeText}>
            D{item.d_day_offset >= 0 ? '+' : ''}
            {item.d_day_offset}
          </Text>
        </View>

        <Text style={styles.title}>{item.title}</Text>
        <Text style={styles.category}>{item.category}</Text>

        {/* 날짜 카드 */}
        <View style={styles.card}>
          <Row icon="calendar" label="시작일" value={item.start_date} />
          {item.deadline_date && (
            <Row
              icon="alarm"
              label="마감일"
              value={`${item.deadline_date} (${item.deadline_days}일 기한)`}
              color={colors.warning}
            />
          )}
          {item.penalty && (
            <Row
              icon="warning"
              label="과태료"
              value={item.penalty}
              color={colors.danger}
            />
          )}
        </View>

        {/* 설명 */}
        {item.description && (
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>📝 설명</Text>
            <Text style={styles.body}>{item.description}</Text>
          </View>
        )}

        {/* 방법 */}
        {item.method && (
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>🛠 신청 방법</Text>
            <Text style={styles.body}>{item.method}</Text>
          </View>
        )}

        {/* 연락처 */}
        {item.contact && (
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>☎ 연락처</Text>
            <Pressable onPress={() => Linking.openURL(`tel:${item.contact}`)}>
              <Text style={[styles.body, { color: colors.primaryLight, fontWeight: '700' }]}>
                {item.contact}
              </Text>
            </Pressable>
          </View>
        )}

        {/* 법 조항 citations */}
        {item.citations.length > 0 && (
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>📖 법적 근거</Text>
            {item.citations.map((c, i) => (
              <Pressable
                key={i}
                onPress={() => openLaw(c.law_name)}
                style={styles.citationRow}
              >
                <Ionicons
                  name="library"
                  size={16}
                  color={colors.primaryLight}
                />
                <Text style={styles.citationText}>
                  {c.law_name} {c.article}
                </Text>
                <Ionicons
                  name="open-outline"
                  size={14}
                  color={colors.textMute}
                />
              </Pressable>
            ))}
          </View>
        )}

        {/* 완료 토글 + 공유 */}
        <View style={styles.actions}>
          <Pressable
            style={[
              styles.actionBtn,
              done && { backgroundColor: colors.success },
            ]}
            onPress={handleToggle}
          >
            <Ionicons
              name={done ? 'checkmark-circle' : 'ellipse-outline'}
              size={20}
              color="#fff"
            />
            <Text style={styles.actionText}>
              {done ? '완료됨' : '완료로 표시'}
            </Text>
          </Pressable>
          <Pressable style={styles.actionBtnOutline} onPress={handleShare}>
            <Ionicons
              name="share-outline"
              size={20}
              color={colors.primary}
            />
            <Text style={styles.actionTextOutline}>공유</Text>
          </Pressable>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({
  icon,
  label,
  value,
  color,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <View style={styles.row}>
      <Ionicons name={icon} size={18} color={color ?? colors.primaryLight} />
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={[styles.rowValue, color ? { color } : undefined]}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.lg, paddingBottom: spacing.xxl },
  emptyBox: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xxl,
  },
  emptyText: {
    ...typography.subtitle,
    color: colors.textMute,
    marginVertical: spacing.md,
  },
  backBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
  },
  backBtnText: { color: '#fff', fontWeight: '700' },
  badge: {
    alignSelf: 'flex-start',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    marginBottom: spacing.sm,
  },
  badgeText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  title: { ...typography.display, fontSize: 24, marginBottom: spacing.xs },
  category: { ...typography.caption, marginBottom: spacing.lg },
  card: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  sectionTitle: {
    ...typography.subtitle,
    fontSize: 14,
    marginBottom: spacing.sm,
  },
  body: { ...typography.body, fontSize: 14, lineHeight: 22 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  rowLabel: {
    ...typography.caption,
    fontWeight: '600',
    minWidth: 60,
  },
  rowValue: { ...typography.body, fontSize: 13, flex: 1 },
  citationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  citationText: {
    ...typography.body,
    fontSize: 13,
    flex: 1,
    color: colors.primaryLight,
  },
  actions: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    backgroundColor: colors.primary,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
  },
  actionText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  actionBtnOutline: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.primary,
    backgroundColor: colors.cardBg,
  },
  actionTextOutline: { color: colors.primary, fontSize: 14, fontWeight: '700' },
});
