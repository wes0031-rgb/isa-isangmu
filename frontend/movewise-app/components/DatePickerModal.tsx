/**
 * DatePickerModal — 순수 React Native 달력 모달.
 * 외부 패키지 없이 웹/네이티브 모두 동작.
 */
import { Ionicons } from '@expo/vector-icons';
import { useMemo, useState } from 'react';
import {
  Modal,
  Pressable,
  StyleSheet,
  View,
} from 'react-native';

import { Text } from '../lib/AppText';
import { colors, radius, spacing, typography } from '../theme/colors';

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
const MONTH_NAMES = [
  '1월', '2월', '3월', '4월', '5월', '6월',
  '7월', '8월', '9월', '10월', '11월', '12월',
];

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function formatYmd(y: number, m: number, d: number): string {
  return `${y}-${pad2(m + 1)}-${pad2(d)}`;
}

function parseYmd(s: string): { y: number; m: number; d: number } {
  const [ys, ms, ds] = s.split('-');
  return { y: Number(ys), m: Number(ms) - 1, d: Number(ds) };
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

/**
 * 손 없는 날 — 민간 풍습 기준 양력 끝자리 9·0 인 날.
 * (9일, 10일, 19일, 20일, 29일, 30일)
 * 이사 수요가 몰려서 업체 예약 어렵고 비용 비쌈.
 */
function isSonEopsNeunNal(day: number): boolean {
  const last = day % 10;
  return last === 9 || last === 0;
}

export function DatePickerModal({
  visible,
  value,
  onClose,
  onSelect,
  minDate,
}: {
  visible: boolean;
  value: string;
  onClose: () => void;
  onSelect: (ymd: string) => void;
  minDate?: string;
}) {
  const initial = useMemo(() => {
    const v = value || formatYmd(new Date().getFullYear(), new Date().getMonth(), new Date().getDate());
    return parseYmd(v);
  }, [value]);

  const [year, setYear] = useState(initial.y);
  const [month, setMonth] = useState(initial.m);

  const dim = daysInMonth(year, month);
  const firstDay = new Date(year, month, 1).getDay();
  const cells: Array<number | null> = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= dim; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  const weeks: Array<Array<number | null>> = [];
  for (let i = 0; i < cells.length; i += 7) {
    weeks.push(cells.slice(i, i + 7));
  }

  const selected = value ? parseYmd(value) : null;
  const minParsed = minDate ? parseYmd(minDate) : null;

  function prevMonth() {
    if (month === 0) {
      setYear(year - 1);
      setMonth(11);
    } else {
      setMonth(month - 1);
    }
  }

  function nextMonth() {
    if (month === 11) {
      setYear(year + 1);
      setMonth(0);
    } else {
      setMonth(month + 1);
    }
  }

  function isBeforeMin(y: number, m: number, d: number): boolean {
    if (!minParsed) return false;
    if (y < minParsed.y) return true;
    if (y > minParsed.y) return false;
    if (m < minParsed.m) return true;
    if (m > minParsed.m) return false;
    return d < minParsed.d;
  }

  return (
    <Modal
      transparent
      visible={visible}
      animationType="fade"
      onRequestClose={onClose}
    >
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <Pressable onPress={prevMonth} hitSlop={12}>
              <Ionicons name="chevron-back" size={22} color={colors.primary} />
            </Pressable>
            <Text style={styles.headerTitle}>
              {year}년 {MONTH_NAMES[month]}
            </Text>
            <Pressable onPress={nextMonth} hitSlop={12}>
              <Ionicons name="chevron-forward" size={22} color={colors.primary} />
            </Pressable>
          </View>

          <View style={styles.weekRow}>
            {WEEKDAYS.map((w, i) => (
              <Text
                key={w}
                style={[
                  styles.weekCell,
                  i === 0 && { color: colors.danger },
                  i === 6 && { color: colors.primaryLight },
                ]}
              >
                {w}
              </Text>
            ))}
          </View>

          {weeks.map((week, wi) => (
            <View key={wi} style={styles.weekRow}>
              {week.map((d, di) => {
                if (d === null) {
                  return <View key={di} style={styles.dayCell} />;
                }
                const isSelected =
                  selected &&
                  selected.y === year &&
                  selected.m === month &&
                  selected.d === d;
                const disabled = isBeforeMin(year, month, d);
                const isSun = di === 0;
                const isSat = di === 6;
                const isSonEopsEul = isSonEopsNeunNal(d);
                return (
                  <Pressable
                    key={di}
                    disabled={disabled}
                    onPress={() => {
                      onSelect(formatYmd(year, month, d));
                      onClose();
                    }}
                    style={[
                      styles.dayCell,
                      isSelected && styles.dayCellSelected,
                      disabled && { opacity: 0.25 },
                    ]}
                  >
                    <Text
                      style={[
                        styles.dayText,
                        isSelected && styles.dayTextSelected,
                        !isSelected && isSun && { color: colors.danger },
                        !isSelected && isSat && { color: colors.primaryLight },
                      ]}
                    >
                      {d}
                    </Text>
                    {isSonEopsEul && !isSelected && (
                      <View style={styles.sonEopsDot} />
                    )}
                  </Pressable>
                );
              })}
            </View>
          ))}

          {/* 범례 */}
          <View style={styles.legend}>
            <View style={styles.legendItem}>
              <View style={styles.legendDot} />
              <Text style={styles.legendText}>
                손 없는 날 (9·10·19·20·29·30일)
              </Text>
            </View>
            <Text style={styles.legendHint}>
              이사 수요가 몰려 업체 예약이 어렵고 비용이 더 들 수 있어요
            </Text>
          </View>

          <Pressable onPress={onClose} style={styles.closeBtn}>
            <Text style={styles.closeText}>닫기</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const CELL = 40;

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  sheet: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.lg,
    padding: spacing.lg,
    width: '100%',
    maxWidth: 360,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  headerTitle: {
    ...typography.subtitle,
    fontSize: 17,
    color: colors.primary,
  },
  weekRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 2,
  },
  weekCell: {
    width: CELL,
    textAlign: 'center',
    ...typography.caption,
    fontWeight: '700',
    paddingVertical: 4,
  },
  dayCell: {
    width: CELL,
    height: CELL,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
  },
  dayCellSelected: {
    backgroundColor: colors.primary,
  },
  dayText: {
    fontSize: 14,
    color: colors.text,
  },
  dayTextSelected: {
    color: '#fff',
    fontWeight: '700',
  },
  sonEopsDot: {
    position: 'absolute',
    bottom: 4,
    width: 5,
    height: 5,
    borderRadius: 3,
    backgroundColor: colors.warning,
  },
  legend: {
    marginTop: spacing.md,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  legendDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.warning,
  },
  legendText: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.warning,
  },
  legendHint: {
    ...typography.caption,
    fontSize: 11,
    color: colors.textMute,
    marginTop: 2,
    lineHeight: 15,
  },
  closeBtn: {
    marginTop: spacing.md,
    paddingVertical: spacing.sm,
    alignItems: 'center',
  },
  closeText: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '600',
  },
});
