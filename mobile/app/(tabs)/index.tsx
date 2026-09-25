import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";

import { Button, Card, Loading, Pill, Screen, Segmented, StatTile, useTheme } from "@/components/ui";
import { api } from "@/lib/api";
import { runSyncCycle } from "@/lib/autoSync";
import { followUps } from "@/lib/followUps";
import { permissionStatus, setupComplete, type PermissionState } from "@/lib/permissions";
import { useSession } from "@/lib/session";
import { STATUS_LABEL, duration, statusColor } from "@/lib/theme";
import type { AgentStatus, DaySummary, PendingUpload, PeriodStats } from "@/lib/types";
import { uploadQueue } from "@/lib/uploadQueue";

const TOGGLES: AgentStatus[] = ["available", "wrap_up", "break", "offline"];
type Period = "today" | "week";

export default function HomeScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { session, status, loading, setStatus } = useSession();
  const [summary, setSummary] = useState<DaySummary | null>(null);
  const [period, setPeriod] = useState<Period>("today");
  const [pending, setPending] = useState<PendingUpload[]>([]);
  const [permissions, setPermissions] = useState<PermissionState[]>([]);
  const [missedToReturn, setMissedToReturn] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => uploadQueue.subscribe(setPending), []);

  useEffect(() => {
    if (!loading && !session) router.replace("/pair");
  }, [loading, session, router]);

  const refresh = useCallback(async () => {
    if (!session) return;
    setRefreshing(true);
    setPermissions(await permissionStatus());

    // Sync first, so the figures below include the call that just ended.
    try {
      await runSyncCycle(session.device_id);
    } catch {
      /* offline: the figures below still load from the last sync */
    }
    try {
      setSummary(await api.summary());
    } catch {
      /* keep whatever was last shown rather than blanking the screen */
    }
    try {
      setMissedToReturn((await followUps()).length);
    } catch {
      /* no call log access; the setup prompt covers it */
    }
    setRefreshing(false);
  }, [session]);

  // Coming back from a call or from setup should show fresh figures.
  useFocusEffect(
    useCallback(() => {
      void refresh();
    }, [refresh]),
  );

  if (loading) return <Loading label="Checking your pairing" />;
  if (!session) return null;

  const missing = permissions.filter((item) => !item.granted && !item.optional).length;
  const stuck = pending.filter((item) => item.lastError !== null).length;
  const stats = summary?.[period] ?? null;

  return (
    <ScrollView
      style={{ backgroundColor: theme.page }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
    >
      <Screen>
        {permissions.length > 0 && !setupComplete(permissions) && (
          <Card
            style={{ marginBottom: 16, borderColor: theme.warning }}
            title="Finish setting up"
            subtitle={`${missing} permission${missing === 1 ? "" : "s"} still needed before your calls are tracked`}
          >
            <Button label="Set up now" variant="primary" onPress={() => router.push("/permissions")} />
          </Card>
        )}

        {missedToReturn > 0 && (
          <Card
            style={{ marginBottom: 16, borderColor: theme.critical }}
            title={`${missedToReturn} missed call${missedToReturn === 1 ? "" : "s"} to return`}
            subtitle="Callers you have not spoken to since they rang"
          >
            <Button label="Call them back" variant="primary" onPress={() => router.push("/calls")} />
          </Card>
        )}

        <Card title={session.agent_name} subtitle={session.organization_name}>
          <Pill label={STATUS_LABEL[status] ?? status} color={statusColor(status, theme)} />
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
            {TOGGLES.map((option) => (
              <Button
                key={option}
                label={STATUS_LABEL[option]}
                variant={status === option ? "primary" : "secondary"}
                onPress={() => void setStatus(option)}
                style={{ flexGrow: 1, minWidth: "45%", paddingVertical: 10 }}
              />
            ))}
          </View>
        </Card>

        <View style={{ marginTop: 20, marginBottom: 10 }}>
          <Segmented
            options={[
              { value: "today", label: "Today" },
              { value: "week", label: "Last 7 days" },
            ]}
            value={period}
            onChange={setPeriod}
          />
        </View>

        {stats ? (
          <StatGrid stats={stats} />
        ) : (
          <Text style={{ color: theme.inkMuted, fontSize: 13, paddingVertical: 12 }}>
            Pull down to load your figures.
          </Text>
        )}

        <Card
          style={{ marginTop: 16 }}
          title="Uploads"
          subtitle={
            pending.length === 0
              ? "All recordings uploaded"
              : `${pending.length} waiting${stuck ? ` · ${stuck} need attention` : ""}`
          }
        >
          <Button
            label={pending.length ? "Review uploads" : "View uploads"}
            onPress={() => router.push("/uploads")}
          />
        </Card>
      </Screen>
    </ScrollView>
  );
}

function StatGrid({ stats }: { stats: PeriodStats }) {
  const theme = useTheme();
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
      <StatTile label="Calls" value={String(stats.calls)} />
      <StatTile label="Talk time" value={duration(stats.talk_seconds)} />
      <StatTile label="Incoming" value={String(stats.inbound)} />
      <StatTile label="Outgoing" value={String(stats.outbound)} />
      <StatTile
        label="Missed"
        value={String(stats.missed)}
        valueColor={stats.missed > 0 ? theme.critical : undefined}
      />
      <StatTile label="Recorded" value={String(stats.recorded)} />
      <StatTile label="Average call" value={duration(stats.avg_call_seconds)} />
      <StatTile
        label="Customer mood"
        value={moodLabel(stats.avg_sentiment)}
        valueColor={moodColor(stats.avg_sentiment, theme)}
      />
    </View>
  );
}

/** Sentiment runs -1..1; an agent reads words faster than decimals. */
function moodLabel(score: number | null): string {
  if (score === null) return "—";
  if (score >= 0.25) return "Positive";
  if (score <= -0.25) return "Negative";
  return "Neutral";
}

function moodColor(score: number | null, theme: ReturnType<typeof useTheme>): string | undefined {
  if (score === null) return undefined;
  if (score >= 0.25) return theme.good;
  if (score <= -0.25) return theme.critical;
  return undefined;
}
