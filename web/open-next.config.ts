// OpenNext config for the Cloudflare adapter. Defaults are correct for this
// app — no ISR/tag caching, no queue, nothing custom to configure — so this
// just has to exist and be the default export.
// https://opennext.js.org/cloudflare
import { defineCloudflareConfig } from "@opennextjs/cloudflare";

export default defineCloudflareConfig();
