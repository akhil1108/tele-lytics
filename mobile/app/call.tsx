import { useKeepAwake } from "expo-keep-awake";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ScrollView, Switch, Text, TextInput, View } from "react-native";

import { Button, Card, Note, Pill, Screen, useTheme } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { CallRecorder } from "@/lib/recorder";
import { useSession } from "@/lib/session";
import { clock, policyReason } from "@/lib/theme";
import type { Direction, PolicyDecision } from "@/lib/types";
import { uploadQueue } from "@/lib/uploadQueue";

type Phase = "setup" | "ready" | "recording" | "saving";

/**
 * Record one call.
 *
 * The flow is deliberately gated: a number is entered, the server decides
 * whether this call may be recorded, and only then does the record control
 * unlock. When consent is required, the agent must confirm the announcement
 * was made — the switch is the record of that, and it is uploaded with the
 * audio.
 */
export default function CallScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { session, setStatus } = useSession();
  useKeepAwake(); // the screen must not sleep mid-recording

  const [phase, setPhase] = useState<Phase>("setup");
  const [number, setNumber] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [direction, setDirection] = useState<Direction>("outbound");
  const [policy, setPolicy] = useState<PolicyDecision | null>(null);
  const [consentGiven, setConsentGiven] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const recorder = useRef(new CallRecorder());
  const startedAt = useRef<string | null>(null);
  const ticker = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const active = recorder.current;
    return () => {
      if (ticker.current) clearInterval(ticker.current);
      // Leaving mid-recording abandons the take rather than silently keeping
      // an orphan file the agent never sees again.
      if (active.isRecording) void active.cancel();
    };
  }, []);

  const checkPolicy = useCallback(async () => {
    setBusy(true);
    setError(null);
    setPolicy(null);
    try {
      const decision = await api.recordingPolicy(number.trim(), direction);
      setPolicy(decision);
      setConsentGiven(!decision.consent_required);
      setPhase("ready");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not check the policy");
    } finally {
      setBusy(false);
    }
  }, [number, direction]);

  async function startRecording() {
    setError(null);
    try {
      await recorder.current.start();
      startedAt.current = new Date().toISOString();
      setPhase("recording");
      setElapsed(0);
      ticker.current = setInterval(
        () => setElapsed(recorder.current.elapsedSeconds),
        500,
      );
      void setStatus("on_call");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start recording");
    }
  }

  async function finish(withRecording: boolean) {
    setPhase("saving");
    if (ticker.current) clearInterval(ticker.current);
    setError(null);

    try {
      const result =
        withRecording && recorder.current.isRecording ? await recorder.current.stop() : null;
      if (!withRecording && recorder.current.isRecording) {
        await recorder.current.cancel();
      }

      const started = startedAt.current ?? new Date().toISOString();
      const ended = new Date().toISOString();

      const call = await api.logCall({
        // Ties a retry to the same call rather than creating a duplicate.
        external_ref: `${session?.device_id ?? "device"}-${started}`,
        direction,
        customer_number: number.trim(),
        customer_name: customerName.trim() || null,
        started_at: started,
        ended_at: ended,
        status: "completed",
        recording_expected: Boolean(policy?.should_record),
        recording_skipped_reason: policy?.should_record ? null : (policy?.reason ?? null),
      });

      if (result) {
        // Queued rather than uploaded inline: the agent is free to take the
        // next call immediately, and a dropped connection costs nothing.
        await uploadQueue.enqueue({
          callId: call.id,
          fileUri: result.uri,
          mimeType: result.mimeType,
          fileName: result.fileName,
          durationSeconds: result.durationSeconds,
          consentCaptured: consentGiven,
          customerNumber: number.trim(),
          startedAt: started,
        });
      }

      void setStatus("wrap_up");
      router.replace("/uploads");
    } catch (caught) {
      const message =
        caught instanceof ApiError
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "Could not save the call";
      setError(`${message}. The recording is still on this handset.`);
      setPhase("ready");
    }
  }

  const canRecord = policy?.should_record === true && consentGiven;

  return (
    <ScrollView style={{ backgroundColor: theme.page }} keyboardShouldPersistTaps="handled">
      <Screen>
        {phase !== "recording" && (
          <Card title="Who are you calling?">
            <TextInput
              value={number}
              onChangeText={setNumber}
              placeholder="+91 98765 43210"
              placeholderTextColor={theme.inkMuted}
              keyboardType="phone-pad"
              accessibilityLabel="Customer number"
              editable={phase === "setup" || phase === "ready"}
              style={{
                borderColor: theme.border,
                borderWidth: 1,
                borderRadius: 10,
                padding: 14,
                fontSize: 18,
                color: theme.ink,
                backgroundColor: theme.surfaceRaised,
              }}
            />
            <TextInput
              value={customerName}
              onChangeText={setCustomerName}
              placeholder="Customer name (optional)"
              placeholderTextColor={theme.inkMuted}
              accessibilityLabel="Customer name"
              style={{
                borderColor: theme.border,
                borderWidth: 1,
                borderRadius: 10,
                padding: 14,
                fontSize: 15,
                marginTop: 10,
                color: theme.ink,
                backgroundColor: theme.surfaceRaised,
              }}
            />

            <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
              {(["outbound", "inbound"] as Direction[]).map((option) => (
                <Button
                  key={option}
                  label={option === "outbound" ? "I called them" : "They called me"}
                  variant={direction === option ? "primary" : "secondary"}
                  onPress={() => {
                    setDirection(option);
                    setPolicy(null);
                    setPhase("setup");
                  }}
                  style={{ flex: 1, paddingVertical: 12 }}
                />
              ))}
            </View>

            <Button
              label="Check recording policy"
              onPress={checkPolicy}
              busy={busy}
              disabled={number.trim().length < 6}
              style={{ marginTop: 12 }}
            />
          </Card>
        )}

        {policy && phase !== "recording" && (
          <Card
            style={{ marginTop: 16 }}
            title={policy.should_record ? "This call will be recorded" : "This call will not be recorded"}
          >
            <Pill
              label={policyReason(policy.reason)}
              color={policy.should_record ? theme.good : theme.inkMuted}
            />

            {policy.should_record && policy.consent_required && (
              <View style={{ marginTop: 14 }}>
                <Note>
                  Read this to the customer before you start:
                </Note>
                <Text
                  style={{
                    color: theme.ink,
                    fontSize: 15,
                    lineHeight: 22,
                    marginTop: 8,
                    fontStyle: "italic",
                  }}
                >
                  “{policy.consent_prompt}”
                </Text>
                <View
                  style={{
                    flexDirection: "row",
                    alignItems: "center",
                    gap: 12,
                    marginTop: 14,
                  }}
                >
                  <Switch
                    value={consentGiven}
                    onValueChange={setConsentGiven}
                    accessibilityLabel="I read the consent announcement"
                    trackColor={{ true: theme.accent, false: theme.border }}
                  />
                  <Text style={{ color: theme.ink, fontSize: 14, flex: 1 }}>
                    I read this out and the customer agreed
                  </Text>
                </View>
              </View>
            )}

            {!policy.should_record && (
              <View style={{ marginTop: 12 }}>
                <Note>
                  You can still log this call so it appears in your history and in the
                  dashboard — it just will not have audio or a transcript.
                </Note>
              </View>
            )}

            <Button
              label={policy.should_record ? "Start recording" : "Log this call"}
              variant="primary"
              onPress={() => (policy.should_record ? startRecording() : finish(false))}
              disabled={policy.should_record ? !canRecord : false}
              busy={phase === "saving"}
              style={{ marginTop: 16 }}
            />
          </Card>
        )}

        {phase === "recording" && (
          <Card title="Recording">
            <Text
              style={{
                color: theme.ink,
                fontSize: 48,
                fontVariant: ["tabular-nums"],
                textAlign: "center",
                marginVertical: 12,
              }}
              accessibilityLabel={`Recording, ${Math.round(elapsed)} seconds elapsed`}
            >
              {clock(elapsed)}
            </Text>
            <Text style={{ color: theme.inkMuted, fontSize: 13, textAlign: "center" }}>
              {number} · {direction === "outbound" ? "outgoing" : "incoming"}
            </Text>

            <View style={{ marginTop: 20 }}>
              <Note>
                Keep this app open or the call on speaker. Recording captures the
                microphone — the platform does not allow apps to tap the carrier call
                directly.
              </Note>
            </View>

            <Button
              label="Stop and save"
              variant="primary"
              onPress={() => finish(true)}
              style={{ marginTop: 20 }}
            />
            <Button
              label="Discard this recording"
              variant="danger"
              onPress={() => finish(false)}
              style={{ marginTop: 10 }}
            />
          </Card>
        )}

        {error && (
          <View style={{ marginTop: 16 }}>
            <Note tone="critical">{error}</Note>
          </View>
        )}
      </Screen>
    </ScrollView>
  );
}
