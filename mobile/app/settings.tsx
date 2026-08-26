import { useEffect, useState } from "react";
import { Alert, Platform, ScrollView, Text, View } from "react-native";

import { Button, Card, Note, Row, Screen, useTheme } from "@/components/ui";
import { API_BASE_URL } from "@/lib/config";
import {
  hasPermission as hasCallLogPermission,
  isSupported as callLogSupported,
  resetSyncState,
  syncedCount,
} from "@/lib/callLogService";
import { importedCount, recordingFolder, resetLedger } from "@/lib/importer";
import { CallRecorder } from "@/lib/recorder";
import { useSession } from "@/lib/session";
import { STATUS_LABEL } from "@/lib/theme";
import { uploadQueue } from "@/lib/uploadQueue";

export default function SettingsScreen() {
  const theme = useTheme();
  const { session, status, unpair } = useSession();
  const [micGranted, setMicGranted] = useState<boolean | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [folder, setFolder] = useState<string | null>(null);
  const [imported, setImported] = useState(0);
  const [reported, setReported] = useState(0);
  const [logGranted, setLogGranted] = useState(false);

  useEffect(() => {
    void CallRecorder.hasPermission().then(setMicGranted);
    void recordingFolder.get().then(setFolder);
    void importedCount().then(setImported);
    void syncedCount().then(setReported);
    setLogGranted(callLogSupported() && hasCallLogPermission());
    return uploadQueue.subscribe((queue) => setPendingCount(queue.length));
  }, []);

  function confirmForgetImports() {
    Alert.alert(
      "Report every call again?",
      "The app remembers which calls and recordings it has already sent, so a " +
        "sync never reports the same call twice. Clearing that will offer them " +
        "all again — useful if a batch was filed wrongly, but it can create " +
        "duplicates otherwise.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Clear",
          style: "destructive",
          onPress: () => {
            void Promise.all([resetLedger(), resetSyncState()]).then(() => {
              setImported(0);
              setReported(0);
            });
          },
        },
      ],
    );
  }

  function confirmUnpair() {
    // Unpairing with recordings still queued loses them, so say so plainly.
    const warning =
      pendingCount > 0
        ? `${pendingCount} recording${pendingCount === 1 ? "" : "s"} on this handset have not been uploaded yet. Unpairing means they can never be uploaded.`
        : "You will need a new pairing code from your supervisor to use this handset again.";

    Alert.alert("Unpair this handset?", warning, [
      { text: "Cancel", style: "cancel" },
      { text: "Unpair", style: "destructive", onPress: () => void unpair() },
    ]);
  }

  return (
    <ScrollView style={{ backgroundColor: theme.page }}>
      <Screen>
        <Card title="This handset">
          <Row label="Agent" value={session?.agent_name ?? "—"} />
          <Row label="Number" value={session?.agent_number ?? "—"} />
          <Row label="Organisation" value={session?.organization_name ?? "—"} />
          <Row label="Status" value={STATUS_LABEL[status] ?? status} />
          <Row label="Uploads waiting" value={String(pendingCount)} />
        </Card>

        <Card style={{ marginTop: 16 }} title="Permissions">
          <Row
            label="Microphone"
            value={micGranted === null ? "…" : micGranted ? "Granted" : "Not granted"}
            valueColor={micGranted === false ? theme.critical : undefined}
          />
          {micGranted === false && (
            <Button
              label="Grant microphone access"
              onPress={() => void CallRecorder.requestPermission().then(setMicGranted)}
              style={{ marginTop: 12 }}
            />
          )}
        </Card>

        {Platform.OS === "android" && (
          <Card style={{ marginTop: 16 }} title="Call tracking">
            <Row
              label="Call log access"
              value={logGranted ? "Granted" : "Not granted"}
              valueColor={logGranted ? undefined : theme.warning}
            />
            <Row label="Calls reported" value={String(reported)} />
            <Row
              label="Recordings folder"
              value={folder ? (decodeURIComponent(folder).split(":").pop() ?? "Set") : "Not set"}
            />
            <Row label="Recordings uploaded" value={String(imported)} />
            {(imported > 0 || reported > 0) && (
              <Button
                label="Report everything again"
                onPress={confirmForgetImports}
                style={{ marginTop: 12 }}
              />
            )}
          </Card>
        )}

        <Card style={{ marginTop: 16 }} title="How recording works">
          <Note>
            Neither Android nor iOS lets an app record the carrier call itself — that
            needs a system-level permission Google and Apple do not grant to normal
            apps.
            {"\n\n"}
            On Android this app reports every call from your call log — the number,
            when it happened and how long it lasted — whether or not there was a
            recording. If your phone&apos;s dialler saves recordings, pointing the app at
            that folder adds transcripts and analysis on top. In-app recording captures
            the microphone instead, so put the call on speaker if you use it.
          </Note>
        </Card>

        <Card style={{ marginTop: 16 }} title="Server">
          <Text style={{ color: theme.inkSecondary, fontSize: 13 }}>{API_BASE_URL}</Text>
        </Card>

        <Button
          label="Unpair this handset"
          variant="danger"
          onPress={confirmUnpair}
          style={{ marginTop: 24 }}
        />

        <View style={{ marginTop: 16 }}>
          <Note>
            Unpairing revokes this handset&apos;s access. Your call history stays in the
            dashboard.
          </Note>
        </View>
      </Screen>
    </ScrollView>
  );
}
