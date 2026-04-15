/**
 * 챗봇 탭 — 이사·전월세 질문 RAG 답변.
 * Azure 연결 전: 키워드 검색 기반 fallback
 * Azure 연결 후: GPT-4o 자연어 답변 (자동 전환)
 */
import { Ionicons } from '@expo/vector-icons';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Image,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppPressable } from '../../components/AppPressable';
import { api, ChatCitation, ChatResponse } from '../../lib/api';
import { Text } from '../../lib/AppText';
import { buildMobileLawUrl, parseLawTitle } from '../../lib/lawUrl';
import { colors, radius, spacing, typography } from '../../theme/colors';

/** citation 을 모바일 친화 URL 로 변환. law 타입은 m.law.go.kr 사용. */
function resolveCitationUrl(c: ChatCitation): string | null {
  if (c.source_type === 'law') {
    const { law_name, article } = parseLawTitle(c.title);
    return buildMobileLawUrl(law_name, article);
  }
  return c.url || null;
}

type SourceKind = 'law' | 'procedure' | 'video';

const SOURCE_META: Record<SourceKind, { label: string; color: string; bg: string }> = {
  law: { label: '법률', color: '#003A75', bg: '#E6EEF8' },
  procedure: { label: '절차', color: '#4A5568', bg: '#EDF2F7' },
  video: { label: '영상', color: '#C53030', bg: '#FFF5F5' },
};

/** 본문의 [법률]/[절차]/[영상] 태그 → 컬러 배지, http(s) URL → 탭 가능한 링크. */
function renderAnswerWithTags(text: string, textColor: string) {
  // 태그 + URL 을 한 split 에서 함께 처리 (URL 은 마지막 구두점 제외)
  const parts = text.split(/(\[법률\]|\[절차\]|\[영상\]|https?:\/\/[^\s)]+[^\s.,!?)\]])/g);
  return parts.map((p, i) => {
    let kind: SourceKind | null = null;
    if (p === '[법률]') kind = 'law';
    else if (p === '[절차]') kind = 'procedure';
    else if (p === '[영상]') kind = 'video';
    if (kind) {
      const meta = SOURCE_META[kind];
      return (
        <Text
          key={i}
          style={{
            fontSize: 10,
            fontWeight: '800',
            color: meta.color,
            backgroundColor: meta.bg,
            paddingHorizontal: 5,
            paddingVertical: 1,
            borderRadius: 4,
            overflow: 'hidden',
          }}
        >
          {' '}{meta.label}{' '}
        </Text>
      );
    }
    if (/^https?:\/\//.test(p)) {
      return (
        <Text
          key={i}
          style={{
            color: SOURCE_META.video.color,
            textDecorationLine: 'underline',
            fontWeight: '600',
          }}
          onPress={() => Linking.openURL(p)}
        >
          {p}
        </Text>
      );
    }
    return (
      <Text key={i} style={{ color: textColor }}>
        {p}
      </Text>
    );
  });
}

interface ChatMessage {
  role: 'user' | 'bot';
  text: string;
  mode?: 'fallback' | 'azure';
  citations?: ChatCitation[];
}

const INITIAL_BOT_MESSAGE: ChatMessage = {
  role: 'bot',
  text: '안녕하세요! 이사·전월세 관련 궁금한 점을 물어보세요. 아래 프리셋을 선택하거나 직접 입력할 수 있어요.',
};

