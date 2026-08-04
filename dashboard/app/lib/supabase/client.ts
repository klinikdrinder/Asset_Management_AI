"use client";
import{createBrowserClient}from"@supabase/ssr";import{getFirebaseClientAuth}from"../firebase/client";
export function createClient(){return createBrowserClient(process.env.NEXT_PUBLIC_SUPABASE_URL!,(process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY??process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)!,{accessToken:async()=>getFirebaseClientAuth().currentUser?.getIdToken(false)??null})}
