import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";

import { Button, Card, Loading, Pill, Row, Screen, useTheme } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { STATUS_LABEL, duration, statusColor } from "@/lib/theme";
import type { AgentStatus, DaySummary } from "@/lib/types";
import { uploadQueue } from "@/lib/uploadQueue";
import type { PendingUpload } from "@/lib/types";

const TOGGLES: AgentStatus[] = ["available", "wrap_up", "break", "offline"];

export default function HomeScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { session, status, loading, setStatus } = useSession();
  const [summary, setSummary] = useState<DaySummary | null>(null);
  const [pending, setPending] = useState<PendingUpload[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => uploadQueue.subscribe(setPending), []);

  useEffect(() => {
    if (!loading && !session) router.replace("/pair");
  }, [loading, session, router]);

  const refresh = useCallback(async () => {
    if (!session) return;
    setRefreshing(true);
    try {
      setSummary(await api.summary());
    } catch {
      /* offline: keep whatever was last shown rather than blanking the screen */
    } finally {
      setRefreshing(false);
    }
  }, [session]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (loading) return <Loading label="Checking your pairing" />;
  if (!session) return null;

  const stuck = pending.filter((item) => item.lastError !== null).length;

  return (
    <ScrollView
      style={{ backgroundColor: theme.page }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
    >
      <Screen>
        <Card title={session.agent_name} subtitle={session.agent_number}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Pill label={STATUS_LABEL[status] ?? status} color={statusColor(status, theme)} />
            <Text style={{ color: theme.inkMuted, fontSize: 12 }}>
              {session.organization_name}
            </Text>
          </View>

          <Text style={{ color: theme.inkMuted, fontSize: 12, marginTop: 14 }}>
            Set your status
          </Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
            {TOGGLES.map((option) => (
              <Button
                key={option}
                label={STATUS_LABEL[option]}
                variant={status === option ? "primary" : "secondary"}
                onPress={() => void setStatus(option)}
                style={{ flexGrow: 1, minWidth: "45%", paddingVertical: 12 }}
              />
            ))}
          </View>
        </Card>

        <Button
          label="Record a call"
          variant="primary"
          onPress={() => router.push("/call")}
          style={{ marginTop: 16 }}
        />

        <Card style={{ marginTop: 16 }} title="Today">
          {summary ? (
            <>
              <Row label="Calls" value={String(summary.calls_today)} />
              <Row label="Talk time" value={duration(summary.talk_seconds_today)} />
              <Row label="Recorded" value={String(summary.recorded_today)} />
              <Row
                label="Average sentiment"
                value={
                  summary.avg_sentiment_today === null
                    ? "—"
                    : summary.avg_sentiment_today.toFixed(2)
                }
              />
            </>
          ) : (
            <Text style={{ color: theme.inkMuted, fontSize: 13 }}>
              Pull down to load today&apos;s figures.
            </Text>
          )}
        </Card>

        <Card
          style={{ marginTop: 16 }}
          title="Uploads"
          subtitle={
            pending.length === 0
              ? "Everything has been uploaded"
              : `${pending.length} waiting${stuck ? ` · ${stuck} need attention` : ""}`
          }
        >
          <Button
            label={pending.length ? "Review uploads" : "View history"}
            onPress={() => router.push("/uploads")}
          />
        </Card>

        <View style={{ flexDirection: "row", gap: 12, marginTop: 16 }}>
          <Button
            label="Import a recording"
            onPress={() => router.push("/import")}
            style={{ flex: 1 }}
          />
          <Button
            label="Settings"
            onPress={() => router.push("/settings")}
            style={{ flex: 1 }}
          />
        </View>
      </Screen>
    </ScrollView>
  );
}
