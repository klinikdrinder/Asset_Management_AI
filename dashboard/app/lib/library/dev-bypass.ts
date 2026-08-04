import "server-only";

export function isLibraryDevBypassEnabled(env: NodeJS.ProcessEnv = process.env) {
  return env.NODE_ENV === "development" && env.KDI_LIBRARY_DEV_BYPASS === "true";
}
