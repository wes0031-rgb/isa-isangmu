/**
 * RegionPickerModal — 시/도 → 시/군/구 2단 선택 모달.
 */
import { Ionicons } from '@expo/vector-icons';
import { useMemo, useState } from 'react';
import {
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';

import { Text } from '../lib/AppText';
import { REGIONS, formatRegion, parseRegion } from '../lib/regions';
import { colors, radius, spacing, typography } from '../theme/colors';

export function RegionPickerModal({
  visible,
  value,
  onClose,
  onSelect,
}: {
  visible: boolean;
  value: string;
  onClose: () => void;
  onSelect: (region: string) => void;
}) {
  const parsed = parseRegion(value);
  const [selectedSido, setSelectedSido] = useState<string | null>(parsed?.sido ?? null);
  const [query, setQuery] = useState('');

  const sidoList = useMemo(() => {
    if (!query.trim()) return REGIONS;
    const q = query.trim();
    return REGIONS.filter(
      (r) => r.sido.includes(q) || r.districts.some((d) => d.includes(q)),
    );
  }, [query]);

  const districts = useMemo(() => {
    if (!selectedSido) return [];
    const region = REGIONS.find((r) => r.sido === selectedSido);
    if (!region) return [];
    if (!query.trim()) return region.districts;
    return region.districts.filter((d) => d.includes(query.trim()));
  }, [selectedSido, query]);

  function handleSelectDistrict(district: string) {
    if (!selectedSido) return;
    onSelect(formatRegion(selectedSido, district));
    onClose();
  }

  return (
    <Modal
      transparent
      visible={visible}
      animationType="slide"
      onRequestClose={onClose}
    >
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <View style={styles.header}>
            <Text style={styles.headerTitle}>지역 선택</Text>
            <Pressable onPress={onClose} hitSlop={12}>
              <Ionicons name="close" size={22} color={colors.text} />
            </Pressable>
          </View>

          <View style={styles.searchBox}>
            <Ionicons name="search" size={16} color={colors.textMute} />
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="시/도 또는 시/군/구 이름"
              placeholderTextColor={colors.textMute}
              style={styles.searchInput}
            />
          </View>

          <View style={styles.columns}>
            <FlatList
              style={styles.sidoCol}
              data={sidoList}
              keyExtractor={(r) => r.sido}
              renderItem={({ item }) => (
                <Pressable
                  style={[
                    styles.sidoRow,
                    selectedSido === item.sido && styles.sidoRowActive,
                  ]}
                  onPress={() => setSelectedSido(item.sido)}
                >
                  <Text
                    style={[
                      styles.sidoText,
                      selectedSido === item.sido && styles.sidoTextActive,
                    ]}
                  >
                    {item.sido.replace('특별자치', '').replace('특별시', '').replace('광역시', '').replace('도', '')}
                  </Text>
                </Pressable>
              )}
            />

            <FlatList
              style={styles.districtCol}
              data={districts}
              keyExtractor={(d) => d}
              ListEmptyComponent={
                <Text style={styles.emptyText}>
                  {selectedSido ? '검색 결과가 없습니다' : '왼쪽에서 시/도를 먼저 선택'}
                </Text>
              }
              renderItem={({ item }) => (
                <Pressable
                  style={styles.districtRow}
                  onPress={() => handleSelectDistrict(item)}
                >
                  <Text style={styles.districtText}>{item}</Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.textMute} />
                </Pressable>
              )}
            />
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: colors.cardBg,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    height: '75%',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  headerTitle: {
    ...typography.subtitle,
    fontSize: 17,
    color: colors.primary,
  },
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.bg,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  searchInput: {
    flex: 1,
    fontSize: 14,
    color: colors.text,
    padding: 0,
  },
  columns: {
    flex: 1,
    flexDirection: 'row',
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
  },
  sidoCol: {
    width: 110,
    backgroundColor: colors.bg,
    borderRightWidth: 1,
    borderRightColor: colors.border,
  },
  districtCol: {
    flex: 1,
  },
  sidoRow: {
    paddingVertical: spacing.md - 2,
    paddingHorizontal: spacing.md,
  },
  sidoRowActive: {
    backgroundColor: colors.cardBg,
    borderLeftWidth: 3,
    borderLeftColor: colors.primary,
  },
  sidoText: {
    ...typography.body,
    color: colors.textSub,
    fontWeight: '600',
  },
  sidoTextActive: {
    color: colors.primary,
  },
  districtRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md - 2,
    paddingHorizontal: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  districtText: {
    ...typography.body,
    color: colors.text,
  },
  emptyText: {
    ...typography.caption,
    textAlign: 'center',
    padding: spacing.lg,
  },
});
