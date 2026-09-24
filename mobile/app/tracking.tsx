import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Platform, ScrollView, Text, View } from "react-native";

import { Button, Card, Note, Row, Screen, useTheme } from "@/components/ui";
import {
  callLogEnabled,
  hasPermission as hasCallLogPermission,
  isSupported as callLogSupported,
  requestPermission as requestCallLogPermission,
  syncCallLog,
  syncedCount,
  type SyncReport,
} from "@/lib/callLogService";
import { KNOWN_RECORDING_FOLDERS } from "@/lib/callRecordings";
import { chooseRecordingFolder, recordingFolder } from "@/lib/importer";
import { useSession } from "@/lib/session";

/**
 * Android call tracking.
 *
 * One flow, two layers:
 *
 * * **The call log** reports every call — number, exact duration, direction.
 *   This works on every Android phone and needs no recording support at all.
 * * **A recordings folder**, when the phone's dialler has one, attaches audio
 *   to those calls so they also get a transcript and analysis.
 *
 * The second is optional. A phone that cannot record still reports its full
 * call volume and talk time, which is the point: a dashboard that only knows
 * about recorded calls under-reports the floor's work, and the gap is
 * invisible.
 */
export default function TrackingScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { session } = useSession();

  const [logGranted, setLogGranted] = useState(false);
  const [logEnabled, setLogEnabled] = useState(false);
  const [folder, setFolder] = useState<string | null>(null);
  const [synced, setSynced] = useState(0);
  const [report, setReport] = useState<SyncReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLogGranted(hasCallLogPermission());
    setLogEnabled(await callLogEnabled.get());
    setFolder(await recordingFolder.get());
    setSynced(await syncedCount());
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function enableCallLog() {
    setError(null);
    const granted = await requestCallLogPermission();
    setLogGranted(granted);
    if (granted) {
      await callLogEnabled.set(true);
      setLogEnabled(true);
      await runSync();
    } else {
      setError(
        "Without call log access the app can only report calls it recorded itself.",
      );
    }
  }

  async function pickFolder(seed?: string) {
    setError(null);
    const chosen = await chooseRecordingFolder(seed);
    if (chosen) {
      setFolder(chosen);
      await runSync();
    }
  }

  const runSync = useCallback(async () => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const result = await syncCallLog(session.device_id);
      setReport(result);
      setSynced(await syncedCount());
      if (result.errors.length > 0) setError(result.errors[0]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sync failed");
    } finally {
      setBusy(false);
    }
  }, [session]);

  if (Platform.OS !== "android") {
    return (
      <Screen>
        <Card title="Android only">
          <Note>
            iOS gives apps no access to the call log or to another app&apos;s
            recordings. On iOS, record through this app, or have your telephony
            provider send calls to the server directly.
          </Note>
        </Card>
      </Screen>
    );
  }

  if (!callLogSupported()) {
    return (
      <Screen>
        <Card title="Not available in this build">
          <Note>
            Call log reading needs the full app, not Expo Go. Install the build your
            administrator provided.
          </Note>
        </Card>
      </Screen>
    );
  }

  return (
    <ScrollView style={{ backgroundColor: theme.page }}>
      <Screen>
        {/* Step 1 — the layer every Android phone can do. */}
        <Card
          title="1. Report your calls"
          subtitle="Number, duration and direction for every call — recorded or not"
        >
          {logGranted && logEnabled ? (
            <>
              <Row label="Call log access" value="Granted" valueColor={theme.good} />
              <Row label="Calls reported" value={String(synced)} />
              <Button
                label={busy ? "Syncing…" : "Sync now"}
                variant="primary"
                onPress={runSync}
                busy={busy}
                style={{ marginTop: 12 }}
              />
            </>
          ) : (
            <>
              <Note>
                The app reads your call log to report which calls you handled. It reads
                the number, the time and the duration — not your contacts, and not
                anything about calls outside work hours beyond that.
              </Note>
              <Button
                label="Allow call log access"
                variant="primary"
                onPress={enableCallLog}
                style={{ marginTop: 14 }}
              />
            </>
          )}
        </Card>

        {/* Step 2 — the optional layer. */}
        <Card
          style={{ marginTop: 16 }}
          title="2. Add recordings (optional)"
          subtitle={
            folder
              ? "Recordings are matched to your calls automatically"
              : "Only if your phone's dialler saves call recordings"
          }
        >
          {folder ? (
            <>
              <Row
                label="Folder"
                value={decodeURIComponent(folder).split(":").pop() ?? "Set"}
              />
              <Button
                label="Change folder"
                onPress={() => void pickFolder()}
                style={{ marginTop: 12 }}
              />
            </>
          ) : (
            <>
              <Note>
                Turn on call recording in your phone&apos;s dialler first, then point the
                app at the folder it writes to. Calls with a recording also get a
                transcript and analysis; calls without are still reported.
              </Note>
              <View style={{ marginTop: 14, gap: 8 }}>
                {KNOWN_RECORDING_FOLDERS.slice(0, 5).map((entry) => (
                  <Button
                    key={entry.path}
                    label={`${entry.label} — ${entry.path}`}
                    onPress={() => void pickFolder(entry.path)}
                    style={{ paddingVertical: 11 }}
                  />
                ))}
                <Button
                  label="Browse for the folder"
                  onPress={() => void pickFolder()}
                  style={{ marginTop: 4 }}
                />
              </View>
              <View style={{ marginTop: 14 }}>
                <Note>
                  If your phone cannot record calls, skip this. Step 1 alone reports
                  every call you handle.
                </Note>
              </View>
            </>
          )}
        </Card>

        {error && (
          <View style={{ marginTop: 16 }}>
            <Note tone="warning">{error}</Note>
          </View>
        )}

        {report && <SyncSummary report={report} hasFolder={Boolean(folder)} />}

        <Button
          label="View uploads"
          onPress={() => router.push("/uploads")}
          style={{ marginTop: 20 }}
        />
      </Screen>
    </ScrollView>
  );
}

function SyncSummary({ report, hasFolder }: { report: SyncReport; hasFolder: boolean }) {
  const theme = useTheme();

  if (report.reported === 0 && report.failed === 0) {
    return (
      <Card style={{ marginTop: 16 }} title="Nothing new">
        <Note>Every call on this phone has already been reported.</Note>
      </Card>
    );
  }

  return (
    <Card style={{ marginTop: 16 }} title="Last sync">
      <Row label="Calls reported" value={String(report.reported)} />
      {hasFolder && <Row label="With a recording" value={String(report.withRecording)} />}
      <Row
        label={hasFolder ? "Without a recording" : "Reported without audio"}
        value={String(report.metadataOnly)}
      />

      {report.refusedByPolicy > 0 && (
        <View style={{ marginTop: 12 }}>
          <Note tone="warning">
            {report.refusedByPolicy} recording
            {report.refusedByPolicy === 1 ? " was" : "s were"} not uploaded because your
            organisation&apos;s policy does not allow it. The calls themselves were still
            reported.
          </Note>
        </View>
      )}

      {report.failed > 0 && (
        <View style={{ marginTop: 12 }}>
          <Note tone="critical">
            {report.failed} could not be reported. They will be retried on the next
            sync.
          </Note>
        </View>
      )}

      {(report.skippedUnreportable > 0 || report.skippedNoNumber > 0) && (
        <Text style={{ color: theme.inkMuted, fontSize: 12, marginTop: 12 }}>
          Skipped {report.skippedUnreportable} voicemail or blocked entries
          {report.skippedNoNumber > 0 && ` and ${report.skippedNoNumber} withheld numbers`}.
        </Text>
      )}
    </Card>
  );
}
