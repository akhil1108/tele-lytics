import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useColorScheme } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { SessionProvider } from "@/lib/session";
import { dark, light } from "@/lib/theme";

export default function RootLayout() {
  const theme = useColorScheme() === "dark" ? dark : light;

  return (
    <SafeAreaProvider>
      <SessionProvider>
        <StatusBar style="auto" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: theme.surface },
            headerTintColor: theme.ink,
            headerTitleStyle: { fontSize: 16, fontWeight: "600" },
            contentStyle: { backgroundColor: theme.page },
          }}
        >
          <Stack.Screen name="index" options={{ title: "Today" }} />
          <Stack.Screen name="pair" options={{ title: "Pair this handset", headerBackVisible: false }} />
          <Stack.Screen name="call" options={{ title: "Record a call" }} />
          <Stack.Screen name="uploads" options={{ title: "Uploads" }} />
          <Stack.Screen name="tracking" options={{ title: "Call tracking" }} />
          <Stack.Screen name="settings" options={{ title: "Settings" }} />
        </Stack>
      </SessionProvider>
    </SafeAreaProvider>
  );
}
