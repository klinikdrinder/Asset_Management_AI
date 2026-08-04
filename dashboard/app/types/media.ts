import type { MediaCategory } from "../lib/library/classification";

export type MediaSort = "newest" | "oldest" | "smallest" | "largest";
export type MediaAsset = {
  id: string; sourceFileId: string | null; filename: string; extension: string | null;
  mimeType: string | null; category: MediaCategory; sizeBytes: number | null;
  createdAt: string | null; modifiedAt: string | null; sourceFolder: string;
  storageDestination: "google-drive" | null; migrationStatus: string; verificationStatus: string;
  canPreview: boolean; canDownload: boolean; previewUrl: string | null; downloadUrl: string | null;
};
export type MediaPage = { items: MediaAsset[]; total: number; page: number; pageSize: number; totalPages: number };
export type MediaQuery = { page: number; pageSize: number; search: string; category: MediaCategory | ""; extension: string; sort: MediaSort };
