import { ComponentProps } from 'react';
import { Platform, Pressable, StyleProp, ViewStyle } from 'react-native';

type PressableProps = ComponentProps<typeof Pressable>;

interface Props extends Omit<PressableProps, 'style' | 'android_ripple'> {
  style?: StyleProp<ViewStyle>;
  scale?: number;
  rippleColor?: string;
}

/**
 * Pressable with unified press feedback:
 * - iOS: scale 0.96 + opacity 0.85 on press
 * - Android: ripple + scale
 */
export function AppPressable({ style, scale = 0.96, rippleColor = 'rgba(0, 58, 117, 0.1)', children, ...rest }: Props) {
  return (
    <Pressable
      {...rest}
      android_ripple={{ color: rippleColor, borderless: false }}
      style={({ pressed }) => [
        style,
        pressed && Platform.OS === 'ios' && {
          opacity: 0.85,
          transform: [{ scale }],
        },
      ]}
    >
      {children}
    </Pressable>
  );
}
