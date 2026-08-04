export const FIREBASE_PROJECT_ID = "kdi-media-library";
export const FIREBASE_ISSUER = `https://securetoken.google.com/${FIREBASE_PROJECT_ID}`;

export function firebaseClientConfig() {
  // Direct references are required so Next.js can inline NEXT_PUBLIC values in browser bundles.
  const config = {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
    storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  };
  if (Object.values(config).some((value) => !value) || config.projectId !== FIREBASE_PROJECT_ID) {
    throw new Error("Firebase configuration is unavailable");
  }
  return config as Record<keyof typeof config, string>;
}