export default function ChatScreen() {
  const [messages, setMessages] = useState<ChatMessage[]>([INITIAL_BOT_MESSAGE]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [presets, setPresets] = useState<string[]>([]);

  useEffect(() => {
    api
      .chatPresets()
      .then(setPresets)
      .catch(() => setPresets([]));
  }, []);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', text: trimmed }]);
    setLoading(true);
    try {
      const res: ChatResponse = await api.chat(trimmed);
      setMessages((prev) => [
        ...prev,
        {
          role: 'bot',
          text: res.answer,
          mode: res.mode,
          citations: res.citations,
        },
      ]);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        { role: 'bot', text: `오류: ${e.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  // FlatList inverted 용: 메시지 배열을 역순으로 (최신이 인덱스 0)
  const invertedData: ChatMessage[] = [
    ...(loading ? [{ role: 'bot' as const, text: '__loading__' }] : []),
    ...[...messages].reverse(),
  ];

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 88 : 0}
      >
        <View style={styles.header}>
          <Image
            source={require('../../assets/duck-chat-header.png')}
            style={styles.headerDuck}
            resizeMode="contain"
          />
          <View style={{ flex: 1 }}>
            <Text style={styles.h1}>꽉꽉봇</Text>
            <Text style={styles.h1Sub}>
              이사·전월세 궁금한 점을 물어보세요
            </Text>
          </View>
        </View>

        <FlatList
          style={{ flex: 1 }}
          data={invertedData}
          inverted
          keyExtractor={(_, i) => `msg-${i}`}
          renderItem={({ item }) =>
            item.text === '__loading__' ? (
              <View style={styles.loading}>
                <ActivityIndicator color={colors.primary} />
                <Text style={styles.loadingText}>답변 생성 중...</Text>
              </View>
            ) : (
              <MessageBubble message={item} />
            )
          }
          contentContainerStyle={styles.messages}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        />

        {/* 프리셋 질문 */}
        {presets.length > 0 && messages.length < 3 && (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.presetsRow}
            contentContainerStyle={styles.presetsContent}
          >
            {presets.map((q, i) => (
              <Pressable
                key={i}
                style={styles.presetChip}
                onPress={() => send(q)}
              >
                <Text style={styles.presetText}>{q}</Text>
              </Pressable>
            ))}
          </ScrollView>
        )}

        {/* 법적 면책 + 개인정보 고지 (항상 보임) */}
        <View style={styles.disclaimerBar}>
          <Ionicons name="shield-checkmark-outline" size={12} color={colors.textSub} />
          <Text style={styles.disclaimerText}>
            참고용 답변입니다. 법률 자문이 아니며, 질문·답변은 서버에 저장되지 않아요.
          </Text>
        </View>

        {/* 입력창 */}
        <View style={styles.inputBar}>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder="질문을 입력하세요..."
            placeholderTextColor={colors.textMute}
            style={styles.input}
            onSubmitEditing={() => send(input)}
            returnKeyType="send"
            editable={!loading}
          />
          <AppPressable
            style={[styles.sendBtn, (!input.trim() || loading) && { opacity: 0.4 }]}
            onPress={() => send(input)}
            disabled={!input.trim() || loading}
          >
            <Ionicons name="send" size={20} color="#fff" />
          </AppPressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isBot = message.role === 'bot';
  return (
    <View
      style={[
        styles.bubbleWrap,
        { alignSelf: isBot ? 'flex-start' : 'flex-end' },
      ]}
    >
      {isBot && message.mode && (
        <View style={styles.modeBadge}>
          <Ionicons
            name={message.mode === 'azure' ? 'sparkles' : 'construct'}
            size={10}
            color={message.mode === 'azure' ? colors.primary : colors.textSub}
          />
          <Text style={styles.modeText}>
            {message.mode === 'azure' ? 'Azure LLM' : 'fallback'}
          </Text>
        </View>
      )}
      <View
        style={[
          styles.bubble,
          isBot ? styles.bubbleBot : styles.bubbleUser,
        ]}
      >
        <Text
          style={[
            styles.bubbleText,
            isBot ? { color: colors.text } : { color: '#fff' },
          ]}
        >
          {isBot
            ? renderAnswerWithTags(message.text, colors.text)
            : message.text}
        </Text>
      </View>
      {isBot && message.citations && message.citations.length > 0 && (
        <CitationsGrouped citations={message.citations} />
      )}
    </View>
  );
}

/** source_type 별 그룹핑된 출처 목록. 아이콘/색/한글 라벨로 구분. */
function CitationsGrouped({ citations }: { citations: ChatCitation[] }) {
  // backend source_type: 'law' | 'procedure' | 'youtube'
  // UI: law / procedure / video (youtube 를 video 로 매핑)
  const groups: Record<SourceKind, ChatCitation[]> = {
    law: [],
    procedure: [],
    video: [],
  };
  for (const c of citations) {
    if (c.source_type === 'law') groups.law.push(c);
    else if (c.source_type === 'procedure') groups.procedure.push(c);
    else if (c.source_type === 'youtube') groups.video.push(c);
  }
  const order: SourceKind[] = ['law', 'procedure', 'video'];
  return (
    <View style={styles.citationsBox}>
      <Text style={styles.citationsLabel}>출처</Text>
      {order.map((kind) => {
        const items = groups[kind];
        if (items.length === 0) return null;
        const meta = SOURCE_META[kind];
        return (
          <View key={kind} style={{ marginBottom: 4 }}>
            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 4,
                marginBottom: 2,
              }}
            >
              <Ionicons
                name={
                  kind === 'law'
                    ? 'library'
                    : kind === 'video'
                    ? 'logo-youtube'
                    : 'document-text'
                }
                size={11}
                color={meta.color}
              />
              <Text
                style={{
                  fontSize: 10,
                  fontWeight: '800',
                  color: meta.color,
                }}
              >
                {meta.label} · {items.length}건
              </Text>
            </View>
            {items.slice(0, 3).map((c, i) => (
              <Pressable
                key={i}
                style={[
                  styles.citationChip,
                  { backgroundColor: meta.bg, marginLeft: spacing.sm },
                ]}
                onPress={() => {
                  const url = resolveCitationUrl(c);
                  if (url) Linking.openURL(url);
                }}
              >
                <Text
                  style={[styles.citationText, { color: meta.color }]}
                  numberOfLines={1}
                >
                  {c.title}
                </Text>
                {c.url && (
                  <Ionicons
                    name="open-outline"
                    size={10}
                    color={meta.color}
                  />
                )}
              </Pressable>
            ))}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.lg,
    paddingBottom: spacing.sm,
  },
  headerDuck: { width: 64, height: 64 },
  h1: { ...typography.display },
  h1Sub: { ...typography.caption, marginTop: spacing.xs },
  messages: {
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  bubbleWrap: {
    maxWidth: '85%',
    marginBottom: spacing.md,
  },
  modeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    marginBottom: 4,
    paddingHorizontal: spacing.sm,
  },
  modeText: {
    fontSize: 10,
    fontWeight: '600',
    color: colors.textSub,
  },
  bubble: {
    padding: spacing.md,
    borderRadius: radius.lg,
  },
  bubbleBot: {
    backgroundColor: colors.cardBg,
    borderWidth: 1,
    borderColor: colors.borderLight,
    borderBottomLeftRadius: radius.sm,
  },
  bubbleUser: {
    backgroundColor: colors.primary,
    borderBottomRightRadius: radius.sm,
  },
  bubbleText: {
    fontSize: 14,
    lineHeight: 21,
  },
  citationsBox: {
    marginTop: spacing.xs,
    gap: 3,
  },
  citationsLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.textSub,
    marginBottom: 2,
  },
  citationChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.primaryBg,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.sm,
  },
  citationText: {
    fontSize: 11,
    color: colors.primary,
    flex: 1,
  },
  loading: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
  },
  loadingText: {
    ...typography.caption,
  },
  presetsRow: {
    maxHeight: 50,
    paddingHorizontal: spacing.lg,
  },
  presetsContent: {
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  presetChip: {
    backgroundColor: colors.cardBg,
    borderWidth: 1,
    borderColor: colors.primaryLight,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm - 2,
    marginRight: spacing.sm,
  },
  presetText: {
    fontSize: 12,
    color: colors.primary,
    fontWeight: '600',
  },
  disclaimerBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    backgroundColor: colors.primaryBg,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  disclaimerText: {
    fontSize: 10,
    color: colors.textSub,
    flex: 1,
  },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.cardBg,
  },
  input: {
    flex: 1,
    backgroundColor: colors.bg,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    fontSize: 14,
    color: colors.text,
  },
  sendBtn: {
    backgroundColor: colors.primary,
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
