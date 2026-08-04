"use client";

import { getApp, getApps, initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { firebaseClientConfig } from "./config";

export function getFirebaseClientApp() {
  return getApps().length ? getApp() : initializeApp(firebaseClientConfig());
}

export function getFirebaseClientAuth() {
  return getAuth(getFirebaseClientApp());
}
