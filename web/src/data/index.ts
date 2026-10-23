import { apiSource } from "./api";
import { staticSource } from "./static";
import type { DataSource } from "./types";

// VITE_DATA_SOURCE=api|static picks the source at build time (default: api).
const choice = (import.meta.env.VITE_DATA_SOURCE as string | undefined) ?? "api";

export const data: DataSource = choice === "static" ? staticSource : apiSource;
export * from "./types";
export * from "./timing";
