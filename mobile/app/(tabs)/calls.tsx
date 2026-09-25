import Ionicons from "@expo/vector-icons/Ionicons";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState, type ReactNode } from "react";
import { Alert, FlatList, Linking, Pressable, RefreshControl, Text, View } from "react-native";

import { Button, Card, Note, Screen, useTheme } from "@/components/ui";
import type { FollowUp } from "@/lib/callInsights";
import {
  dismissFollowUp,
  followUps as loadFollowUps,
  isSupported as callLogReadable,
  recentCalls,
  RECENT_WINDOW_DAYS,
  type RecentCall,
} from "@/lib/followUps";
import { duration } from "@/lib/theme";
import { untrackedNumbers } from "@/lib/untracked";

/**
 * The agent's calls from the last week, with the missed ones that still need a
 * call back pinned on top.
 *
 * Every row can be switched between tracked and not tracked. Untracked numbers
 * are never reported and their recordings never leave the phone.
 */
export default function CallsScreen() {
  const theme = useTheme();
  const router = useRouter();
  const [calls, setCalls] = useState<RecentCall[]>([]);
  const [pending, setPending] = useState<FollowUp[]>([]);
  const [readable, setReadable] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    const canRead = callLogReadable();
    setReadable(canRead);
    if (canRead) {
      try {
        const [recent, open] = await Promise.all([recentCalls(), loadFollowUps()]);
        setCalls(recent);
        setPending(open);
      } catch {
        /* keep the last list */
      }
    }
    setRefreshing(false);
  }, []);

  useFocusEffect(
    useCallback(() => {
      void refresh();
    }, [refresh]),
  );

  function callBack(number: string) {
    void Linking.openURL(`tel:${number.replace(/[^\d+]/g, "")}`);
  }

  async function markDone(followUp: FollowUp) {
    await dismissFollowUp(followUp);
    setPending((current) => current.filter((item) => item !== followUp));
  }

  function openActions(call: RecentCall) {
    const who = call.name ?? call.number;
    Alert.alert(who, call.name ? call.number : undefined, [
      { text: "Call back", onPress: () => callBack(call.number) },
      call.untracked
        ? {
            text: "Track this number",
            onPress: () => void untrackedNumbers.remove(call.number).then(refresh),
          }
        : {
            text: "Don't track this number",
            style: "destructive",
            onPress: () => confirmUntrack(call),
          },
      { text: "Cancel", style: "cancel" },
    ]);
  }

  function confirmUntrack(call: RecentCall) {
    Alert.alert(
      "Stop tracking this number?",
      "Future calls with this number will not be reported and their recordings will " +
        "stay on your phone. Calls already reported stay in the dashboard.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Don't track",
          style: "destructive",
          onPress: () => void untrackedNumbers.add(call.number, call.name).then(refresh),
        },
      ],
    );
  }

  if (!readable) {
    return (
      <Screen>
        <Card title="Call log access needed">
          <Note>
            Allow call log access to see your calls and the missed ones to follow up.
          </Note>
          <Button
            label="Set up"
            variant="primary"
            onPress={() => router.push("/permissions")}
            style={{ marginTop: 14 }}
          />
        </Card>
        <Button
          label="Record a call in the app"
          onPress={() => router.push("/call")}
          style={{ marginTop: 16 }}
        />
      </Screen>
    );
  }

  return (
    <FlatList
      style={{ backgroundColor: theme.page }}
      contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
      data={calls}
      keyExtractor={(item) => item.id}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      ListHeaderComponent={
        <View style={{ marginBottom: 12 }}>
          {pending.length > 0 && (
            <>
              <SectionTitle>To call back ({pending.length})</SectionTitle>
              {pending.map((followUp) => (
                <FollowUpCard
                  key={followUp.key}
                  followUp={followUp}
                  onCall={() => callBack(followUp.number)}
                  onDone={() => void markDone(followUp)}
                />
              ))}
            </>
          )}
          <Button
            label="Record a call in the app"
            onPress={() => router.push("/call")}
            style={{ marginTop: pending.length ? 8 : 0, marginBottom: 16 }}
          />
          <SectionTitle>Last {RECENT_WINDOW_DAYS} days</SectionTitle>
        </View>
      }
      ListEmptyComponent={
        <Note>No calls in the last {RECENT_WINDOW_DAYS} days.</Note>
      }
      renderItem={({ item }) => <CallRow call={item} onPress={() => openActions(item)} />}
      ItemSeparatorComponent={() => (
        <View style={{ height: 1, backgroundColor: theme.border }} />
      )}
    />
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  const theme = useTheme();
  return (
    <Text
      style={{
        color: theme.inkMuted,
        fontSize: 12,
        fontWeight: "600",
        textTransform: "uppercase",
        letterSpacing: 0.5,
        marginBottom: 8,
      }}
    >
      {children}
    </Text>
  );
}

