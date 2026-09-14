"use client";
import type { AssetSceneRow } from "./queries";

// Clickable scene timeline for video. Each entry seeks the single media <video> (id kdiAssetVideo,
// set by MediaViewer) to the scene's start time and plays — the P4 "jump to timecode" behaviour.
const formatTime = (seconds: number | null) => {
  if (seconds == null) return "--:--";
  const total = Math.max(0, Math.floor(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
};

export function SceneTimeline({ scenes }: { scenes: AssetSceneRow[] }) {
  if (!scenes.length) return null;
  const seek = (start: number | null) => {
    if (start == null) return;
    const video = document.getElementById("kdiAssetVideo") as HTMLVideoElement | null;
    if (!video) return;
    video.currentTime = start;
    void video.play().catch(() => { /* autoplay may be blocked; the seek still lands */ });
  };
  return (
    <section className="sceneTimeline" aria-label="Scene timeline">
      <h3>Scene timeline · {scenes.length}</h3>
      <ol>
        {scenes.map((scene) => (
          <li key={scene.index}>
            <button type="button" className="sceneJump" onClick={() => seek(scene.start)} disabled={scene.start == null}>
              <span className="sceneTime">{formatTime(scene.start)}</span>
              <span className="sceneDesc">{scene.description || `Scene ${scene.index + 1}`}</span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
