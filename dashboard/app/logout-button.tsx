"use client";
import{signOut}from"firebase/auth";import{getFirebaseClientAuth}from"./lib/firebase/client";
export function LogoutButton(){async function logout(){await fetch("/api/auth/logout",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"}}).catch(()=>undefined);await signOut(getFirebaseClientAuth()).catch(()=>undefined);try{localStorage.clear();sessionStorage.clear()}catch{}window.location.replace("/login")}return <button className="signOutLink" type="button" onClick={logout}>Sign out</button>}
