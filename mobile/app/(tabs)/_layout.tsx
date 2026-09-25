import Ionicons from "@expo/vector-icons/Ionicons";
import { Tabs } from "expo-router";
import type { ComponentProps } from "react";

import { useTheme } from "@/components/ui";

type IconName = ComponentProps<typeof Ionicons>["name"];

function icon(name: IconName) {
  return ({ color, size }: { color: string; size: number }) => (
    <Ionicons name={name} color={color} size={size} />
  );
}

/** Three tabs, and that is the whole app: today, your calls, setup. */
export default function TabsLayout() {
  const theme = useTheme();
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: theme.surface },
        headerTintColor: theme.ink,
        headerTitleStyle: { fontSize: 16, fontWeight: "600" },
        tabBarStyle: { backgroundColor: theme.surface, borderTopColor: theme.border },
        tabBarActiveTintColor: theme.accent,
        tabBarInactiveTintColor: theme.inkMuted,
      }}
      sceneContainerStyle={{ backgroundColor: theme.page }}
    >
      <Tabs.Screen name="index" options={{ title: "Home", tabBarIcon: icon("stats-chart") }} />
      <Tabs.Screen name="calls" options={{ title: "Calls", tabBarIcon: icon("call") }} />
      <Tabs.Screen name="settings" options={{ title: "Settings", tabBarIcon: icon("settings") }} />
    </Tabs>
  );
}
