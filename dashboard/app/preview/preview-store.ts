"use client";
import type{DemoAsset}from"./demo-data";
import{INITIAL_DEMO_ASSETS}from"./demo-data";
const KEY="kdi_demo_uploaded_assets",EVENT="kdi-demo-assets-changed";
let cachedRaw="",cachedAssets:DemoAsset[]=INITIAL_DEMO_ASSETS;
export function getDemoAssets(){if(typeof window==="undefined")return INITIAL_DEMO_ASSETS;try{const raw=localStorage.getItem(KEY)||"[]";if(raw!==cachedRaw){cachedRaw=raw;const saved=JSON.parse(raw)as DemoAsset[];cachedAssets=[...saved,...INITIAL_DEMO_ASSETS]}return cachedAssets}catch{return INITIAL_DEMO_ASSETS}}
export function addDemoAssets(assets:DemoAsset[]){const existing=getDemoAssets().filter(x=>!INITIAL_DEMO_ASSETS.some(base=>base.id===x.id));localStorage.setItem(KEY,JSON.stringify([...assets,...existing]));window.dispatchEvent(new Event(EVENT))}
export function subscribeDemoAssets(listener:()=>void){window.addEventListener(EVENT,listener);return()=>window.removeEventListener(EVENT,listener)}
export function serverDemoAssets(){return INITIAL_DEMO_ASSETS}
