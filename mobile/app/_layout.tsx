import * as Notifications from "expo-notifications";
import { Stack, useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { useColorScheme } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { configureNotifications } from "@/lib/notifications";
import { SessionProvider } from "@/lib/session";
import { dark, light } from "@/lib/theme";

export default function RootLayout() {
  const theme = useColorScheme() === "dark" ? dark : light;
  const router = useRouter();

  // A tapped missed-call reminder opens the Calls tab — including the one that
  // launched the app from cold, which fires before the listener exists.
  useEffect(() => {
    void configureNotifications();
    const open = (response: Notifications.NotificationResponse | null) => {
      if (response?.notification.request.content.data?.route === "/calls") {
        router.push("/calls");
      }
    };
    void Notifications.getLastNotificationResponseAsync().then(open);
    const subscription = Notifications.addNotificationResponseReceivedListener(open);
    return () => subscription.remove();
  }, [router]);

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
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="pair" options={{ title: "Pair this handset", headerBackVisible: false }} />
          <Stack.Screen name="permissions" options={{ title: "Set up" }} />
          <Stack.Screen name="call" options={{ title: "Record a call" }} />
          <Stack.Screen name="uploads" options={{ title: "Uploads" }} />
        </Stack>
      </SessionProvider>
    </SafeAreaProvider>
  );
}
