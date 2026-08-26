import * as Application from "expo-application";
import * as Device from "expo-device";
import { useRouter } from "expo-router";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Platform } from "react-native";

import { ApiError, api, credentials } from "./api";
import { startQueueWatcher, uploadQueue } from "./uploadQueue";
import type { AgentStatus, DeviceSession } from "./types";

interface SessionState {
  session: DeviceSession | null;
  status: AgentStatus;
  loading: boolean;
  pair: (code: string) => Promise<void>;
  setStatus: (status: AgentStatus, callId?: string) => Promise<void>;
  unpair: () => Promise<void>;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<DeviceSession | null>(null);
  const [status, setLocalStatus] = useState<AgentStatus>("offline");
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;

    (async () => {
      await uploadQueue.load();
      const stored = await credentials.session();
      if (cancelled) return;

      if (!stored) {
        setLoading(false);
        return;
      }
      setSession(stored);

      // Confirm the pairing is still good. An admin may have revoked this
      // handset, and finding that out now beats finding out mid-call.
      try {
        const agent = await api.me();
        if (!cancelled) setLocalStatus(agent.status);
      } catch (caught) {
        if (caught instanceof ApiError && caught.isAuthFailure) {
          await credentials.clear();
          if (!cancelled) setSession(null);
        }
        // A network error leaves the session in place — being offline is not
        // the same as being unpaired.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    const stopWatcher = startQueueWatcher();
    return () => {
      cancelled = true;
      stopWatcher();
    };
  }, []);

  const pair = useCallback(
    async (code: string) => {
      const paired = await api.pair({
        code,
        platform: Platform.OS === "ios" ? "ios" : "android",
        device_name: Device.deviceName ?? Device.modelName ?? undefined,
        os_version: Device.osVersion ?? undefined,
        app_version: Application.nativeApplicationVersion ?? undefined,
      });
      await credentials.save(paired);
      setSession(paired);
      setLocalStatus("offline");
      router.replace("/");
    },
    [router],
  );

  const setStatus = useCallback(async (next: AgentStatus, callId?: string) => {
    // Optimistic: the toggle should not feel laggy on a poor connection, and
    // the next heartbeat corrects it if the write failed.
    setLocalStatus(next);
    try {
      const agent = await api.setStatus(next, callId);
      setLocalStatus(agent.status);
    } catch {
      /* keep the local value; presence is a best-effort signal */
    }
  }, []);

  const unpair = useCallback(async () => {
    try {
      await api.unpair();
    } catch {
      /* unpair locally even if the server cannot be reached */
    }
    await credentials.clear();
    setSession(null);
    setLocalStatus("offline");
    router.replace("/pair");
  }, [router]);

  const value = useMemo<SessionState>(
    () => ({ session, status, loading, pair, setStatus, unpair }),
    [session, status, loading, pair, setStatus, unpair],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside <SessionProvider>");
  return context;
}
