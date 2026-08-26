import { useEffect, useState } from "react";
import { FlatList, RefreshControl, Text, View } from "react-native";

import { Button, Card, Note, Pill, Screen, useTheme } from "@/components/ui";
import { duration } from "@/lib/theme";
import type { PendingUpload } from "@/lib/types";
import { isStuck, uploadQueue } from "@/lib/uploadQueue";

/**
 * The upload queue, made visible.
 *
 * An agent needs to know a recording actually left the handset — that is the
 * difference between a call that gets analysed and one that quietly does not.
 * Failures stay on this list until they succeed or are deleted deliberately.
 */
export default function UploadsScreen() {
  const theme = useTheme();
  const [items, setItems] = useState<PendingUpload[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => uploadQueue.subscribe(setItems), []);

  async function refresh() {
    setRefreshing(true);
    await uploadQueue.drain();
    setRefreshing(false);
  }

  return (
    <Screen>
      <FlatList
        data={items}
        keyExtractor={(item) => item.id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
        ListEmptyComponent={
          <Card title="Nothing waiting">
            <Note>
              Every recording on this handset has been uploaded and removed. New
              recordings appear here until the server accepts them.
            </Note>
          </Card>
        }
        ListHeaderComponent={
          items.length > 0 ? (
            <View style={{ marginBottom: 12 }}>
              <Note>
                Recordings upload on their own when you have a connection. They are
                deleted from this handset only once the server has accepted them.
              </Note>
            </View>
          ) : null
        }
        ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
        renderItem={({ item }) => {
          const stuck = isStuck(item);
          return (
            <Card>
              <View
                style={{
                  flexDirection: "row",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  gap: 12,
                }}
              >
                <View style={{ flex: 1 }}>
                  <Text style={{ color: theme.ink, fontSize: 15, fontWeight: "600" }}>
                    {item.customerNumber}
                  </Text>
                  <Text style={{ color: theme.inkMuted, fontSize: 12, marginTop: 2 }}>
                    {new Date(item.startedAt).toLocaleString()} ·{" "}
                    {duration(item.durationSeconds)}
                  </Text>
                </View>
                <Pill
                  label={
                    stuck ? "Needs attention" : item.attempts === 0 ? "Waiting" : "Retrying"
                  }
                  color={stuck ? theme.critical : item.attempts === 0 ? theme.accent : theme.warning}
                />
              </View>

              {item.lastError && (
                <View style={{ marginTop: 10 }}>
                  <Note tone={stuck ? "critical" : "warning"}>
                    {item.lastError}
                    {!stuck && ` · attempt ${item.attempts}`}
                  </Note>
                </View>
              )}

              <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
                <Button
                  label="Retry now"
                  onPress={() => void uploadQueue.retryNow(item.id)}
                  style={{ flex: 1, paddingVertical: 11 }}
                />
                <Button
                  label="Delete"
                  variant="danger"
                  onPress={() => void uploadQueue.remove(item.id, { deleteFile: true })}
                  style={{ flex: 1, paddingVertical: 11 }}
                />
              </View>
            </Card>
          );
        }}
      />
    </Screen>
  );
}
