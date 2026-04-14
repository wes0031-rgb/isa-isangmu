/**
 * 챗봇 탭 — 이사·전월세 질문 RAG 답변.
 * Azure 연결 전: 키워드 검색 기반 fallback
 * Azure 연결 후: GPT-4o 자연어 답변 (자동 전환)
 */
import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef, useState } from 'react';
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

import { api, ChatCitation, ChatResponse } from '../../lib/api';
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

interface ChatMessage {
  role: 'user' | 'bot';
  text: string;
  mode?: 'fallback' | 'azure';
  citations?: ChatCitation[];
}

export default function ChatScreen() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'bot',
      text: '안녕하세요! 이사·전월세 관련 궁금한 점을 물어보세요. 아래 프리셋을 선택하거나 직접 입력할 수 있어요.',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [presets, setPresets] = useState<string[]>([]);
  const scrollRef = useRef<ScrollView>(null);

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

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 88 : 0}
      >
        <View style={styles.header}>
          <Text style={styles.h1}>🐤 꽉꽉봇</Text>
          <Text style={styles.h1Sub}>
            이사·전월세 궁금한 점을 물어보세요
          </Text>
        </View>

        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
          contentContainerStyle={styles.messages}
          onContentSizeChange={() =>
            scrollRef.current?.scrollToEnd({ animated: true })
          }
          keyboardShouldPersistTaps="handled"
        >
          {messages.map((m, i) => (
            <MessageBubble key={i} message={m} />
          ))}
          {loading && (
            <View style={styles.loading}>
              <ActivityIndicator color={colors.primary} />
              <Text style={styles.loadingText}>답변 생성 중...</Text>
            </View>
          )}
        </ScrollView>

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
          <Pressable
            style={[styles.sendBtn, (!input.trim() || loading) && { opacity: 0.4 }]}
            onPress={() => send(input)}
            disabled={!input.trim() || loading}
          >
            <Ionicons name="send" size={20} color="#fff" />
          </Pressable>
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
          {message.text}
        </Text>
      </View>
      {isBot && message.citations && message.citations.length > 0 && (
        <View style={styles.citationsBox}>
          <Text style={styles.citationsLabel}>출처</Text>
          {message.citations.slice(0, 3).map((c, i) => (
            <Pressable
              key={i}
              style={styles.citationChip}
              onPress={() => {
                const url = resolveCitationUrl(c);
                if (url) Linking.openURL(url);
              }}
            >
              <Ionicons
                name={
                  c.source_type === 'law'
                    ? 'library'
                    : c.source_type === 'youtube'
                    ? 'logo-youtube'
                    : 'document-text'
                }
                size={12}
                color={colors.primaryLight}
              />
              <Text style={styles.citationText} numberOfLines={1}>
                {c.title}
              </Text>
              {c.url && (
                <Ionicons
                  name="open-outline"
                  size={10}
                  color={colors.textMute}
                />
              )}
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  header: { padding: spacing.lg, paddingBottom: spacing.sm },
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
  inputBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.cardBg,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
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
