// The background sync task must be defined before anything else runs: Android
// starts the JS runtime headless for it, without mounting a single screen.
import "./src/lib/autoSync";
import "expo-router/entry";
