/**
 * 챗봇 탭 — 이사·전월세 질문 RAG 답변.
 * Azure 연결 전: 키워드 검색 기반 fallback
 * Azure 연결 후: GPT-4o 자연어 답변 (자동 전환)
 */
import { Ionicons } from '@expo/vector-icons';
import { Audio } from 'expo-av';
import { useEffect, useRef, useState } from 'react';
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
            fontSize: 11,
            fontWeight: '800',
            color: meta.color,
            backgroundColor: meta.bg,
            paddingHorizontal: 6,
            paddingVertical: 2,
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
  // STT 녹음 상태 — Azure Speech-to-Text (ko-KR)
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [sttLoading, setSttLoading] = useState(false);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const recordingStartRef = useRef<number | null>(null);
  // Azure STT REST 는 최소 ~0.5s 유효 오디오 필요. 짧은 탭은 로컬에서 조기 차단.
  const MIN_RECORDING_MS = 500;

  useEffect(() => {
    api
      .chatPresets()
      .then(setPresets)
      .catch(() => setPresets([]));
  }, []);

  async function startRecording() {
    try {
      // 권한 요청 (마이크)
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) {
        setMessages((prev) => [
          ...prev,
          { role: 'bot', text: '마이크 권한이 없어요. 설정에서 허용 후 다시 시도해주세요.' },
        ]);
        return;
      }
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });
      // Azure STT 가 가장 잘 받는 포맷: WAV 16kHz mono PCM.
      // iOS: IOSOutputFormat.LINEARPCM 명시해야 실제 RIFF WAV 로 저장됨.
      // Android: MediaRecorder 가 PCM WAV 를 네이티브 지원 안 함 → MPEG_4/AAC 로 .m4a
      //          저장 후 backend 에서 ffmpeg 로 WAV 변환 (/api/stt 내부 처리).
      const rec = new Audio.Recording();
      await rec.prepareToRecordAsync({
        isMeteringEnabled: false,
        android: {
          extension: '.m4a',
          outputFormat: Audio.AndroidOutputFormat.MPEG_4,
          audioEncoder: Audio.AndroidAudioEncoder.AAC,
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 64000,
        },
        ios: {
          extension: '.wav',
          outputFormat: Audio.IOSOutputFormat.LINEARPCM,
          audioQuality: Audio.IOSAudioQuality.HIGH,
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 256000,
          linearPCMBitDepth: 16,
          linearPCMIsBigEndian: false,
          linearPCMIsFloat: false,
        },
        web: {
          mimeType: 'audio/webm',
          bitsPerSecond: 128000,
        },
      });
      await rec.startAsync();
      recordingRef.current = rec;
      recordingStartRef.current = Date.now();
      setRecording(rec);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        { role: 'bot', text: `녹음 시작 실패: ${e.message}` },
      ]);
    }
  }

  async function stopRecording() {
    const rec = recordingRef.current;
    if (!rec) return;
    const startedAt = recordingStartRef.current;
    setRecording(null);
    setSttLoading(true);
    try {
      await rec.stopAndUnloadAsync();
      // iOS 오디오 세션 복원 — 녹음 모드 유지 시 이후 TTS/알림음 경로가 뒤틀릴 수 있음.
      // Android 는 해당 key 무시 (no-op).
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false }).catch(() => {});
      const uri = rec.getURI();
      recordingRef.current = null;
      recordingStartRef.current = null;
      if (!uri) throw new Error('녹음 파일 경로 없음');
      // 최소 녹음 시간 가드 — 짧은 탭은 서버 호출 전 조기 차단 (비용·레이시 절감).
      const elapsed = startedAt ? Date.now() - startedAt : 0;
      if (elapsed > 0 && elapsed < MIN_RECORDING_MS) {
        setMessages((prev) => [
          ...prev,
          { role: 'bot', text: '녹음이 너무 짧아요. 마이크 버튼을 꾹 유지하고 말씀해주세요.' },
        ]);
        return;
      }
      // backend /api/stt 로 multipart 전송
      const { text, status } = await api.stt(uri);
      if (text.trim()) {
        setInput((prev) => (prev ? prev + ' ' + text : text));
      } else {
        // 인식 실패 케이스별 친절한 안내. status 가 Success 여도 text 가 비면 무음/짧음으로 처리.
        const reason =
          status === 'NoMatch'
            ? '말씀하신 내용을 인식 못 했어요. 더 또렷하게 다시 말해주세요.'
            : status === 'InitialSilenceTimeout'
            ? '소리가 없었어요. 마이크 권한·마이크 가까이 다시 시도해주세요.'
            : status === 'BabbleTimeout'
            ? '주변 소음이 너무 커요. 조용한 곳에서 다시 시도해주세요.'
            : '음성이 인식되지 않았어요. 너무 짧거나 무음일 수 있어요. 다시 시도해주세요.';
        setMessages((prev) => [...prev, { role: 'bot', text: reason }]);
      }
    } catch (e: any) {
      // 에러 카테고리 구분 — 네트워크 / 타임아웃 / 서버 / 기타
      const msg = (e?.message || '').toString();
      let text: string;
      if (msg.includes('서버 응답 시간 초과')) {
        text = '서버 응답이 늦어요. 잠시 후 다시 시도해주세요.';
      } else if (/Network request failed|TypeError.*fetch/i.test(msg)) {
        text = '네트워크 오류로 음성 인식에 실패했어요. 연결 확인 후 다시 시도해주세요.';
      } else if (/^STT\s+\d{3}/.test(msg) || /API\s+\d{3}/.test(msg)) {
        text = `서버 오류로 음성 인식에 실패했어요 (${msg.slice(0, 60)}).`;
      } else {
        text = `음성 인식 실패: ${msg.slice(0, 80)}`;
      }
      setMessages((prev) => [...prev, { role: 'bot', text }]);
    } finally {
      setSttLoading(false);
    }
  }

  function toggleMic() {
    if (sttLoading) return;
    if (recording) stopRecording();
    else startRecording();
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setInput('');
    // 멀티턴 — 이전 메시지를 history 로 전달 (initial bot message + 오류 메시지 제외, 최근 8개)
    const history = messages
      .filter((m) => m.text && !m.text.startsWith('오류:') && m !== INITIAL_BOT_MESSAGE)
      .slice(-8)
      .map((m) => ({
        role: (m.role === 'bot' ? 'assistant' : 'user') as 'user' | 'assistant',
        content: m.text,
      }));
    setMessages((prev) => [...prev, { role: 'user', text: trimmed }]);
    setLoading(true);
    try {
      const res: ChatResponse = await api.chat(trimmed, history);
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
            placeholder={recording ? '듣는 중... 다시 누르면 변환' : sttLoading ? '음성 변환 중...' : '질문을 입력하거나 마이크를 누르세요'}
            placeholderTextColor={colors.textMute}
            style={styles.input}
            onSubmitEditing={() => send(input)}
            returnKeyType="send"
            editable={!loading && !sttLoading}
          />
          <AppPressable
            style={[
              styles.micBtn,
              recording && styles.micBtnRecording,
              (loading || sttLoading) && { opacity: 0.4 },
            ]}
            onPress={toggleMic}
            disabled={loading || sttLoading}
            accessibilityLabel={recording ? '녹음 중지' : '음성 입력 시작'}
          >
            {sttLoading ? (
              <ActivityIndicator size="small" color={colors.primary} />
            ) : (
              <Ionicons
                name={recording ? 'stop' : 'mic'}
                size={20}
                color={recording ? '#fff' : colors.primary}
              />
            )}
          </AppPressable>
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
                size={12}
                color={meta.color}
              />
              <Text
                style={{
                  fontSize: 11,
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
    fontSize: 11,
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
    fontSize: 15,
    lineHeight: 23,
  },
  citationsBox: {
    marginTop: spacing.sm,
    gap: 4,
  },
  citationsLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.textSub,
    marginBottom: 3,
  },
  citationChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.primaryBg,
    paddingHorizontal: spacing.sm,
    paddingVertical: 5,
    borderRadius: radius.sm,
  },
  citationText: {
    fontSize: 12,
    color: colors.primary,
    flex: 1,
    lineHeight: 17,
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
    fontSize: 11,
    color: colors.textSub,
    lineHeight: 16,
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
  micBtn: {
    backgroundColor: colors.primaryBg,
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.primary,
  },
  micBtnRecording: {
    backgroundColor: colors.danger,
    borderColor: colors.danger,
  },
});