function FollowUpCard({
  followUp,
  onCall,
  onDone,
}: {
  followUp: FollowUp;
  onCall: () => void;
  onDone: () => void;
}) {
  const theme = useTheme();
  const detail = [
    followUp.missedCount > 1 ? `${followUp.missedCount} missed calls` : "Missed call",
    whenLabel(followUp.lastMissedAt),
  ].join(" · ");

  return (
    <Card
      style={{ marginBottom: 10, borderColor: theme.critical }}
      title={followUp.name ?? followUp.number}
      subtitle={followUp.name ? `${followUp.number} · ${sourceLabel(followUp.nameSource)}` : undefined}
    >
      <Text style={{ color: theme.inkSecondary, fontSize: 13 }}>{detail}</Text>
      {followUp.lastAttemptAt && (
        <Text style={{ color: theme.inkMuted, fontSize: 12, marginTop: 4 }}>
          You tried calling {whenLabel(followUp.lastAttemptAt)} — no answer
        </Text>
      )}
      <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
        <Button label="Call back" variant="primary" onPress={onCall} style={{ flex: 1 }} />
        <Button label="Done" onPress={onDone} style={{ flex: 1 }} />
      </View>
    </Card>
  );
}

const TYPE_ICON: Record<string, { name: keyof typeof Ionicons.glyphMap; tone: "ink" | "critical" | "muted" }> = {
  incoming: { name: "arrow-down", tone: "ink" },
  outgoing: { name: "arrow-up", tone: "ink" },
  missed: { name: "close", tone: "critical" },
  rejected: { name: "remove-circle-outline", tone: "muted" },
  blocked: { name: "ban", tone: "muted" },
  voicemail: { name: "recording-outline", tone: "muted" },
  unknown: { name: "help", tone: "muted" },
};

function CallRow({ call, onPress }: { call: RecentCall; onPress: () => void }) {
  const theme = useTheme();
  const icon = TYPE_ICON[call.type] ?? TYPE_ICON.unknown;
  const iconColor =
    icon.tone === "critical" ? theme.critical : icon.tone === "muted" ? theme.inkMuted : theme.ink;

  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => ({
        flexDirection: "row",
        alignItems: "center",
        gap: 12,
        paddingVertical: 12,
        opacity: pressed ? 0.7 : 1,
      })}
    >
      <Ionicons name={icon.name} size={18} color={iconColor} />
      <View style={{ flex: 1 }}>
        <Text
          style={{ color: call.untracked ? theme.inkMuted : theme.ink, fontSize: 15, fontWeight: "600" }}
          numberOfLines={1}
        >
          {call.name ?? call.number}
        </Text>
        <Text style={{ color: theme.inkMuted, fontSize: 12, marginTop: 2 }} numberOfLines={1}>
          {[
            call.name ? call.number : null,
            call.nameSource === "caller_id" ? "Caller ID" : null,
            whenLabel(call.startedAt),
            call.durationSeconds > 0 ? duration(call.durationSeconds) : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </Text>
      </View>
      {call.untracked ? (
        <Text style={{ color: theme.inkMuted, fontSize: 11, fontWeight: "600" }}>NOT TRACKED</Text>
      ) : (
        <Ionicons name="ellipsis-vertical" size={16} color={theme.inkMuted} />
      )}
    </Pressable>
  );
}

function sourceLabel(source: FollowUp["nameSource"]): string {
  return source === "contact" ? "Contact" : "Caller ID";
}

/** "10:42", "Yesterday 18:05" or "Mon 09:12" — short enough for one line. */
function whenLabel(date: Date): string {
  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const today = new Date();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  if (date.getTime() >= startOfToday) return time;
  if (date.getTime() >= startOfToday - 86_400_000) return `Yesterday ${time}`;
  return `${date.toLocaleDateString([], { weekday: "short" })} ${time}`;
}
