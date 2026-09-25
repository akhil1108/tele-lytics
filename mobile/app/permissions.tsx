import Ionicons from "@expo/vector-icons/Ionicons";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { Linking, Platform, ScrollView, Text, View } from "react-native";

import { Button, Card, Note, Screen, useTheme } from "@/components/ui";
import { runSyncCycle } from "@/lib/autoSync";
import { KNOWN_RECORDING_FOLDERS } from "@/lib/callRecordings";
import { chooseRecordingFolder } from "@/lib/importer";
import {
  permissionStatus,
  requestAll,
  requestOne,
  setupComplete,
  type PermissionState,
} from "@/lib/permissions";
import { useSession } from "@/lib/session";

/**
 * Setup: every permission the app needs, on one screen, with one button.
 *
 * Reached straight after pairing and from the home screen whenever something
 * is still missing. A permission the agent refused twice can only be turned on
 * from system settings, so that is offered as the fallback.
 */
export default function PermissionsScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { session } = useSession();
  const [states, setStates] = useState<PermissionState[]>([]);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState(false);

  const refresh = useCallback(async () => {
    setStates(await permissionStatus());
  }, []);

  useFocusEffect(
    useCallback(() => {
      void refresh();
    }, [refresh]),
  );

  async function afterChange(next: PermissionState[]) {
    setStates(next);
    // Report the backlog as soon as there is something to report it with.
    if (session) void runSyncCycle(session.device_id).catch(() => {});
  }

  async function grantAll() {
    setBusy(true);
    try {
      const next = await requestAll();
      setRefused(!setupComplete(next));
      await afterChange(next);
    } finally {
      setBusy(false);
    }
  }

  async function grant(item: PermissionState) {
    if (item.id === "folder") return;
    const ok = await requestOne(item.id);
    if (!ok) setRefused(true);
    await afterChange(await permissionStatus());
  }

  async function pickFolder(seed?: string) {
    const chosen = await chooseRecordingFolder(seed);
    if (chosen) await afterChange(await permissionStatus());
  }

  const done = states.length > 0 && setupComplete(states);
  const folder = states.find((item) => item.id === "folder");

  return (
    <ScrollView style={{ backgroundColor: theme.page }}>
      <Screen>
        <Card
          title={done ? "You're all set" : "Allow access"}
          subtitle={
            done
              ? "Your calls are tracked and missed calls will remind you"
              : "The app needs these to track your calls"
          }
        >
          {states
            .filter((item) => item.id !== "folder")
            .map((item) => (
              <PermissionRow key={item.id} item={item} onGrant={() => void grant(item)} />
            ))}
          {!done && refused && (
            <View style={{ marginTop: 14 }}>
              {/* Android stops showing the dialog after two refusals. */}
              <Note tone="warning">
                If nothing pops up, turn the permission on in your phone&apos;s settings.
              </Note>
              <Button
                label="Open phone settings"
                onPress={() => void Linking.openSettings()}
                style={{ marginTop: 10 }}
              />
            </View>
          )}
          {!done && (
            <Button
              label="Allow all"
              variant="primary"
              busy={busy}
              onPress={() => void grantAll()}
              style={{ marginTop: 14 }}
            />
          )}
        </Card>

        {folder && (
          <Card
            style={{ marginTop: 16 }}
            title="Call recordings (file access)"
            subtitle={
              folder.granted
                ? "Recordings are picked up and uploaded automatically"
                : "Only if your phone's dialler saves call recordings"
            }
          >
            {folder.granted ? (
              <Button label="Change folder" onPress={() => void pickFolder()} />
            ) : (
              <>
                <Note>
                  Turn on call recording in your phone&apos;s dialler, then choose the
                  folder it saves to. Calls with a recording get a transcript and
                  analysis; calls without are still counted.
                </Note>
                <View style={{ marginTop: 14, gap: 8 }}>
                  {KNOWN_RECORDING_FOLDERS.slice(0, 4).map((entry) => (
                    <Button
                      key={entry.path}
                      label={entry.label}
                      onPress={() => void pickFolder(entry.path)}
                      style={{ paddingVertical: 11 }}
                    />
                  ))}
                  <Button label="Browse for the folder" onPress={() => void pickFolder()} />
                </View>
              </>
            )}
          </Card>
        )}

        {Platform.OS === "android" && (
          <View style={{ marginTop: 16 }}>
            <Note>
              Android does not let apps record the phone call itself. The app uses the
              recordings your dialler already saves, or you can record on speaker from
              the Calls tab.
            </Note>
          </View>
        )}

        <Button
          label={done ? "Done" : "Skip for now"}
          variant={done ? "primary" : "secondary"}
          onPress={() => router.replace("/")}
          style={{ marginTop: 20 }}
        />
      </Screen>
    </ScrollView>
  );
}

function PermissionRow({ item, onGrant }: { item: PermissionState; onGrant: () => void }) {
  const theme = useTheme();
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: 12,
        paddingVertical: 10,
        borderBottomColor: theme.border,
        borderBottomWidth: 1,
      }}
    >
      <Ionicons
        name={item.granted ? "checkmark-circle" : "ellipse-outline"}
        size={22}
        color={item.granted ? theme.good : theme.inkMuted}
      />
      <View style={{ flex: 1 }}>
        <Text style={{ color: theme.ink, fontSize: 14, fontWeight: "600" }}>{item.title}</Text>
        <Text style={{ color: theme.inkMuted, fontSize: 12, marginTop: 2 }}>{item.why}</Text>
      </View>
      {!item.granted && (
        <Button label="Allow" onPress={onGrant} style={{ paddingVertical: 8, paddingHorizontal: 12 }} />
      )}
    </View>
  );
}
