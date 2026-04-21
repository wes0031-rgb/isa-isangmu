/**
 * Home Dashboard — 저장된 체크리스트 기반 D-day 카운트다운 + 임박 마감일 위젯.
 */
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import {
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppPressable } from '../../components/AppPressable';
import { api } from '../../lib/api';
import { Text } from '../../lib/AppText';
import {
  StoredChecklist,
  CompletionMap,
  loadChecklist,
  loadCompletions,
} from '../../lib/storage';
import { colors, radius, spacing, typography } from '../../theme/colors';

function daysUntil(dateStr: string): number {
  const target = new Date(dateStr);
  target.setHours(0, 0, 0, 0);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = target.getTime() - today.getTime();
  return Math.round(diff / (1000 * 60 * 60 * 24));
}

function itemKey(category: string, title: string): string {
  return `${category}::${title}`;
}

export default function Home() {
  const router = useRouter();
  const [health, setHealth] = useState<
    { service: string; version: string; azure_ready: boolean } | null
  >(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [saved, setSaved] = useState<StoredChecklist | null>(null);
  const [completions, setCompletions] = useState<CompletionMap>({});

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      // health 체크 + 실패 시 1회 자동 재시도 (Render cold start 흡수).
      // 백엔드 wake-up 후엔 첫 요청 외 모두 빠름.
      async function checkHealth(retry = false) {
        try {
          const h = await api.health();
          if (!cancelled) {
            setHealth(h);
            setHealthError(null);
          }
        } catch (e: any) {
          if (cancelled) return;
          if (!retry) {
            setHealthError('백엔드가 깨어나는 중이에요... (잠시 후 자동 재시도)');
            setTimeout(() => checkHealth(true), 5000);
          } else {
            setHealthError('백엔드 연결 실패 — 네트워크 또는 서버 상태를 확인하세요');
          }
        }
      }
      checkHealth();
      loadChecklist().then(setSaved);
      loadCompletions().then(setCompletions);
      return () => {
        cancelled = true;
      };
    }, []),
  );

  const daysToMove = saved ? daysUntil(saved.request.move_date) : null;
  const completedCount = saved
    ? saved.response.items.filter(
        (it) => completions[itemKey(it.category, it.title)],
      ).length
    : 0;
  const totalCount = saved?.response.total_items ?? 0;
  const progress =
    totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  // 오늘 시작해야 하는 일 (start_date 가 오늘, 미완료)
  const todayTasks = saved
    ? saved.response.items
        .filter((it) => {
          if (!it.start_date) return false;
          if (completions[itemKey(it.category, it.title)]) return false;
          return daysUntil(it.start_date) === 0;
        })
        .slice(0, 5)
    : [];

  // 앞으로 가장 임박한 마감일 상위 3건
  const upcomingDeadlines = saved
    ? saved.response.items
        .filter((it) => {
          if (!it.deadline_date) return false;
          if (completions[itemKey(it.category, it.title)]) return false;
          return daysUntil(it.deadline_date) >= 0;
        })
        .sort(
          (a, b) =>
            daysUntil(a.deadline_date!) - daysUntil(b.deadline_date!),
        )
        .slice(0, 3)
    : [];

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <ScrollView contentContainerStyle={styles.container}>
        {/* Greeting */}
        <View style={styles.greeting}>
          <View style={styles.welcomeRow}>
            <Ionicons
              name="hand-right"
              size={18}
              color={colors.accent}
            />
            <Text style={styles.welcome}>어서와요</Text>
          </View>
          <Text style={styles.userName}>이사이상무</Text>
        </View>

        {/* D-day hero card */}
        {saved && daysToMove !== null ? (
          <View style={styles.heroCard}>
            <View style={styles.heroHeader}>
              <Text style={styles.heroLabel}>이사까지</Text>
              <Text style={styles.heroRegion}>{saved.request.region}</Text>
            </View>
            <Text style={styles.heroDay}>
              {daysToMove >= 0 ? `D-${daysToMove}` : `D+${-daysToMove}`}
            </Text>
            <Text style={styles.heroDate}>{saved.request.move_date}</Text>

            {totalCount > 0 && (
              <View style={styles.progressWrap}>
                <View style={styles.progressRow}>
                  <Text style={styles.progressLabel}>
                    진행률 {completedCount}/{totalCount}
                  </Text>
                  <Text style={styles.progressValue}>{progress}%</Text>
                </View>
                <View style={styles.progressBar}>
                  <View
                    style={[styles.progressFill, { width: `${progress}%` }]}
                  />
                </View>
              </View>
            )}
          </View>
        ) : (
          <AppPressable
            style={styles.emptyHero}
            onPress={() => router.push('/(tabs)/checklist')}
          >
            <Image
              source={require('../../assets/duck-wave.png')}
              style={styles.emptyHeroDuck}
              resizeMode="contain"
            />
            <Text style={styles.emptyHeroTitle}>안녕하세요! 🐣</Text>
            <Text style={styles.emptyHeroSub}>
              조건 몇 개만 알려주세요{'\n'}D-day 타임라인 만들어드릴게요
            </Text>
          </AppPressable>
        )}

        {/* Backend status — 재시도 중이면 warning 색, 최종 실패만 danger */}
        {(health || healthError) && (
        <View
          style={[
            styles.statusCard,
            healthError
              ? {
                  backgroundColor: healthError.includes('깨어나는')
                    ? colors.warningBg
                    : colors.dangerBg,
                }
              : { backgroundColor: colors.cardBg },
          ]}
        >
          {healthError ? (
            <>
              <Ionicons
                name={healthError.includes('깨어나는') ? 'sync' : 'alert-circle'}
                size={18}
                color={healthError.includes('깨어나는') ? colors.warning : colors.danger}
              />
              <Text style={[styles.statusError, healthError.includes('깨어나는') && { color: colors.warning }]}>
                {healthError}
              </Text>
            </>
          ) : health ? (
            <>
              <Ionicons
                name={health.azure_ready ? 'sparkles' : 'construct'}
                size={18}
                color={colors.primaryLight}
              />
              <Text style={styles.statusText}>
                {health.azure_ready
                  ? 'Azure LLM 모드'
                  : 'Local fallback 모드'}
              </Text>
              <Text style={styles.statusVersion}>v{health.version}</Text>
            </>
          ) : null}
        </View>
        )}

        {/* Today tasks — 오늘 시작할 일 */}
        {todayTasks.length > 0 && (
          <View style={styles.sectionBlock}>
            <View style={styles.sectionTitleRow}>
              <Ionicons name="today" size={18} color={colors.accent} />
              <Text style={styles.sectionTitle}>오늘 할 일 · {todayTasks.length}건</Text>
            </View>
            {todayTasks.map((it, idx) => (
              <Pressable
                key={idx}
                style={styles.todayCard}
                onPress={() =>
                  router.push({
                    pathname: '/checklist/[id]',
                    params: {
                      id: itemKey(it.category, it.title),
                    },
                  })
                }
              >
                <View style={styles.todayBadge}>
                  <Ionicons name="flash" size={16} color="#fff" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.todayTitle}>{it.title}</Text>
                  <Text style={styles.todayMeta}>
                    {it.category}
                    {it.deadline_date ? ` · ${it.deadline_date} 까지` : ''}
                  </Text>
                </View>
                <Ionicons
                  name="chevron-forward"
                  size={18}
                  color={colors.textMute}
                />
              </Pressable>
            ))}
          </View>
        )}

        {/* Upcoming deadlines */}
        {upcomingDeadlines.length > 0 && (
          <View style={styles.sectionBlock}>
            <View style={styles.sectionTitleRow}>
              <Ionicons name="alarm" size={18} color={colors.warning} />
              <Text style={styles.sectionTitle}>임박한 마감일</Text>
            </View>
            {upcomingDeadlines.map((it, idx) => {
              const days = daysUntil(it.deadline_date!);
              const severity = days <= 3 ? 'danger' : days <= 7 ? 'warning' : 'ok';
              return (
                <Pressable
                  key={idx}
                  style={[
                    styles.deadlineCard,
                    severity === 'danger' && { borderLeftColor: colors.danger },
                    severity === 'warning' && {
                      borderLeftColor: colors.warning,
                    },
                  ]}
                  onPress={() =>
                    router.push({
                      pathname: '/checklist/[id]',
                      params: {
                        id: itemKey(it.category, it.title),
                      },
                    })
                  }
                >
                  <View style={styles.deadlineDayBadge}>
                    <Text style={styles.deadlineDayText}>
                      D-{days}
                    </Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.deadlineTitle}>{it.title}</Text>
                    <Text style={styles.deadlineDate}>
                      {it.deadline_date} 까지
                    </Text>
                  </View>
                  <Ionicons
                    name="chevron-forward"
                    size={18}
                    color={colors.textMute}
                  />
                </Pressable>
              );
            })}
          </View>
        )}

        {/* Main CTAs */}
        <View style={styles.ctaGroup}>
          <AppPressable
            style={styles.bigCta}
            onPress={() => router.push('/(tabs)/checklist')}
          >
            <View style={styles.ctaIcon}>
              <Ionicons name="list" size={26} color="#fff" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.ctaTitle}>
                {saved ? '체크리스트 보기' : '체크리스트 만들기'}
              </Text>
              <Text style={styles.ctaDesc}>
                {saved
                  ? `${totalCount}개 항목 · ${progress}% 완료`
                  : '조건 입력 → D-day 타임라인 자동 생성'}
              </Text>
            </View>
            <Ionicons
              name="chevron-forward"
              size={20}
              color={colors.textSub}
            />
          </AppPressable>

          <AppPressable
            style={styles.bigCta}
            onPress={() => router.push('/(tabs)/safecontract')}
          >
            <View
              style={[styles.ctaIcon, { backgroundColor: colors.accent }]}
            >
              <Ionicons name="shield-checkmark" size={26} color="#fff" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.ctaTitle}>계약 전 체크</Text>
              <Text style={styles.ctaDesc}>
                등기부등본 해석 + 기존 서비스 안내
              </Text>
            </View>
            <Ionicons
              name="chevron-forward"
              size={20}
              color={colors.textSub}
            />
          </AppPressable>
        </View>

        <Text style={styles.footerNote}>
          ※ 본 서비스는 법률 자문이 아닌 참고용 도구입니다.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function StatCard({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit: string;
}) {
  return (
    <View style={styles.statCard}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statUnit}>{unit}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.lg, paddingBottom: spacing.xxl },
  greeting: { marginBottom: spacing.lg },
  welcomeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  welcome: { ...typography.caption, fontSize: 14 },
  userName: { ...typography.display, marginTop: spacing.xs },

  // Hero
  heroCard: {
    backgroundColor: colors.primary,
    borderRadius: radius.lg,
    padding: spacing.lg + 4,
    marginBottom: spacing.md,
    borderLeftWidth: 4,
    borderLeftColor: colors.accent,
  },
  heroHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  heroLabel: { color: colors.primaryMute, fontSize: 14, fontWeight: '700' },
  heroRegion: { color: colors.primaryMute, fontSize: 13, fontWeight: '500' },
  heroDay: {
    color: colors.accent,
    fontSize: 56,
    fontWeight: '900',
    marginTop: spacing.sm,
    letterSpacing: -1,
    textShadowColor: 'rgba(245, 166, 35, 0.35)',
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 12,
  },
  heroDate: {
    color: colors.primaryMute,
    fontSize: 14,
    marginBottom: spacing.md,
    fontWeight: '500',
  },
  progressWrap: { marginTop: spacing.sm },
  progressRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  progressLabel: { color: colors.primaryMute, fontSize: 13, fontWeight: '600' },
  progressValue: { color: '#fff', fontSize: 14, fontWeight: '800' },
  progressBar: {
    height: 8,
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  progressFill: { height: '100%', backgroundColor: colors.accent },

  // Empty
  emptyHero: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: colors.accent,
    borderStyle: 'dashed',
    marginBottom: spacing.md,
  },
  emptyHeroDuck: {
    width: 96,
    height: 112,
  },
  emptyHeroTitle: {
    ...typography.subtitle,
    marginTop: spacing.sm,
  },
  emptyHeroSub: { ...typography.caption, marginTop: spacing.xs, textAlign: 'center', lineHeight: 18 },

  // Status
  statusCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  statusText: { ...typography.captionBold, flex: 1 },
  statusVersion: { ...typography.caption, color: colors.textMute },
  statusError: { ...typography.captionBold, color: colors.danger, flex: 1 },

  // Upcoming
  sectionBlock: { marginBottom: spacing.lg },
  sectionTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: spacing.sm,
  },
  sectionTitle: {
    ...typography.subtitle,
  },
  deadlineCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.cardBg,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: spacing.sm,
    borderLeftWidth: 4,
    borderLeftColor: colors.primaryLight,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  deadlineDayBadge: {
    backgroundColor: colors.primary,
    width: 48,
    height: 48,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  deadlineDayText: { color: '#fff', fontSize: 13, fontWeight: '800' },
  deadlineTitle: { ...typography.bodyBold, fontSize: 15 },
  deadlineDate: { ...typography.caption, marginTop: 2 },

  // Today tasks
  todayCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.cardBg,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: spacing.sm,
    borderLeftWidth: 4,
    borderLeftColor: colors.accent,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  todayBadge: {
    backgroundColor: colors.accent,
    width: 36,
    height: 36,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  todayTitle: { ...typography.bodyBold, fontSize: 15 },
  todayMeta: { ...typography.caption, marginTop: 2 },

  // CTAs
  ctaGroup: { gap: spacing.md, marginBottom: spacing.lg },
  bigCta: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.cardBg,
    padding: spacing.md + 2,
    borderRadius: radius.lg,
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  ctaIcon: {
    width: 56,
    height: 56,
    borderRadius: radius.md,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ctaTitle: { ...typography.subtitle },
  ctaDesc: { ...typography.caption, marginTop: 3 },

  // Stats
  statsRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.lg },
  statCard: {
    flex: 1,
    backgroundColor: colors.cardBg,
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  statValue: { fontSize: 26, fontWeight: '800', color: colors.accent },
  statUnit: { ...typography.caption, fontSize: 11 },
  statLabel: { ...typography.caption, marginTop: spacing.xs, fontWeight: '600' },

  footerNote: {
    ...typography.caption,
    textAlign: 'center',
  },
});
