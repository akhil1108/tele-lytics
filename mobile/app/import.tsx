import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system";
import { useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView, Text, TextInput, View } from "react-native";

import { Button, Card, Note, Screen, useTheme } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Direction } from "@/lib/types";
import { uploadQueue } from "@/lib/uploadQueue";

/**
 * Import an existing recording.
 *
 * This is the route for fleets whose dialler, carrier or MDM already writes
 * call audio to the handset — the common arrangement where in-app microphone
 * capture is not good enough. The agent picks the file, says who the call was
 * with, and it joins the same upload queue and the same pipeline.
 */
const ACCEPTED = [
  "audio/mp4", "audio/m4a", "audio/x-m4a", "audio/mpeg", "audio/mp3",
  "audio/wav", "audio/x-wav", "audio/ogg", "audio/opus", "audio/amr",
  "audio/3gpp", "audio/aac", "audio/flac",
];

export default function ImportScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { session } = useSession();

  const [file, setFile] = useState<DocumentPicker.DocumentPickerAsset | null>(null);
  const [number, setNumber] = useState("");
  const [direction, setDirection] = useState<Direction>("inbound");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function pick() {
    setError(null);
    const result = await DocumentPicker.getDocumentAsync({
      type: ACCEPTED,
      copyToCacheDirectory: true,
    });
    if (result.canceled || !result.assets?.[0]) return;

    const asset = result.assets[0];
    if (asset.mimeType && !ACCEPTED.includes(asset.mimeType)) {
      setError(`${asset.mimeType} is not an audio format the server accepts.`);
      return;
    }
    setFile(asset);
  }

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const info = await FileSystem.getInfoAsync(file.uri);
      if (!info.exists) throw new Error("That file is no longer available");

      // Recorded earlier, so the start time is unknown; the file's own
      // modification time is the closest honest answer.
      const started = new Date(
        "modificationTime" in info && info.modificationTime
          ? info.modificationTime * 1000
          : Date.now(),
      ).toISOString();

      const call = await api.logCall({
        external_ref: `${session?.device_id ?? "device"}-import-${file.name}-${started}`,
        direction,
        customer_number: number.trim(),
        started_at: started,
        ended_at: new Date().toISOString(),
        status: "completed",
        recording_expected: true,
        metadata: { source: "imported", original_filename: file.name },
      });

      await uploadQueue.enqueue({
        callId: call.id,
        fileUri: file.uri,
        mimeType: file.mimeType ?? "audio/mp4",
        fileName: file.name,
        durationSeconds: null,
        // An imported file carries no record that consent was announced, so it
        // is never claimed. The dashboard shows that honestly.
        consentCaptured: false,
        customerNumber: number.trim(),
        startedAt: started,
      });

      router.replace("/uploads");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not import that file");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView style={{ backgroundColor: theme.page }} keyboardShouldPersistTaps="handled">
      <Screen>
        <Card
          title="Import a call recording"
          subtitle="For recordings your dialler or carrier already saved to this phone"
        >
          <Button label={file ? "Choose a different file" : "Choose a file"} onPress={pick} />
          {file && (
            <Text style={{ color: theme.inkSecondary, fontSize: 13, marginTop: 10 }}>
              {file.name}
              {file.size ? ` · ${(file.size / 1024 / 1024).toFixed(1)} MB` : ""}
            </Text>
          )}

          <TextInput
            value={number}
            onChangeText={setNumber}
            placeholder="Customer number"
            placeholderTextColor={theme.inkMuted}
            keyboardType="phone-pad"
            accessibilityLabel="Customer number"
            style={{
              borderColor: theme.border,
              borderWidth: 1,
              borderRadius: 10,
              padding: 14,
              fontSize: 16,
              marginTop: 14,
              color: theme.ink,
              backgroundColor: theme.surfaceRaised,
            }}
          />

          <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
            {(["inbound", "outbound"] as Direction[]).map((option) => (
              <Button
                key={option}
                label={option === "inbound" ? "They called" : "We called"}
                variant={direction === option ? "primary" : "secondary"}
                onPress={() => setDirection(option)}
                style={{ flex: 1, paddingVertical: 12 }}
              />
            ))}
          </View>

          {error && (
            <View style={{ marginTop: 12 }}>
              <Note tone="critical">{error}</Note>
            </View>
          )}

          <Button
            label="Import and upload"
            variant="primary"
            onPress={submit}
            busy={busy}
            disabled={!file || number.trim().length < 6}
            style={{ marginTop: 16 }}
          />
        </Card>

        <Card style={{ marginTop: 16 }} title="Before importing">
          <Note>
            Only import recordings your organisation is entitled to hold. An imported
            file carries no record that a consent announcement was made, so it is marked
            as such in the dashboard.
          </Note>
        </Card>
      </Screen>
    </ScrollView>
  );
}
