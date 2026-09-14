"""Generalized per-asset extraction for the AI Search v3 full run.

Parameterized by asset_id from the DB (not a cohort JSON), so the queue worker
can drive it over the whole library. Reuses the proven job-1 pipeline:
  media/drive lookup -> 3-tier image decode (image_access) or 6-frame video
  extraction -> v2 contract prompt with live vocab -> Claude vision ->
  validate -> resolve + finalize_concept + apply_donor_precondition -> write.

--dry-run does everything up to (and excluding) the Claude call and the DB
write: it proves decode + frame extraction + prompt/vocab assembly for an
arbitrary asset without any external call, cost, or write. The real path is
gated by the consent workflow and is not exercised here.
"""
from __future__ import annotations

import argparse, base64, io, json, os, random, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values
from PIL import Image
from supabase import create_client
import imageio_ffmpeg
from google.oauth2 import service_account
from googleapiclient.discovery import build as gbuild
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kdi_media.ontology_resolver import OntologyResolver, PERSON_ROLES, RELATIONSHIP_TYPES  # noqa
from kdi_media.extraction_contract_v2 import (  # noqa
    build_prompt, finalize_concept, apply_donor_precondition, LAYER_IDS, STATES)
from kdi_media.image_access import get_display_jpeg  # noqa

MODEL = "claude-opus-4-8"
NS = uuid.UUID("6b1a9f27-4c3d-4a58-9e70-2d5c8f1b3a64")
FF = imageio_ffmpeg.get_ffmpeg_exe()
FRACS = (0.05, 0.2, 0.4, 0.6, 0.8, 0.95)
WORK = ROOT / "tmp" / "fullrun"; WORK.mkdir(parents=True, exist_ok=True)
VOCAB_TABLE = {"ANATOMY": ("anatomy_terms", "name"), "TREATMENT_PROCEDURE": ("treatments", "name"),
               "ACTIONS_EVENTS": ("actions", "name"),
               "CLINICAL_VISUAL_OBSERVATIONS": ("clinical_observation_definitions", "label"),
               "ENVIRONMENT": ("locations", "name")}
TRANSIENT = (httpx.RemoteProtocolError, httpx.TransportError, ConnectionError)


class PermanentDL(Exception):
    """A per-file download failure that retrying won't fix (404/403/gone)."""


def _env():
    e = {}
    for f in (ROOT / ".env", ROOT / ".env.local", ROOT / "dashboard/.env.local"):
        if f.exists():
            e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ); return e


