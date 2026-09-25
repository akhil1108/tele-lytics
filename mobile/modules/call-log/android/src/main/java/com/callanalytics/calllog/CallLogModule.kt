package com.callanalytics.calllog

import android.Manifest
import android.content.pm.PackageManager
import android.provider.CallLog
import androidx.core.content.ContextCompat
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/**
 * Reads the system call log.
 *
 * This is how the platform accounts for calls that produced no recording — the
 * agent's dialler may not record at all, or recording may be off for that call.
 * The log still knows the number, the exact duration and which way the call
 * went, and that is enough for volume and talk-time reporting.
 *
 * Only the fields the platform actually uses are read. `CACHED_NAME` is the
 * name the dialler showed for the call — a saved contact, or the caller-ID
 * app's lookup (Truecaller writes it here when it is the default dialler). The
 * call log also holds photo URIs, geocoded locations and voicemail
 * transcriptions; none of that is touched.
 */
class CallLogModule : Module() {

  override fun definition() = ModuleDefinition {
    Name("CallLog")

    Function("isAvailable") { true }

    Function("hasPermission") { hasReadCallLogPermission() }

    /**
     * Entries newer than `sinceEpochMs`, oldest first.
     *
     * `limit` bounds a first sync on a handset with years of history; the
     * caller pages by advancing `sinceEpochMs` past the newest entry it saw.
     */
    AsyncFunction("getEntries") { sinceEpochMs: Double, limit: Int ->
      if (!hasReadCallLogPermission()) {
        throw SecurityException("READ_CALL_LOG has not been granted")
      }
      readEntries(sinceEpochMs.toLong(), limit)
    }
  }

  private fun hasReadCallLogPermission(): Boolean {
    val context = appContext.reactContext ?: return false
    return ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALL_LOG) ==
      PackageManager.PERMISSION_GRANTED
  }

  private fun readEntries(sinceEpochMs: Long, limit: Int): List<Map<String, Any?>> {
    val context = appContext.reactContext ?: return emptyList()

    val projection = arrayOf(
      CallLog.Calls._ID,
      CallLog.Calls.NUMBER,
      CallLog.Calls.DATE,
      CallLog.Calls.DURATION,
      CallLog.Calls.TYPE,
      CallLog.Calls.CACHED_NAME,
    )

    val entries = mutableListOf<Map<String, Any?>>()

    // Ascending by date: a sync that is interrupted part way still leaves a
    // contiguous prefix, so resuming from the newest seen entry loses nothing.
    context.contentResolver.query(
      CallLog.Calls.CONTENT_URI,
      projection,
      "${CallLog.Calls.DATE} > ?",
      arrayOf(sinceEpochMs.toString()),
      "${CallLog.Calls.DATE} ASC LIMIT $limit",
    )?.use { cursor ->
      val idColumn = cursor.getColumnIndexOrThrow(CallLog.Calls._ID)
      val numberColumn = cursor.getColumnIndexOrThrow(CallLog.Calls.NUMBER)
      val dateColumn = cursor.getColumnIndexOrThrow(CallLog.Calls.DATE)
      val durationColumn = cursor.getColumnIndexOrThrow(CallLog.Calls.DURATION)
      val typeColumn = cursor.getColumnIndexOrThrow(CallLog.Calls.TYPE)
      val nameColumn = cursor.getColumnIndex(CallLog.Calls.CACHED_NAME)

      while (cursor.moveToNext()) {
        entries.add(
          mapOf(
            "id" to cursor.getString(idColumn),
            "number" to cursor.getString(numberColumn),
            "timestamp" to cursor.getLong(dateColumn).toDouble(),
            "durationSeconds" to cursor.getInt(durationColumn),
            "type" to typeName(cursor.getInt(typeColumn)),
            "name" to if (nameColumn >= 0) cursor.getString(nameColumn)?.takeIf { it.isNotBlank() } else null,
          )
        )
      }
    }

    return entries
  }

  /** Mapped here rather than in JS so the integer constants stay on one side. */
  private fun typeName(type: Int): String = when (type) {
    CallLog.Calls.INCOMING_TYPE -> "incoming"
    CallLog.Calls.OUTGOING_TYPE -> "outgoing"
    CallLog.Calls.MISSED_TYPE -> "missed"
    CallLog.Calls.REJECTED_TYPE -> "rejected"
    CallLog.Calls.BLOCKED_TYPE -> "blocked"
    CallLog.Calls.VOICEMAIL_TYPE -> "voicemail"
    else -> "unknown"
  }
}
