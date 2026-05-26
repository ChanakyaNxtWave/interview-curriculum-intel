import { api, qs } from './client';
import type { Mapping, MappingsResponse } from './types';

export interface MappingsFilters {
  review_status?: string;
  needs_human_review?: boolean | string;
  content_type?: string;
  topic_name?: string;
  kp_id?: string;
  confidence?: string;
  has_tags?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export const fetchMappings = (f: MappingsFilters = {}) =>
  api<MappingsResponse>(`/api/mappings${qs(f)}`);

export const fetchMapping = (contentId: string) =>
  api<Mapping>(`/api/mappings/${encodeURIComponent(contentId)}`);

export const fetchFacets = () =>
  api<{ topics: string[]; content_types: string[] }>('/api/mappings/facets');

export interface ContentBody {
  content_id: string;
  title: string;
  topic_name?: string | null;
  course_title?: string | null;
  content_type: string;
  body_text: string;
  solution_text?: string | null;
}

export const fetchContentBody = (contentId: string) =>
  api<ContentBody>(`/api/content/${encodeURIComponent(contentId)}/body`);
