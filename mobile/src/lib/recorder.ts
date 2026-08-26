import { Audio } from "expo-av";
import * as FileSystem from "expo-file-system";

/**
 * Call audio capture.
 *
 * ## What this can and cannot do — read before planning around it
 *
 * Neither Android nor iOS lets a normal app record the *carrier* voice call.
 *
 * * **Android** — `VOICE_CALL` / `VOICE_DOWNLINK` audio sources have required
 *   the privileged `CAPTURE_AUDIO_OUTPUT` permission since Android 10, granted
 *   only to system apps. A sideloaded app cannot get it, and Google Play policy
 *   forbids using the accessibility API to work around it.
 * * **iOS** — there is no public API for it at all, at any entitlement level.
 *
 * So this module records from the **microphone**, which covers the cases that
 * actually work in production:
 *
 * 1. **Speakerphone or handset-held calls** — the mic picks up both sides.
 *    Quality is lower than a carrier tap and the far side is quieter, which is
 *    why the transcript carries per-segment confidence.
 * 2. **VoIP calls placed inside a companion app** — full-quality both-legs
 *    audio where the app owns the audio session.
 * 3. **Imported recordings** — a carrier or MDM recording written to the
 *    handset is picked up with the file importer (see `app/import.tsx`), which
 *    is the route for a fleet with a recording-capable dialler or a device
 *    owner build that does hold the privileged permission.
 *
 * Server-side recording via the telephony provider (SIP fork, carrier-side
 * recording) is the higher-quality option where the deployment allows it; the
 * upload API is the same either way, so both routes can run side by side.
 *
 * ## Consent
 *
 * Recording never starts until the policy for the number says so and the
 * consent announcement has been made. That check lives in `app/call.tsx` and
 * is not optional — it is what makes the recording lawful in two-party consent
 * jurisdictions.
 */

export interface RecordingResult {
  uri: string;
  fileName: string;
  mimeType: string;
  durationSeconds: number | null;
  sizeBytes: number | null;
}

/**
 * Mono, 44.1 kHz AAC. Speech models want mono — a stereo file of the same call
 * doubles the upload for no accuracy — and 64 kbps is comfortably above what
 * speech recognition needs while keeping an hour-long call around 30 MB.
 */
const RECORDING_OPTIONS: Audio.RecordingOptions = {
  isMeteringEnabled: true,
  android: {
    extension: ".m4a",
    outputFormat: Audio.AndroidOutputFormat.MPEG_4,
    audioEncoder: Audio.AndroidAudioEncoder.AAC,
    sampleRate: 44_100,
    numberOfChannels: 1,
    bitRate: 64_000,
  },
  ios: {
    extension: ".m4a",
    outputFormat: Audio.IOSOutputFormat.MPEG4AAC,
    audioQuality: Audio.IOSAudioQuality.MEDIUM,
    sampleRate: 44_100,
    numberOfChannels: 1,
    bitRate: 64_000,
    linearPCMBitDepth: 16,
    linearPCMIsBigEndian: false,
    linearPCMIsFloat: false,
  },
  web: {
    mimeType: "audio/webm",
    bitsPerSecond: 64_000,
  },
};

export class CallRecorder {
  private recording: Audio.Recording | null = null;
  private startedAt: number | null = null;

  get isRecording(): boolean {
    return this.recording !== null;
  }

  get elapsedSeconds(): number {
    return this.startedAt === null ? 0 : (Date.now() - this.startedAt) / 1000;
  }

  static async hasPermission(): Promise<boolean> {
    const { granted } = await Audio.getPermissionsAsync();
    return granted;
  }

  static async requestPermission(): Promise<boolean> {
    const { granted } = await Audio.requestPermissionsAsync();
    return granted;
  }

  async start(): Promise<void> {
    if (this.recording) throw new Error("Already recording");

    const { granted } = await Audio.requestPermissionsAsync();
    if (!granted) throw new Error("Microphone access is required to record calls");

    await Audio.setAudioModeAsync({
      allowsRecordingIOS: true,
      playsInSilentModeIOS: true,
      // Keep capturing when the user switches away to their dialler — which is
      // exactly what happens on every call.
      staysActiveInBackground: true,
      shouldDuckAndroid: false,
    });

    const recording = new Audio.Recording();
    await recording.prepareToRecordAsync(RECORDING_OPTIONS);
    await recording.startAsync();

    this.recording = recording;
    this.startedAt = Date.now();
  }

  async stop(): Promise<RecordingResult> {
    const recording = this.recording;
    if (!recording) throw new Error("Not recording");

    // Cleared first so a throw below cannot leave the recorder wedged in a
    // state where start() refuses and stop() has nothing to stop.
    this.recording = null;
    const startedAt = this.startedAt;
    this.startedAt = null;

    let status: Audio.RecordingStatus | null = null;
    try {
      await recording.stopAndUnloadAsync();
      status = await recording.getStatusAsync();
    } catch {
      /* fall through: the file is usually still on disk and worth keeping */
    }
    await Audio.setAudioModeAsync({ allowsRecordingIOS: false });

    const uri = recording.getURI();
    if (!uri) throw new Error("The recording produced no file");

    const info = await FileSystem.getInfoAsync(uri);
    const durationMs = status?.durationMillis;
    const durationSeconds =
      durationMs !== undefined
        ? durationMs / 1000
        : startedAt !== null
          ? (Date.now() - startedAt) / 1000
          : null;

    return {
      uri,
      fileName: uri.split("/").pop() ?? "call.m4a",
      mimeType: "audio/mp4",
      durationSeconds,
      sizeBytes: info.exists && !info.isDirectory ? info.size : null,
    };
  }

  /** Abandon the take and delete the partial file. */
  async cancel(): Promise<void> {
    const recording = this.recording;
    this.recording = null;
    this.startedAt = null;
    if (!recording) return;

    try {
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      if (uri) await FileSystem.deleteAsync(uri, { idempotent: true });
    } catch {
      /* best effort */
    }
    await Audio.setAudioModeAsync({ allowsRecordingIOS: false });
  }
}
