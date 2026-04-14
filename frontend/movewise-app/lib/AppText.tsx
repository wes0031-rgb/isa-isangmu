/**
 * 스케일 자동 적용 Text — 프로젝트 전역에서 RN Text 대신 사용.
 *
 * MY 탭 글자 크기 토글(normal/large/xlarge)을 구독해서
 * 개별 Text 의 fontSize / lineHeight 에 SCALE_FACTORS 를 자동으로 곱함.
 * React 19 의 RN 0.81 Text 는 function component 라 render 몽키패치가
 * 동작하지 않아서, wrapper 컴포넌트 접근으로 대체.
 */
import React from 'react';
import { StyleSheet, Text as RNText, TextProps } from 'react-native';

import { typography } from '../theme/colors';
import { SCALE_FACTORS, useFontScaleLevel } from './fontScale';

export function Text(props: TextProps) {
  const [level] = useFontScaleLevel();
  const scale = SCALE_FACTORS[level];

  if (scale === 1.0) {
    return <RNText {...props} />;
  }

  const flat = StyleSheet.flatten(props.style) || {};
  const baseFontSize =
    typeof (flat as any).fontSize === 'number'
      ? (flat as any).fontSize
      : typography.body.fontSize;
  const baseLineHeight =
    typeof (flat as any).lineHeight === 'number'
      ? (flat as any).lineHeight
      : undefined;

  return (
    <RNText
      {...props}
      style={[
        props.style,
        {
          fontSize: baseFontSize * scale,
          ...(baseLineHeight ? { lineHeight: baseLineHeight * scale } : {}),
        },
      ]}
    />
  );
}
