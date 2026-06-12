import { ArrowRight, X } from 'lucide-react';
import type { RelationRecord } from '../types';
import { IconButton } from '../ui/Primitives';

type Props = {
  relation: RelationRecord;
  onDelete?: (relationId: string) => void;
  supportLabelOverride?: string;
};

export default function RelationPill({ relation, onDelete, supportLabelOverride }: Props) {
  const supportLabel = supportLabelOverride || relation.support_paragraph_id || relation.support_sentence_ids;

  return (
    <span className="relation-pill">
      <span className="relation-pill__label">
        <span className="relation-pill__entity">{relation.subject_text}</span>
        <ArrowRight aria-hidden="true" size={12} />
        <strong>{relation.predicate}</strong>
        <ArrowRight aria-hidden="true" size={12} />
        <span className="relation-pill__entity">{relation.object_text}</span>
      </span>
      {supportLabel ? <span className="relation-pill__support">{supportLabel}</span> : null}
      {onDelete ? (
        <IconButton
          className="relation-pill__delete"
          icon={X}
          label={`Delete ${relation.subject_text} ${relation.predicate} ${relation.object_text}`}
          onClick={() => onDelete(relation.relation_id)}
        />
      ) : null}
    </span>
  );
}