class Extractor:
    """Holds the shared clients/resolver/vocab so the queue can reuse one instance."""

    def __init__(self):
        e = _env()
        self.e = e
        self.akey = e.get("ANTHROPIC_API_KEY")
        self.db = create_client(e.get("SUPABASE_URL") or e["NEXT_PUBLIC_SUPABASE_URL"], e["SUPABASE_SERVICE_ROLE_KEY"])
        self.creds = service_account.Credentials.from_service_account_file(
            e["GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH"],
            scopes=["https://www.googleapis.com/auth/drive.readonly"])
        self.drive = gbuild("drive", "v3", credentials=self.creds, cache_discovery=False)
        self.resolver = OntologyResolver.from_supabase(self.db)
        self.vocab = {}
        for layer, (table, namecol) in VOCAB_TABLE.items():
            rows = self.db.table(table).select(f"code,{namecol}").eq("is_active", True).execute().data or []
            self.vocab[layer] = [(r["code"], r.get(namecol)) for r in rows]
        self.vocab["PEOPLE_ROLES"] = [(c, c) for c in PERSON_ROLES]
        self.vocab["RELATIONSHIPS"] = [(c, c) for c in RELATIONSHIP_TYPES]

    def _retry(self, fn, attempts=6):
        for i in range(attempts):
            try:
                return fn()
            except TRANSIENT:
                if i == attempts - 1:
                    raise
                time.sleep(min(30, 2 ** i) + 0.5)

    def asset_meta(self, asset_id):
        a = self.db.table("assets").select("id,file_name,mime_type").eq("id", asset_id).single().execute().data
        media = "video" if str(a.get("mime_type", "")).startswith("video") else "image"
        rows = self.db.table("asset_sources").select("source_file_id,is_first_discovered_source").eq("asset_id", asset_id).execute().data or []
        rows.sort(key=lambda r: 0 if r.get("is_first_discovered_source") else 1)
        src = None
        for r in rows:
            sf = self.db.table("source_files").select("google_file_id,is_folder").eq("id", r["source_file_id"]).single().execute().data
            if sf and sf.get("google_file_id") and not sf.get("is_folder"):
                src = sf["google_file_id"]; break
        d = self.db.table("asset_destinations").select("destination_google_file_id").eq("asset_id", asset_id).limit(1).execute().data
        master = d[0]["destination_google_file_id"] if d else None
        return media, a.get("file_name"), src, master

    def _download(self, file_id):
        for i in range(6):
            try:
                buf = io.BytesIO()
                dl = MediaIoBaseDownload(buf, self.drive.files().get_media(fileId=file_id, supportsAllDrives=True), chunksize=8 * 1024 * 1024)
                done = False
                while not done:
                    _, done = dl.next_chunk()
                return buf.getvalue()
            except HttpError as ex:
                if getattr(ex.resp, "status", None) in (403, 404, 410):
                    raise PermanentDL(f"http_{ex.resp.status}")
                if i == 5:
                    raise PermanentDL("http_exhausted")
                time.sleep(min(30, 2 ** i) + 0.5)
            except TRANSIENT:
                if i == 5:
                    raise PermanentDL("transient_exhausted")
                time.sleep(min(30, 2 ** i) + 0.5)

    def _video_frames_b64(self, asset_id, raw):
        dest = WORK / f"{asset_id}.mp4"; dest.write_bytes(raw)
        try:
            p = subprocess.run([FF, "-i", str(dest)], capture_output=True, text=True)
            dur = 5.0
            for line in p.stderr.splitlines():
                if "Duration:" in line:
                    try:
                        h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
                        dur = int(h) * 3600 + int(m) * 60 + float(s)
                    except ValueError:
                        pass
                    break
            out = []
            for i, fr in enumerate(FRACS):
                o = WORK / f"{asset_id}_f{i}.jpg"
                subprocess.run([FF, "-nostdin", "-ss", f"{max(0.0, dur*fr):.3f}", "-i", str(dest),
                                "-frames:v", "1", "-q:v", "3", str(o), "-y"], capture_output=True)
                if o.exists() and o.stat().st_size > 0:
                    out.append(base64.b64encode(o.read_bytes()).decode("ascii")); o.unlink()
            return out
        finally:
            dest.unlink(missing_ok=True)

    def _frames_from_bytes(self, asset_id, media, raw, gid):
        if media == "video":
            return self._video_frames_b64(asset_id, raw)
        res = get_display_jpeg(raw, drive=self.drive, creds=self.creds, file_id=gid)
        return [base64.b64encode(res["jpeg"]).decode("ascii")] if res["jpeg"] else []

    def frames_for(self, asset_id, media, src, master=None):
        """Try the SOURCE original; if its Drive id is dead (404) or undecodable,
        fall back to the MASTER migrated copy. Never sends 0 frames to the model."""
        last = None
        for gid in (src, master):
            if not gid:
                continue
            try:
                raw = self._download(gid)
            except PermanentDL as ex:
                last = str(ex); continue
            frames = self._frames_from_bytes(asset_id, media, raw, gid)
            if frames:
                return frames
            last = "undecodable"
        raise RuntimeError(f"no_usable_copy:{last}")

    def _analyze(self, frames_b64, evidence_text):
        prompt = build_prompt(evidence_text, self.vocab)
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b}} for b in frames_b64]
        content.append({"type": "text", "text": prompt})
        body = {"model": MODEL, "max_tokens": 12000, "thinking": {"type": "adaptive"},
                "messages": [{"role": "user", "content": content}]}
        headers = {"x-api-key": self.akey, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        last = None
        for attempt in range(6):
            try:
                r = httpx.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=600)
                if r.status_code in (429, 500, 502, 503, 504, 529):
                    last = f"http_{r.status_code}"
                    ra = r.headers.get("retry-after")
                    time.sleep(max(float(ra) if ra else 0.0, min(60, 2 ** attempt) + random.uniform(0, 1.5)))
                    continue
                r.raise_for_status()
                b = r.json()
                text = "".join(x.get("text", "") for x in b.get("content", []) if x.get("type") == "text")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    s, en = text.find("{"), text.rfind("}")
                    return json.loads(text[s:en + 1])
            except (httpx.RemoteProtocolError, httpx.TransportError, httpx.TimeoutException) as ex:
                last = type(ex).__name__
                time.sleep(min(60, 2 ** attempt) + random.uniform(0, 1.5))
        raise RuntimeError(f"anthropic_failed_after_retries:{last}")

    def process(self, asset_id, run_id=None, dry_run=True):
        media, name, src, master = self.asset_meta(asset_id)
        if not src and not master:
            return {"asset_id": asset_id, "status": "NO_DRIVE_ID"}
        frames = self.frames_for(asset_id, media, src, master)
        if not frames:
            return {"asset_id": asset_id, "status": "NO_FRAMES"}  # never call model with 0 frames
        evidence_text = json.dumps({"filename": name, "media": media, "frames_supplied": len(frames)})
        if dry_run:
            prompt = build_prompt(evidence_text, self.vocab)
            return {"asset_id": asset_id, "status": "DRY_OK", "media": media, "frames": len(frames),
                    "prompt_chars": len(prompt), "vocab_layers": sorted(self.vocab)}
        # --- real path (consent-gated; not exercised in dry-run) ---
        parsed = self._analyze(frames, evidence_text)
        by = {L["layer_id"]: L for L in parsed.get("layers", []) if L.get("layer_id") in LAYER_IDS and L.get("state") in STATES}
        if set(LAYER_IDS) - set(by):
            raise RuntimeError("incomplete_layers")
        concepts = []
        for lid in LAYER_IDS:
            L = by[lid]
            if L["state"] != "OBSERVED":
                continue
            for c in (L.get("concepts") or []):
                concepts.append(finalize_concept(lid, c, self.resolver))
        apply_donor_precondition(concepts)
        payload = []
        for i, f in enumerate(concepts):
            payload.append(dict(id=str(uuid.uuid5(NS, f"{run_id}:{asset_id}:{i}")), asset_id=asset_id,
                scene_id=None, event_id=None, concept_type=f["concept_type"], canonical_code=f["canonical_code"],
                display_text=f["display_text"], source="AI_MODEL", semantic_state="OBSERVED",
                confidence=f["model_confidence"], search_critical=True, human_review_status="PENDING",
                analysis_run_id=run_id, assertion_id=None, evidence_ids=[], review_state=f["review_state"],
                raw_concept=f["raw_concept"], model_confidence=f["model_confidence"], resolution_method=f["resolution_method"]))
        if payload:
            self.db.table("asset_search_concepts_v2").insert(payload).execute()
        return {"asset_id": asset_id, "status": "COMPLETE", "concepts": len(payload)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", required=True)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--real", dest="dry_run", action="store_false")
    a = ap.parse_args()
    x = Extractor()
    print(json.dumps(x.process(a.asset, run_id=None, dry_run=a.dry_run), default=str))


if __name__ == "__main__":
    raise SystemExit(main())
