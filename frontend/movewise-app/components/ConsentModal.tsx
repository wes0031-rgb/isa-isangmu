/**
 * 이용 동의 모달 — 앱 최초 진입 시 1회 표시.
 *
 * MSAI09 AI 윤리 평가 항목 대응:
 *   투명성 · 책임성 · 신뢰성 · 개인정보 · 공정성 · 포용성
 * + 법적 면책 + 개인정보 처리 요약 + 사용자 권리 명시.
 */
import { Ionicons } from '@expo/vector-icons';
import { Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Text } from '../lib/AppText';
import { colors, radius, spacing, typography } from '../theme/colors';

interface Props {
  visible: boolean;
  onAgree: () => void;
}

export function ConsentModal({ visible, onAgree }: Props) {
  return (
    <Modal
      visible={visible}
      animationType="fade"
      transparent={false}
      statusBarTranslucent
    >
      <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
        {/* 헤더 */}
        <View style={styles.header}>
          <View style={styles.logoBox}>
            <Ionicons name="shield-checkmark" size={28} color={colors.primary} />
          </View>
          <Text style={styles.h1}>이사이상무 이용 안내</Text>
          <Text style={styles.h1Sub}>
            시작 전 아래 안내를 꼭 확인해주세요
          </Text>
        </View>

        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={styles.scroll}
          showsVerticalScrollIndicator
        >
          {/* 섹션 1 — 서비스 성격 · 법적 면책 */}
          <Section icon="information-circle" color={colors.primary} title="서비스 성격">
            <Bullet>
              본 서비스는 <Bold>이사 절차에 대한 참고용 사전 검토 도구</Bold>이며,
              변호사·법무사 등 전문가의 법률 자문이 아닙니다.
            </Bullet>
            <Bullet>
              AI 모델 특성상 검색 결과에 포함되지 않은 정보는 답변에 제공되지 않으며,
              법 개정·최신 판례 미반영 등으로 오차가 있을 수 있습니다.
            </Bullet>
            <Bullet>
              실제 계약·분쟁·행정 처리는 반드시 해당 기관(주민센터·
              <Bold>법률구조공단 132</Bold>·변호사)에 확인하시기 바랍니다.
            </Bullet>
          </Section>

          {/* 섹션 2 — AI 윤리 6원칙 */}
          <Section icon="sparkles" color={colors.accent} title="AI 윤리 원칙">
            <RowPair
              label="투명성"
              body="모든 법률 인용은 원문 출처와 조문 번호를 제공합니다."
            />
            <RowPair
              label="책임성"
              body="답변 하단에 법적 면책 문구와 공식 상담 기관을 항상 안내합니다."
            />
            <RowPair
              label="신뢰성"
              body="검색 결과에 없는 정보는 답하지 않도록 설계되었습니다 (Hallucination 차단)."
            />
            <RowPair
              label="개인정보"
              body="비로그인·수집 최소화·업로드 파일 즉시 파기 원칙을 따릅니다."
            />
            <RowPair
              label="공정성"
              body="지역·국적·소득·가구 형태에 무관하게 동등한 품질로 안내합니다."
            />
            <RowPair
              label="포용성"
              body="큰 글씨 모드, 외국인·복지급여·병역 등 소수 상황도 동등 지원합니다."
            />
          </Section>

          {/* 섹션 3 — 개인정보 처리 */}
          <Section icon="lock-closed" color={colors.success} title="개인정보 처리">
            <RowPair
              label="수집 항목"
              body="체크리스트 입력값 (이사 지역·일정·세대유형·가족구성 등)과 선택 업로드 파일(등기부등본 PDF)."
            />
            <RowPair
              label="이용 목적"
              body="맞춤 체크리스트 생성, Azure AI Search · OpenAI 질의를 통한 답변 제공."
            />
            <RowPair
              label="서버 저장"
              body="질문·답변·체크리스트 결과는 서버에 영구 저장하지 않습니다."
            />
            <RowPair
              label="PDF 처리"
              body="업로드 파일은 분석 직후 즉시 파기되며 별도 데이터베이스에 저장하지 않습니다."
            />
            <RowPair
              label="보관 위치"
              body="체크리스트 진행 상태는 사용자 기기 로컬(AsyncStorage)에만 저장 — 앱 삭제 시 전량 소실."
            />
          </Section>

          {/* 섹션 4 — 사용자 권리 */}
          <Section icon="person-circle" color={colors.warning} title="사용자 권리">
            <Bullet>
              <Bold>조회·삭제</Bold>: 「마이 → 체크리스트·완료 상태 초기화」 에서
              언제든 기기 내 데이터 전량 삭제 가능합니다.
            </Bullet>
            <Bullet>
              <Bold>문의</Bold>: 개인정보 처리 관련 문의는 개인정보보호위원회
              1577-1000 또는 팀 대표 이메일을 통해 접수됩니다.
            </Bullet>
            <Bullet>
              <Bold>정책 변경</Bold>: 처리 방침이 변경될 경우 앱 내에서 재동의를
              요청드립니다.
            </Bullet>
          </Section>

          <View style={styles.footer}>
            <Text style={styles.footerText}>
              위 내용을 충분히 확인하였으며, 이용에 동의합니다.
            </Text>
          </View>
        </ScrollView>

        {/* 하단 동의 버튼 */}
        <View style={styles.btnBar}>
          <Pressable
            style={({ pressed }) => [
              styles.agreeBtn,
              pressed && { opacity: 0.85 },
            ]}
            onPress={onAgree}
            accessibilityRole="button"
            accessibilityLabel="동의하고 시작"
          >
            <Ionicons name="checkmark-circle" size={20} color="#fff" />
            <Text style={styles.agreeText}>동의하고 시작</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

// ===== 내부 조립 조각 =====

function Section({
  icon,
  color,
  title,
  children,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        <Ionicons name={icon} size={18} color={color} />
        <Text style={[styles.sectionTitle, { color }]}>{title}</Text>
      </View>
      {children}
    </View>
  );
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <View style={styles.bulletRow}>
      <Text style={styles.bulletDot}>•</Text>
      <Text style={styles.bulletText}>{children}</Text>
    </View>
  );
}

function RowPair({ label, body }: { label: string; body: string }) {
  return (
    <View style={styles.rowPair}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowBody}>{body}</Text>
    </View>
  );
}

