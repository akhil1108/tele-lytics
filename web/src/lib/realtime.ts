"use client";

import { useEffect, useRef, useState } from "react";

import { API_BASE_URL, tokenStore } from "./api";
import type { Presence } from "./types";

export interface RealtimeEvent {
  event: string;
  data: Record<string, unknown>;
  ts?: string;
}

interface RealtimeState {
  presence: Presence | null;
  connected: boolean;
  lastEvent: RealtimeEvent | null;
}

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

/**
 * Live dashboard channel.
 *
 * Reconnects with capped exponential backoff; `onEvent` is held in a ref so a
 * caller passing an inline closure does not tear the socket down on every
 * render.
 */
export function useRealtime(onEvent?: (event: RealtimeEvent) => void): RealtimeState {
  const [presence, setPresence] = useState<Presence | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<RealtimeEvent | null>(null);

  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    const token = tokenStore.access;
    if (!token) return;

    let socket: WebSocket | null = null;
    let attempt = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = () => {
      if (closed) return;
      const url = new URL(`${API_BASE_URL}/ws/dashboard`);
      url.protocol = url.protocol.replace("http", "ws");
      url.searchParams.set("token", tokenStore.access ?? token);

      socket = new WebSocket(url.toString());

      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
      };

      socket.onmessage = (message) => {
        let payload: RealtimeEvent;
        try {
          payload = JSON.parse(message.data);
        } catch {
          return; // "pong" and other plain-text frames
        }
        if (payload.event === "heartbeat") return;
        if (payload.event === "presence") setPresence(payload.data as unknown as Presence);
        setLastEvent(payload);
        handlerRef.current?.(payload);
      };

      socket.onclose = () => {
        setConnected(false);
        if (closed) return;
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS);
        attempt += 1;
        retryTimer = setTimeout(connect, delay);
      };

      socket.onerror = () => socket?.close();
    };

    connect();

    return () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  return { presence, connected, lastEvent };
}
