import type { MediaCategory } from "../lib/library/classification";

export type MediaSort = "newest" | "oldest" | "smallest" | "largest";
export type MediaAsset = {
  id: string; sourceFileId: string | null; filename: string; extension: string | null;
  mimeType: string | null; category: MediaCategory; sizeBytes: number | null;
  createdAt: string | null; modifiedAt: string | null; sourceFolder: string;
  storageDestination: "google-drive" | null; migrationStatus: string; verificationStatus: string;
  canPreview: boolean; canDownload: boolean; previewUrl: string | null; downloadUrl: string | null;
  thumbnailUrl?: string | null;
  /** One-sentence display caption from the semantic index. Null until indexed. */
  shortCaption: string | null;
  /**
   * Query-specific hybrid-search relevance, 0-100. Always null outside an
   * active natural-language search — never render a match badge otherwise.
   */
  matchPercent: number | null;
};

/** Full structured metadata for the preview/detail screen. Never includes the embedding. */
export type MediaSemanticDetail = {
  contentType: string | null;
  treatment: string | null;
  subject: string | null;
  doctorName: string | null;
  aiDescription: string | null;
};
export type MediaPage = { items: MediaAsset[]; total: number; page: number; pageSize: number; totalPages: number };
export type MediaQuery = { page: number; pageSize: number; search: string; category: MediaCategory | ""; extension: string; sort: MediaSort };
