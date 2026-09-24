import { useState } from "react";
import { Text, TextInput, View } from "react-native";

import { Button, Card, Note, Screen, useTheme } from "@/components/ui";
import { useSession } from "@/lib/session";

/**
 * Handset pairing.
 *
 * The agent types a one-time code their supervisor generated. That exchange is
 * what binds this handset to exactly one agent — the app never asks which
 * agent it is, so a paired handset can only ever write that agent's calls.
 */
export default function PairScreen() {
  const theme = useTheme();
  const { pair } = useSession();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit() {
    setBusy(true);
    setError(null);
    try {
      await pair(code.trim());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Pairing failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Card
        title="Enter your pairing code"
        subtitle="Your supervisor generates this in the dashboard. It works once and expires after 30 minutes."
      >
        <TextInput
          value={code}
          onChangeText={(next) => setCode(next.toUpperCase())}
          autoCapitalize="characters"
          autoCorrect={false}
          placeholder="ABCD-1234"
          placeholderTextColor={theme.inkMuted}
          accessibilityLabel="Pairing code"
          style={{
            borderColor: theme.border,
            borderWidth: 1,
            borderRadius: 10,
            paddingVertical: 14,
            paddingHorizontal: 16,
            fontSize: 22,
            letterSpacing: 4,
            textAlign: "center",
            color: theme.ink,
            backgroundColor: theme.surfaceRaised,
          }}
        />

        {error && (
          <View style={{ marginTop: 12 }}>
            <Note tone="critical">{error}</Note>
          </View>
        )}

        <Button
          label="Pair handset"
          variant="primary"
          onPress={onSubmit}
          busy={busy}
          disabled={code.trim().length < 4}
          style={{ marginTop: 16 }}
        />
      </Card>

      <Card style={{ marginTop: 16 }} title="Before you start">
        <Note>
          This app records calls only on numbers your administrator has switched on, and
          only after the consent announcement has been made. It checks the policy for the
          other party before every call and will refuse to record when the policy says no —
          including when a customer has asked not to be recorded.
        </Note>
      </Card>

      <Text style={{ color: theme.inkMuted, fontSize: 12, marginTop: 20, textAlign: "center" }}>
        Recordings are uploaded over HTTPS and deleted from this handset once accepted.
      </Text>
    </Screen>
  );
}
