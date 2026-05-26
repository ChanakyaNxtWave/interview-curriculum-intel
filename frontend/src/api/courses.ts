import { api } from './client';
import type { CoursesResponse } from './types';

export const fetchCourses = () => api<CoursesResponse>('/api/courses');