function Bold({ children }: { children: React.ReactNode }) {
  return <Text style={{ fontWeight: '800' }}>{children}</Text>;
}

// ===== 스타일 =====

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    alignItems: 'center',
  },
  logoBox: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.primaryBg,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  h1: { ...typography.display, fontSize: 22, textAlign: 'center' },
  h1Sub: {
    ...typography.caption,
    textAlign: 'center',
    marginTop: spacing.xs,
  },
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.lg,
  },
  section: {
    backgroundColor: colors.cardBg,
    borderRadius: radius.lg,
    padding: spacing.md,
    marginTop: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  sectionTitle: { fontSize: 15, fontWeight: '800' },
  bulletRow: {
    flexDirection: 'row',
    marginTop: 4,
    paddingRight: spacing.sm,
  },
  bulletDot: {
    color: colors.textSub,
    marginRight: spacing.xs,
    marginTop: 1,
  },
  bulletText: {
    flex: 1,
    fontSize: 13,
    lineHeight: 20,
    color: colors.text,
  },
  rowPair: {
    marginTop: 4,
    paddingBottom: 6,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  rowLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.textSub,
    marginBottom: 2,
  },
  rowBody: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.text,
  },
  footer: {
    marginTop: spacing.lg,
    paddingVertical: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  footerText: {
    fontSize: 13,
    color: colors.textSub,
    textAlign: 'center',
  },
  btnBar: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
    backgroundColor: colors.cardBg,
  },
  agreeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    backgroundColor: colors.primary,
    paddingVertical: spacing.md,
    borderRadius: radius.pill,
  },
  agreeText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '800',
  },
});
