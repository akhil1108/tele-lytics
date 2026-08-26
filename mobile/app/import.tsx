import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Platform, ScrollView, Text, TextInput, View } from "react-native";

import { Button, Card, Note, Pill, Screen, useTheme } from "@/components/ui";
import { KNOWN_RECORDING_FOLDERS } from "@/lib/callRecordings";
import {
  chooseRecordingFolder,
  defaultDirection,
  importAll,
  importRecording,
  recordingFolder,
  scanRecordingFolder,
  type DetectedRecording,
  type ImportOutcome,
  type ScanResult,
} from "@/lib/importer";
import { useSession } from "@/lib/session";
import { policyReason } from "@/lib/theme";
import type { Direction } from "@/lib/types";

/**
 * Import recordings the phone's own dialler made.
 *
 * The agent turns on call recording in their phone app and grants this folder
 * once; from then on a scan finds every new call, reads the number and time out
 * of the filename, and files them.
 *
 * Files whose number could not be read are listed separately with a field to
 * type it in. They are never guessed at — a call filed against the wrong
 * customer is worse than one the agent had to label.
 */
export default function ImportScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { session } = useSession();

  const [folder, setFolder] = useState<string | null>(null);
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [fallback, setFallback] = useState<Direction>("unknown");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<ImportOutcome[] | null>(null);

  useEffect(() => {
    void recordingFolder.get().then(setFolder);
    void defaultDirection.get().then(setFallback);
  }, []);

  const runScan = useCallback(async () => {
    setBusy(true);
    setError(null);
    setOutcomes(null);
    try {
      const result = await scanRecordingFolder();
      setScan(result);
      if (result && result.detected.length === 0) {
        setError(null);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not read the folder");
      setFolder(null);
      setScan(null);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (folder) void runScan();
  }, [folder, runScan]);

  async function pickFolder(seed?: string) {
    setError(null);
    const chosen = await chooseRecordingFolder(seed);
    if (chosen) setFolder(chosen);
  }

  async function importOne(item: DetectedRecording) {
    if (!session) return;
    setBusy(true);
    const outcome = await importRecording(item, {
      numberOverride: overrides[item.fileName],
      deviceId: session.device_id,
      fallbackDirection: fallback,
    });
    setOutcomes([outcome]);
    setBusy(false);
    if (outcome.ok) await runScan();
  }

  async function importReady() {
    if (!session || !scan) return;
    const ready = scan.detected.filter(
      (item) => !item.needsNumber || (overrides[item.fileName] ?? "").trim().length >= 6,
    );
    if (ready.length === 0) return;

    setBusy(true);
    const results = await importAll(
      ready.map((item) => ({
        item,
        numberOverride: item.parsed.customerNumber
          ? undefined
          : overrides[item.fileName]?.trim(),
      })),
      { deviceId: session.device_id, fallbackDirection: fallback },
    );
    setOutcomes(results);
    setBusy(false);
    await runScan();
  }

  if (Platform.OS !== "android") {
    return (
      <Screen>
        <Card title="Android only">
          <Note>
            iOS does not let an app read another app&apos;s recordings, and it has no
            call-recording API of its own. On iOS, record through this app instead, or
            have your telephony provider send recordings to the server directly.
          </Note>
        </Card>
      </Screen>
    );
  }

  const readyCount =
    scan?.detected.filter(
      (item) => !item.needsNumber || (overrides[item.fileName] ?? "").trim().length >= 6,
    ).length ?? 0;

  return (
    <ScrollView style={{ backgroundColor: theme.page }} keyboardShouldPersistTaps="handled">
      <Screen>
        {!folder ? (
          <Card
            title="Choose your recordings folder"
            subtitle="Where your phone app saves call recordings. You only do this once."
          >
            <Note>
              Turn on call recording in your phone&apos;s dialler first, then point this
              app at the folder it writes to. Pick the one that matches your phone, or
              browse for it.
            </Note>
            <View style={{ marginTop: 14, gap: 8 }}>
              {KNOWN_RECORDING_FOLDERS.slice(0, 6).map((entry) => (
                <Button
                  key={entry.path}
                  label={`${entry.label} — ${entry.path}`}
                  onPress={() => void pickFolder(entry.path)}
                  style={{ paddingVertical: 11 }}
                />
              ))}
              <Button
                label="Browse for the folder"
                variant="primary"
                onPress={() => void pickFolder()}
                style={{ marginTop: 4 }}
              />
            </View>
          </Card>
        ) : (
          <>
            <Card
              title="Recordings folder"
              subtitle={decodeURIComponent(folder).split(":").pop() ?? folder}
            >
              <View style={{ flexDirection: "row", gap: 10 }}>
                <Button
                  label={busy ? "Scanning…" : "Scan for new calls"}
                  variant="primary"
                  onPress={runScan}
                  busy={busy}
                  style={{ flex: 1 }}
                />
                <Button
                  label="Change"
                  onPress={() => void pickFolder()}
                  style={{ flex: 0, paddingHorizontal: 20 }}
                />
              </View>

              {scan && (
                <Text style={{ color: theme.inkMuted, fontSize: 12, marginTop: 12 }}>
                  {scan.detected.length} new ·{" "}
                  {scan.skippedAlreadyImported} already imported
                  {scan.skippedNotAudio > 0 && ` · ${scan.skippedNotAudio} not audio`}
                </Text>
              )}
            </Card>

            <Card style={{ marginTop: 16 }} title="When the filename does not say">
              <Note>
                Most phone recorders do not record whether a call was incoming or
                outgoing. Choose what to assume — or leave it unset, which is recorded
                honestly as unknown rather than guessed.
              </Note>
              <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
                {(["unknown", "inbound", "outbound"] as Direction[]).map((option) => (
                  <Button
                    key={option}
                    label={
                      option === "unknown"
                        ? "Leave unknown"
                        : option === "inbound"
                          ? "Incoming"
                          : "Outgoing"
                    }
                    variant={fallback === option ? "primary" : "secondary"}
                    onPress={() => {
                      setFallback(option);
                      void defaultDirection.set(option);
                    }}
                    style={{ flex: 1, paddingVertical: 11 }}
                  />
                ))}
              </View>
            </Card>
          </>
        )}

        {error && (
          <View style={{ marginTop: 16 }}>
            <Note tone="critical">{error}</Note>
          </View>
        )}

        {outcomes && <OutcomeSummary outcomes={outcomes} />}

        {scan && scan.detected.length === 0 && !busy && (
          <Card style={{ marginTop: 16 }} title="Nothing new">
            <Note>
              Every recording in that folder has already been imported. New calls will
              appear here after you record them.
            </Note>
          </Card>
        )}

        {scan && scan.detected.length > 0 && (
          <>
            <Card
              style={{ marginTop: 16 }}
              title={`${scan.detected.length} recording${scan.detected.length === 1 ? "" : "s"} found`}
              subtitle={
                readyCount === scan.detected.length
                  ? "All read successfully"
                  : `${readyCount} ready · ${scan.detected.length - readyCount} need a number`
              }
            >
              <Button
                label={`Import ${readyCount} recording${readyCount === 1 ? "" : "s"}`}
                variant="primary"
                onPress={importReady}
                busy={busy}
                disabled={readyCount === 0}
              />
            </Card>

            {scan.detected.map((item) => (
              <DetectedRow
                key={item.fileName}
                item={item}
                override={overrides[item.fileName] ?? ""}
                onOverride={(value) =>
                  setOverrides((current) => ({ ...current, [item.fileName]: value }))
                }
                onImport={() => void importOne(item)}
                busy={busy}
              />
            ))}
          </>
        )}

        <Button
          label="View uploads"
          onPress={() => router.push("/uploads")}
          style={{ marginTop: 20 }}
        />
      </Screen>
    </ScrollView>
  );
}

function DetectedRow({
  item,
  override,
  onOverride,
  onImport,
  busy,
}: {
  item: DetectedRecording;
  override: string;
  onOverride: (value: string) => void;
  onImport: () => void;
  busy: boolean;
}) {
  const theme = useTheme();
  const { parsed } = item;
  const canImport = !item.needsNumber || override.trim().length >= 6;

  return (
    <Card style={{ marginTop: 12 }}>
      <Text style={{ color: theme.ink, fontSize: 14, fontWeight: "600" }} numberOfLines={1}>
        {parsed.customerNumber ?? parsed.contactName ?? "Unknown caller"}
      </Text>
      <Text style={{ color: theme.inkMuted, fontSize: 11, marginTop: 2 }} numberOfLines={1}>
        {item.fileName}
      </Text>

      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
        {parsed.recordedAt ? (
          <Pill label={parsed.recordedAt.toLocaleString()} />
        ) : (
          <Pill label="No time in filename" color={theme.warning} />
        )}
        {parsed.direction !== "unknown" && (
          <Pill label={parsed.direction === "inbound" ? "Incoming" : "Outgoing"} />
        )}
        {item.sizeBytes !== null && (
          <Pill label={`${(item.sizeBytes / 1024 / 1024).toFixed(1)} MB`} />
        )}
      </View>

      {item.needsNumber && (
        <View style={{ marginTop: 12 }}>
          <Note tone="warning">
            {parsed.contactName
              ? `Your phone saved this as "${parsed.contactName}" with no number. Type the number to file it.`
              : "No number in the filename. Type the number to file it."}
          </Note>
          <TextInput
            value={override}
            onChangeText={onOverride}
            placeholder="Customer number"
            placeholderTextColor={theme.inkMuted}
            keyboardType="phone-pad"
            accessibilityLabel={`Customer number for ${item.fileName}`}
            style={{
              borderColor: theme.border,
              borderWidth: 1,
              borderRadius: 10,
              padding: 12,
              fontSize: 16,
              marginTop: 10,
              color: theme.ink,
              backgroundColor: theme.surfaceRaised,
            }}
          />
        </View>
      )}

      <Button
        label="Import this one"
        onPress={onImport}
        disabled={!canImport || busy}
        style={{ marginTop: 12, paddingVertical: 11 }}
      />
    </Card>
  );
}

function OutcomeSummary({ outcomes }: { outcomes: ImportOutcome[] }) {
  const theme = useTheme();
  const imported = outcomes.filter((outcome) => outcome.ok);
  const refused = outcomes.filter((outcome) => outcome.refusedByPolicy);
  const failed = outcomes.filter((outcome) => !outcome.ok && !outcome.refusedByPolicy);

  return (
    <Card style={{ marginTop: 16 }} title="Last import">
      {imported.length > 0 && (
        <Text style={{ color: theme.good, fontSize: 14, fontWeight: "600" }}>
          {imported.length} queued for upload
        </Text>
      )}

      {refused.length > 0 && (
        <View style={{ marginTop: imported.length ? 12 : 0 }}>
          <Note tone="warning">
            {refused.length} refused by your organisation&apos;s policy and not uploaded:
          </Note>
          {refused.map((outcome) => (
            <Text
              key={outcome.fileName}
              style={{ color: theme.inkSecondary, fontSize: 12, marginTop: 4 }}
            >
              {outcome.fileName} — {policyReason(outcome.error ?? "")}
            </Text>
          ))}
        </View>
      )}

      {failed.length > 0 && (
        <View style={{ marginTop: 12 }}>
          <Note tone="critical">{failed.length} could not be imported:</Note>
          {failed.map((outcome) => (
            <Text
              key={outcome.fileName}
              style={{ color: theme.inkSecondary, fontSize: 12, marginTop: 4 }}
            >
              {outcome.fileName} — {outcome.error}
            </Text>
          ))}
        </View>
      )}
    </Card>
  );
}
