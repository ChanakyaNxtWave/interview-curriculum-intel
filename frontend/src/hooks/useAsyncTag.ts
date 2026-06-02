import { useCallback, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { tagTheoryQuestion, type TagStartResponse } from '../api/theory';
import { tagCodingQuestion } from '../api/coding';

export interface TagProgressSession {
  requestedRowKey: string;
  tagRowKey: string;
  questionText: string;
  tracking: boolean;
  isCoding: boolean;
}

export function useAsyncTag(onComplete?: () => void) {
  const [session, setSession] = useState<TagProgressSession | null>(null);

  const startTag = useMutation({
    mutationFn: async ({
      rowKey,
      qt,
      questionText,
    }: {
      rowKey: string;
      qt: string;
      questionText: string;
    }) => {
      const fn = qt === 'CODING' ? tagCodingQuestion : tagTheoryQuestion;
      return fn(rowKey);
    },
    onSuccess: (data: TagStartResponse, vars) => {
      if (!data.started && !data.already_running) {
        return;
      }
      setSession({
        requestedRowKey: vars.rowKey,
        tagRowKey: data.tag_row_key,
        questionText: vars.questionText,
        tracking: true,
        isCoding: vars.qt === 'CODING',
      });
    },
    onError: () => {
      setSession(null);
    },
  });

  const beginTag = useCallback(
    (rowKey: string, qt: string, questionText: string) => {
      startTag.mutate({ rowKey, qt, questionText });
    },
    [startTag],
  );

  const finishTag = useCallback(() => {
    setSession(null);
    onComplete?.();
  }, [onComplete]);

  return {
    session,
    beginTag,
    finishTag,
    isStarting: startTag.isPending,
    startError: startTag.error,
    pendingRowKey: startTag.isPending ? startTag.variables?.rowKey : null,
  };
}
