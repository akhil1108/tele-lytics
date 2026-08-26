import { useEffect, useState } from "react";
import { Alert, Platform, ScrollView, Text, View } from "react-native";

import { Button, Card, Note, Row, Screen, useTheme } from "@/components/ui";
import { API_BASE_URL } from "@/lib/config";
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

  useEffect(() => {
    void CallRecorder.hasPermission().then(setMicGranted);
    void recordingFolder.get().then(setFolder);
    void importedCount().then(setImported);
    return uploadQueue.subscribe((queue) => setPendingCount(queue.length));
  }, []);

  function confirmForgetImports() {
    Alert.alert(
      "Offer every recording again?",
      "The app remembers which files it has already imported so a scan never " +
        "uploads the same call twice. Clearing that will offer all of them again — " +
        "useful if some were filed against the wrong number, but it can create " +
        "duplicates otherwise.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Clear",
          style: "destructive",
          onPress: () => {
            void resetLedger().then(() => setImported(0));
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
          <Card style={{ marginTop: 16 }} title="Recording import">
            <Row
              label="Folder"
              value={folder ? (decodeURIComponent(folder).split(":").pop() ?? "Set") : "Not set"}
              valueColor={folder ? undefined : theme.warning}
            />
            <Row label="Files already imported" value={String(imported)} />
            {imported > 0 && (
              <Button
                label="Offer every recording again"
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
            On Android the reliable route is to turn on call recording in your phone&apos;s
            own dialler and let this app import from the folder it writes to. In-app
            recording captures the microphone instead, so put the call on speaker if you
            use it.
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
