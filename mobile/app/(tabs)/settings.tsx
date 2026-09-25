import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Alert, Platform, ScrollView, Text, View } from "react-native";

import { Button, Card, Note, Row, Screen, useTheme } from "@/components/ui";
import { API_BASE_URL } from "@/lib/config";
import { resetSyncState, syncedCount } from "@/lib/callLogService";
import { importedCount, resetLedger } from "@/lib/importer";
import { permissionStatus, type PermissionState } from "@/lib/permissions";
import { useSession } from "@/lib/session";
import { STATUS_LABEL } from "@/lib/theme";
import { untrackedNumbers, type UntrackedNumber } from "@/lib/untracked";
import { uploadQueue } from "@/lib/uploadQueue";

export default function SettingsScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { session, status, unpair } = useSession();
  const [pendingCount, setPendingCount] = useState(0);
  const [permissions, setPermissions] = useState<PermissionState[]>([]);
  const [untracked, setUntracked] = useState<UntrackedNumber[]>([]);
  const [imported, setImported] = useState(0);
  const [reported, setReported] = useState(0);

  useEffect(() => uploadQueue.subscribe((queue) => setPendingCount(queue.length)), []);
  useEffect(() => untrackedNumbers.subscribe(setUntracked), []);

  useFocusEffect(
    useCallback(() => {
      void permissionStatus().then(setPermissions);
      void importedCount().then(setImported);
      void syncedCount().then(setReported);
    }, []),
  );

  const allowed = permissions.filter((item) => item.granted).length;

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
        </Card>

        <Card
          style={{ marginTop: 16 }}
          title="Permissions"
          subtitle={`${allowed} of ${permissions.length} allowed`}
        >
          {permissions.map((item) => (
            <Row
              key={item.id}
              label={item.title}
              value={item.granted ? "Allowed" : item.optional ? "Not set" : "Not allowed"}
              valueColor={item.granted ? theme.good : item.optional ? undefined : theme.critical}
            />
          ))}
          <Button
            label="Manage permissions"
            onPress={() => router.push("/permissions")}
            style={{ marginTop: 12 }}
          />
        </Card>

        <Card
          style={{ marginTop: 16 }}
          title="Numbers you don't track"
          subtitle="Calls with these numbers are never reported. Mark a number from the Calls tab."
        >
          {untracked.length === 0 ? (
            <Note>None — every number is tracked.</Note>
          ) : (
            untracked.map((entry) => (
              <View
                key={entry.key}
                style={{ flexDirection: "row", alignItems: "center", paddingVertical: 6, gap: 12 }}
              >
                <View style={{ flex: 1 }}>
                  <Text style={{ color: theme.ink, fontSize: 14, fontWeight: "600" }}>
                    {entry.name ?? entry.number}
                  </Text>
                  {entry.name && (
                    <Text style={{ color: theme.inkMuted, fontSize: 12 }}>{entry.number}</Text>
                  )}
                </View>
                <Button
                  label="Track again"
                  onPress={() => void untrackedNumbers.remove(entry.number)}
                  style={{ paddingVertical: 8, paddingHorizontal: 12 }}
                />
              </View>
            ))
          )}
        </Card>

        {Platform.OS === "android" && (
          <Card style={{ marginTop: 16 }} title="Reporting">
            <Row label="Calls reported" value={String(reported)} />
            <Row label="Recordings uploaded" value={String(imported)} />
            <Row label="Uploads waiting" value={String(pendingCount)} />
            <Note>Syncs automatically about every 15 minutes, even with the app closed.</Note>
            {(imported > 0 || reported > 0) && (
              <Button
                label="Report everything again"
                onPress={confirmForgetImports}
                style={{ marginTop: 12 }}
              />
            )}
          </Card>
        )}

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
