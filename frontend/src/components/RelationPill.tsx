import { ArrowRight, Pencil, X } from 'lucide-react';
import type { RelationRecord } from '../types';
import { IconButton } from '../ui/Primitives';

type Props = {
  relation: RelationRecord;
  changeType?: 'added' | 'modified' | 'removed' | 'unchanged';
  onDelete?: (relationId: string) => void;
  onEdit?: (relation: RelationRecord) => void;
};

export default function RelationPill({ relation, changeType, onDelete, onEdit }: Props) {
  const changeLabel = changeType === 'added'
    ? 'New'
    : changeType === 'modified'
      ? 'Modified'
      : changeType === 'removed'
        ? 'Deleted'
        : '';

  return (
    <span className={`relation-pill${changeType ? ` relation-pill--${changeType}` : ''}`}>
      <span className="relation-pill__label">
        <span className="relation-pill__entity">{relation.subject_text}</span>
        <ArrowRight aria-hidden="true" size={12} />
        <strong>{relation.predicate}</strong>
        <ArrowRight aria-hidden="true" size={12} />
        <span className="relation-pill__entity">{relation.object_text}</span>
      </span>
      {changeLabel ? <span className="relation-pill__change-label">{changeLabel}</span> : null}
      {onEdit ? (
        <IconButton
          className="relation-pill__edit"
          icon={Pencil}
          label={`Edit ${relation.subject_text} ${relation.predicate} ${relation.object_text}`}
          onClick={() => onEdit(relation)}
        />
      ) : null}
      {onDelete ? (
        <IconButton
          className="relation-pill__delete"
          icon={X}
          label={`Delete ${relation.subject_text} ${relation.predicate} ${relation.object_text}`}
          onClick={() => onDelete(relation.logical_relation_id || relation.relation_id)}
        />
      ) : null}
    </span>
  );
}
