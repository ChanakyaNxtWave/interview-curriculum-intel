import type { ReviewStatus } from '../api/types';

const CLS: Record<ReviewStatus, string> = {
  pending: 'bg-status-pending/15 text-status-pending border-status-pending/40',
  needs_review: 'bg-status-needs/15 text-status-needs border-status-needs/40',
  approved: 'bg-status-approved/15 text-status-approved border-status-approved/40',
  rejected: 'bg-status-rejected/15 text-status-rejected border-status-rejected/40',
};

const LABEL: Record<ReviewStatus, string> = {
  pending: 'pending',
  needs_review: 'needs review',
  approved: 'approved',
  rejected: 'rejected',
};

export default function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${CLS[status]}`}>
      {LABEL[status]}
    </span>
  );
}
