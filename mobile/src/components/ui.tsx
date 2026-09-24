import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  useColorScheme,
  View,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { dark, light, type Theme } from "@/lib/theme";

export function useTheme(): Theme {
  return useColorScheme() === "dark" ? dark : light;
}

export function Screen({
  children,
  style,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const theme = useTheme();
  return (
    <View style={[{ flex: 1, backgroundColor: theme.page, padding: 16 }, style]}>
      {children}
    </View>
  );
}

export function Card({
  children,
  title,
  subtitle,
  style,
}: {
  children?: ReactNode;
  title?: string;
  subtitle?: string;
  style?: StyleProp<ViewStyle>;
}) {
  const theme = useTheme();
  return (
    <View
      style={[
        {
          backgroundColor: theme.surface,
          borderColor: theme.border,
          borderWidth: StyleSheet.hairlineWidth,
          borderRadius: 12,
          padding: 16,
        },
        style,
      ]}
    >
      {title && (
        <Text style={{ color: theme.ink, fontSize: 15, fontWeight: "600" }}>{title}</Text>
      )}
      {subtitle && (
        <Text style={{ color: theme.inkMuted, fontSize: 12, marginTop: 2 }}>{subtitle}</Text>
      )}
      {children && <View style={{ marginTop: title ? 12 : 0 }}>{children}</View>}
    </View>
  );
}

export function Button({
  label,
  onPress,
  variant = "secondary",
  disabled,
  busy,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  busy?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const theme = useTheme();
  const background =
    variant === "primary"
      ? theme.accent
      : variant === "danger"
        ? theme.critical
        : theme.surfaceRaised;
  const color = variant === "secondary" ? theme.ink : theme.onAccent;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || busy }}
      onPress={onPress}
      disabled={disabled || busy}
      style={({ pressed }) => [
        {
          backgroundColor: background,
          borderColor: theme.border,
          borderWidth: variant === "secondary" ? StyleSheet.hairlineWidth : 0,
          borderRadius: 10,
          // 48px tall: this is tapped one-handed, often in a hurry.
          paddingVertical: 14,
          paddingHorizontal: 18,
          alignItems: "center",
          opacity: disabled || busy ? 0.5 : pressed ? 0.85 : 1,
        },
        style,
      ]}
    >
      {busy ? (
        <ActivityIndicator color={color} />
      ) : (
        <Text style={{ color, fontSize: 15, fontWeight: "600" }}>{label}</Text>
      )}
    </Pressable>
  );
}

export function Row({
  label,
  value,
  valueColor,
}: {
  label: string;
  value: string;
  valueColor?: string;
}) {
  const theme = useTheme();
  return (
    <View
      style={{
        flexDirection: "row",
        justifyContent: "space-between",
        alignItems: "center",
        paddingVertical: 6,
      }}
    >
      <Text style={{ color: theme.inkSecondary, fontSize: 14 }}>{label}</Text>
      <Text
        style={{ color: valueColor ?? theme.ink, fontSize: 14, fontWeight: "600" }}
        // Figures line up down the column.
        numberOfLines={1}
      >
        {value}
      </Text>
    </View>
  );
}

export function Pill({ label, color }: { label: string; color?: string }) {
  const theme = useTheme();
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: 6,
        borderColor: theme.border,
        borderWidth: StyleSheet.hairlineWidth,
        borderRadius: 999,
        paddingHorizontal: 10,
        paddingVertical: 4,
        alignSelf: "flex-start",
      }}
    >
      {color && (
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: color }} />
      )}
      <Text style={{ color: theme.inkSecondary, fontSize: 12, fontWeight: "500" }}>
        {label}
      </Text>
    </View>
  );
}

export function Note({ children, tone = "muted" }: { children: ReactNode; tone?: "muted" | "warning" | "critical" }) {
  const theme = useTheme();
  const color =
    tone === "critical" ? theme.critical : tone === "warning" ? theme.warning : theme.inkMuted;
  return <Text style={{ color, fontSize: 13, lineHeight: 19 }}>{children}</Text>;
}

export function Loading({ label }: { label?: string }) {
  const theme = useTheme();
  return (
    <View style={{ padding: 24, alignItems: "center", gap: 10 }}>
      <ActivityIndicator color={theme.accent} />
      {label && <Text style={{ color: theme.inkMuted, fontSize: 13 }}>{label}</Text>}
    </View>
  );
}
