/**
 * 앱 첫 진입 — 온보딩 페이지 스킵하고 바로 홈(tabs/index) 으로 이동.
 */
import { Redirect } from 'expo-router';

export default function Entry() {
  return <Redirect href="/(tabs)" />;
}
