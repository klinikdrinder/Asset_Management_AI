"use client";
import { createBrowserClient } from "@supabase/ssr";
export function createPasswordAuthClient(remember=true){return createBrowserClient(process.env.NEXT_PUBLIC_SUPABASE_URL!,(process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY??process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)!,{cookieOptions:{path:"/",sameSite:"lax",secure:window.location.protocol==="https:",...(remember?{maxAge:30*24*60*60}:{maxAge:undefined})}})}
