/**
 * Task Detail screen — 체크리스트 항목 클릭 시 상세 화면.
 */
import { Ionicons } from '@expo/vector-icons';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import {
  Image,
  Linking,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ChecklistItem, Citation } from '../../lib/api';
import { Text } from '../../lib/AppText';
import { alertAsync } from '../../lib/confirm';
import { buildMobileLawUrl } from '../../lib/lawUrl';
import {
  CompletionMap,
  loadChecklist,
  loadCompletions,
  loadCustomItems,
  loadNotes,
  setCompletion,
  setNote,
} from '../../lib/storage';
import { colors, radius, spacing, typography } from '../../theme/colors';

function itemKey(it: ChecklistItem): string {
  return `${it.category}::${it.title}`;
}

/** 이사일 기준 오프셋 → 사용자 친화적 라벨 ("이사 14일 전" / "이사 당일" / "이사 3일 후"). */
function formatMoveOffsetLabel(offset: number): string {
  if (offset === 0) return '이사 당일';
  if (offset < 0) return `이사 ${-offset}일 전`;
  return `이사 ${offset}일 후`;
}

export default function TaskDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [item, setItem] = useState<ChecklistItem | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [completions, setCompletions] = useState<CompletionMap>({});
  const [note, setNoteText] = useState('');
  const [noteSaved, setNoteSaved] = useState(true);

  // 언마운트 시 최신값으로 강제 저장하기 위한 refs — TextInput.onBlur 가
  // 뒤로가기/탭전환으로 건너뛰어지는 경우의 유실 방지용.
  const noteRef = useRef(note);
  const noteSavedRef = useRef(noteSaved);
  const itemRef = useRef<ChecklistItem | null>(null);
  useEffect(() => {
    noteRef.current = note;
  }, [note]);
  useEffect(() => {
    noteSavedRef.current = noteSaved;
  }, [noteSaved]);

  // 언마운트 시 한 번만 실행되는 fallback: TextInput.onBlur 를 놓친 경우
  // (뒤로가기·탭전환·딥링크 등) AsyncStorage 에 최신 메모 강제 저장.
  useEffect(() => {
    return () => {
      if (!noteSavedRef.current && itemRef.current) {
        setNote(itemKey(itemRef.current), noteRef.current).catch(() => {});
      }
    };
  }, []);

  useEffect(() => {
    (async () => {
      const saved = await loadChecklist();
      if (!saved) {
        setNotFound(true);
        return;
      }
      const customs = await loadCustomItems();
      const all = [...saved.response.items, ...customs];
      const it = all.find((x) => itemKey(x) === id);
      if (!it) {
        setNotFound(true);
        return;
      }
      setItem(it);
      itemRef.current = it;
      const c = await loadCompletions();
      setCompletions(c);
      const notes = await loadNotes();
      setNoteText(notes[itemKey(it)] || '');
    })();
  }, [id]);

  if (notFound) {
    return (
      <SafeAreaView style={styles.root}>
        <Stack.Screen options={{ title: '항목 상세' }} />
        <View style={styles.emptyBox}>
          <Image
            source={require('../../assets/duck-confused.png')}
            style={styles.emptyDuck}
            resizeMode="contain"
          />
          <Text style={styles.emptyTitle}>음...?</Text>
          <Text style={styles.emptyText}>찾으시는 항목이 없는 것 같아요</Text>
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

  function handleToggle() {
    if (!item) return;
    const key = itemKey(item);
    setCompletions((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      setCompletion(key, next[key]).catch(() => {
        setCompletions((p) => ({ ...p, [key]: !next[key] }));
      });
      return next;
    });
  }

  async function handleShare() {
    if (!item) return;
    const dday = formatMoveOffsetLabel(item.d_day_offset);
    const startLine = item.start_date
      ? `시작일: ${item.start_date} (${dday})`
      : `(${dday})`;
    const lines = [
      `[${item.title}]`,
      `카테고리: ${item.category}`,
      startLine,
      item.deadline_date ? `마감: ${item.deadline_date} (${item.deadline_days}일 기한)` : '',
      item.penalty ? `과태료: ${item.penalty}` : '',
      '',
      item.description,
      '',
      ...item.citations.map((c) => `[법] ${c.law_name} ${c.article}`),
    ].filter(Boolean);
    try {
      await Share.share({ message: lines.join('\n') });
    } catch (e: any) {
      alertAsync('공유 실패', e?.message ?? '알 수 없는 오류');
    }
  }

  function openLaw(lawName: string, article?: string | null) {
    const url = buildMobileLawUrl(lawName, article);
    Linking.openURL(url).catch(() =>
      alertAsync('링크 열기 실패', '기본 브라우저로 열어주세요.'),
    );
  }

  function handleNoteChange(text: string) {
    setNoteText(text);
    setNoteSaved(false);
  }

  async function handleNoteSave() {
    if (!item) return;
    await setNote(itemKey(item), note);
    setNoteSaved(true);
  }

  return (
    <SafeAreaView style={styles.root}>
      <Stack.Screen options={{ title: '항목 상세' }} />
      <ScrollView contentContainerStyle={styles.container}>
        {/* D-day 배지 — 이사일 기준 offset 으로 통일 (체크리스트 전체와 동일) */}
        <View style={styles.badgeRow}>
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
              {formatMoveOffsetLabel(item.d_day_offset)}
            </Text>
          </View>
          {item.start_date ? (
            <Text style={styles.offsetLabel}>시작일: {item.start_date}</Text>
          ) : null}
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

        {/* 설명 — 비어있으면 fallback 안내 (디테일 화면이 빈 카드처럼 보이지 않게) */}
        <View style={styles.card}>
          <SectionHeader icon="reader" title="설명" />
          <Text style={styles.body}>
            {item.description?.trim() ||
              '이 항목은 자동 생성된 안내입니다. 아래 법적 근거 또는 외부 링크에서 자세한 절차를 확인하세요.'}
          </Text>
        </View>

        {/* 방법 */}
        {item.method && (
          <View style={styles.card}>
            <SectionHeader icon="construct" title="신청 방법" />
            <Text style={styles.body}>{item.method}</Text>
          </View>
        )}

        {/* 연락처 */}
        {item.contact && (
          <View style={styles.card}>
            <SectionHeader icon="call" title="연락처" />
            <Pressable onPress={() => Linking.openURL(`tel:${item.contact}`)}>
              <Text style={[styles.body, { color: colors.primaryLight, fontWeight: '700' }]}>
                {item.contact}
              </Text>
            </Pressable>
          </View>
        )}

        {/* 법 조항 citations — 원문 텍스트 포함 */}
        {item.citations.length > 0 && (
          <View style={styles.card}>
            <SectionHeader icon="library" title="법적 근거" />
            {item.citations.map((c, i) => (
              <LawArticleCard key={i} citation={c} onOpenExternal={openLaw} />
            ))}
          </View>
        )}

        {/* 개인 메모 */}
        <View style={styles.card}>
          <View style={styles.noteHeader}>
            <SectionHeader icon="create" title="내 메모" />
            {!noteSaved && (
              <Pressable onPress={handleNoteSave} hitSlop={8}>
                <Text style={styles.noteSaveBtn}>저장</Text>
              </Pressable>
            )}
            {noteSaved && note.length > 0 && (
              <Ionicons
                name="checkmark-circle"
                size={16}
                color={colors.success}
              />
            )}
          </View>
          <TextInput
            value={note}
            onChangeText={handleNoteChange}
            onBlur={handleNoteSave}
            placeholder="담당자·주의사항·진행 메모를 자유롭게 적어보세요"
            placeholderTextColor={colors.textMute}
            multiline
            textAlignVertical="top"
            style={styles.noteInput}
          />
        </View>

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

function SectionHeader({
  icon,
  title,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
}) {
  return (
    <View style={styles.sectionHeaderRow}>
      <Ionicons name={icon} size={16} color={colors.primaryLight} />
      <Text style={styles.sectionTitle}>{title}</Text>
    </View>
  );
}

function LawArticleCard({
  citation,
  onOpenExternal,
}: {
  citation: Citation;
  onOpenExternal: (lawName: string, article?: string | null) => void;
}) {
  const hasText = !!citation.article_text;
  // 본문이 있으면 기본 펼침 — 사용자가 바로 조항 내용 확인 가능
  const [expanded, setExpanded] = useState(hasText);

  const handleToggle = () => {
    if (hasText) setExpanded((prev) => !prev);
    else onOpenExternal(citation.law_name, citation.article);
  };

  return (
    <View style={styles.lawArticle}>
      <Pressable
        onPress={handleToggle}
        hitSlop={8}
        android_ripple={{ color: colors.primaryBg }}
        style={({ pressed }) => [
          styles.lawHeader,
          pressed && { opacity: 0.6 },
        ]}
      >
        <Ionicons name="library" size={18} color={colors.primaryLight} />
        <View style={{ flex: 1 }}>
          <Text style={styles.lawTitle}>
            {citation.law_name} {citation.article}
          </Text>
          {citation.article_title && (
            <Text style={styles.lawSubtitle}>{citation.article_title}</Text>
          )}
        </View>
        {hasText ? (
          <Ionicons
            name={expanded ? 'chevron-up' : 'chevron-down'}
            size={18}
            color={colors.primaryLight}
          />
        ) : (
          <Ionicons name="open-outline" size={14} color={colors.textMute} />
        )}
      </Pressable>

      {expanded && citation.article_text && (
        <View style={styles.lawBodyBox}>
          {citation.article_text
            .split('\n')
            .map((l) => l.trim())
            .filter(Boolean)
            .map((line, i) => (
              <Text
                key={i}
                style={[styles.lawBody, i > 0 && { marginTop: 6 }]}
              >
                {line}
              </Text>
            ))}
          <Pressable
            onPress={() => onOpenExternal(citation.law_name, citation.article)}
            hitSlop={8}
            style={styles.lawExternalBtn}
          >
            <Ionicons name="open-outline" size={14} color={colors.primary} />
            <Text style={styles.lawExternalText}>전문 보기 (law.go.kr)</Text>
          </Pressable>
        </View>
      )}
    </View>
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
  emptyDuck: {
    width: 120,
    height: 140,
    marginBottom: spacing.md,
  },
  emptyTitle: {
    ...typography.title,
    color: colors.primary,
    marginBottom: spacing.xs,
  },
  emptyText: {
    ...typography.caption,
    color: colors.textSub,
    marginBottom: spacing.lg,
    textAlign: 'center',
  },
  backBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
  },
  backBtnText: { color: '#fff', fontWeight: '700' },
  badgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  offsetLabel: {
    ...typography.captionBold,
    fontSize: 12,
    color: colors.primary,
  },
  badge: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
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
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: spacing.sm,
  },
  sectionTitle: {
    ...typography.subtitle,
    fontSize: 15,
  },
  body: { ...typography.body, fontSize: 15, lineHeight: 23 },
  noteHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  noteSaveBtn: {
    ...typography.captionBold,
    color: colors.primary,
    fontSize: 12,
    marginBottom: spacing.sm,
  },
  noteInput: {
    minHeight: 70,
    backgroundColor: colors.bg,
    borderRadius: radius.sm,
    padding: spacing.sm,
    fontSize: 13,
    lineHeight: 19,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
  },
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
  lawArticle: {
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  lawHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  lawTitle: {
    ...typography.body,
    fontSize: 13,
    fontWeight: '700',
    color: colors.primaryLight,
  },
  lawSubtitle: {
    ...typography.caption,
    fontSize: 11,
    marginTop: 2,
  },
  lawBodyBox: {
    marginTop: spacing.sm,
    padding: spacing.sm,
    backgroundColor: colors.bg,
    borderRadius: radius.sm,
    borderLeftWidth: 3,
    borderLeftColor: colors.primaryLight,
  },
  lawBody: {
    ...typography.body,
    fontSize: 13,
    lineHeight: 21,
    color: colors.text,
  },
  lawExternalBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.sm,
    paddingVertical: spacing.xs,
    alignSelf: 'flex-start',
  },
  lawExternalText: {
    ...typography.caption,
    fontSize: 11,
    fontWeight: '700',
    color: colors.primary,
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
