import { api, qs } from './client';
import type { KpsWithCountsResponse } from './types';

export interface KpsFilters {
  course_id?: string;
  q?: string;
  min_content_count?: number;
  tag_role?: string;
  limit?: number;
}

export const fetchKpsWithCounts = (f: KpsFilters = {}) =>
  api<KpsWithCountsResponse>(`/api/kps/with-counts${qs(f)}`);
