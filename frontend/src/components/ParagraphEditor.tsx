import { useEffect, useMemo, useState } from 'react';
import { Eraser, MessageSquareText, MousePointer2, Plus } from 'lucide-react';
import type { MentionRecord, ModifiedRelationRecord, ParagraphCommentChange, ParagraphRecord, RelationRecord, SentenceRecord } from '../types';
import RelationPill from './RelationPill';
import {
  buildCustomParagraphRelation,
  buildManualRelation,
  mentionLabel,
  mentionTypeValue,
  sentenceSegments,
} from './editorUtils';
import { Button, EmptyState, Field } from '../ui/Primitives';

export type ParagraphRevisionChanges = {
  parentVersion: number;
  addedRelationIds: Set<string>;
  removedRelations: RelationRecord[];
  modifiedRelations: ModifiedRelationRecord[];
  commentChange?: ParagraphCommentChange;
};

function relationIdentity(relation: RelationRecord) {
  return relation.logical_relation_id || relation.relation_id;
}

type Props = {
  paperId: string;
  paperTitle: string;
  doi: string;
  paragraph: ParagraphRecord;
  sentences: SentenceRecord[];
  mentionsBySentence: Map<string, MentionRecord[]>;
  relations: RelationRecord[];
  revisionChanges?: ParagraphRevisionChanges;
  comment: string;
  onAddPredicate: (predicate: string) => Promise<void>;
  onDelete: (relationId: string) => void;
  onAdd: (relation: RelationRecord) => void;
  onUpdate: (relation: RelationRecord) => void;
  onCommentChange: (commentText: string) => void;
  readOnly?: boolean;
  commentReadOnly?: boolean;
};

export default function ParagraphEditor({
  paperId,
  paperTitle,
  doi,
  paragraph,
  sentences,
  mentionsBySentence,
  relations,
  revisionChanges,
  comment,
  onAddPredicate,
  onDelete,
  onAdd,
  onUpdate,
  onCommentChange,
  readOnly = false,
  commentReadOnly = readOnly,
}: Props) {
  const [selectedMentionIds, setSelectedMentionIds] = useState<string[]>([]);
  const [selectedRelation, setSelectedRelation] = useState('');
  const [isSavingSelectedRelation, setIsSavingSelectedRelation] = useState(false);
  const [customHead, setCustomHead] = useState('');
  const [customRelation, setCustomRelation] = useState('');
  const [customTail, setCustomTail] = useState('');
  const [editingRelation, setEditingRelation] = useState<RelationRecord | null>(null);

  const modifiedRelationIds = useMemo(
    () => new Set(revisionChanges?.modifiedRelations.map((change) => relationIdentity(change.after)) ?? []),
    [revisionChanges?.modifiedRelations]
  );
  const changedRelations = relations.filter((relation) => (
    revisionChanges?.addedRelationIds.has(relationIdentity(relation))
    || modifiedRelationIds.has(relationIdentity(relation))
  ));
  const unchangedRelations = relations.filter((relation) => (
    !revisionChanges?.addedRelationIds.has(relationIdentity(relation))
    && !modifiedRelationIds.has(relationIdentity(relation))
  ));
  const orderedRelations = [...changedRelations, ...unchangedRelations];
  const removedRelations = revisionChanges?.removedRelations ?? [];
  const commentChangeLabel = revisionChanges?.commentChange
    ? revisionChanges.commentChange.before_text && revisionChanges.commentChange.after_text
      ? 'Comment modified'
      : revisionChanges.commentChange.after_text
        ? 'Comment added'
        : 'Comment deleted'
    : '';

  const mentionsById = useMemo(() => {
    const pairs = paragraph.sentence_ids.flatMap((sentenceId) =>
      (mentionsBySentence.get(sentenceId) ?? [])
        .filter((mention) => mention.text.trim().length > 0)
        .map((mention) => [mention.mention_id, mention] as const)
    );
    return new Map<string, MentionRecord>(pairs);
  }, [mentionsBySentence, paragraph.sentence_ids]);

  const selectedMentions = selectedMentionIds
    .map((mentionId) => mentionsById.get(mentionId))
    .filter((mention): mention is MentionRecord => Boolean(mention));

  useEffect(() => {
    setSelectedMentionIds((current) => current.filter((mentionId) => mentionsById.has(mentionId)).slice(0, 2));
  }, [mentionsById]);

  useEffect(() => {
    if (editingRelation && !relations.some((relation) => relation.logical_relation_id === editingRelation.logical_relation_id)) {
      setEditingRelation(null);
    }
  }, [editingRelation, relations]);

  const toggleMention = (mentionId: string) => {
    if (readOnly) return;
    setSelectedMentionIds((current) => {
      if (current.includes(mentionId)) {
        return current.filter((id) => id !== mentionId);
      }
      if (current.length < 2) {
        return [...current, mentionId];
      }
      return [current[1], mentionId];
    });
  };

  const canAddCustomRelation = Boolean(customHead.trim() && customRelation.trim() && customTail.trim());

  const handleAddSelectedRelation = async () => {
    const predicate = selectedRelation.trim();
    if (selectedMentions.length !== 2 || !predicate) return;
    const supportSentenceIds = Array.from(new Set(selectedMentions.map((mention) => mention.sentence_id)));
    const evidenceText = supportSentenceIds.length === 1
      ? sentences.find((sentence) => sentence.sentence_id === supportSentenceIds[0])?.text ?? paragraph.text
      : paragraph.text;

    setIsSavingSelectedRelation(true);
    try {
      await onAddPredicate(predicate);
      onAdd(buildManualRelation({
        paperId,
        paperTitle,
        doi,
        predicate,
        evidenceText,
        subject: selectedMentions[0],
        object: selectedMentions[1],
        supportSentenceIds,
        supportParagraphId: paragraph.paragraph_id,
      }));
      setSelectedRelation('');
      setSelectedMentionIds([]);
    } finally {
      setIsSavingSelectedRelation(false);
    }
  };

  const handleAddCustomRelation = () => {
    if (!canAddCustomRelation) return;
    onAdd(buildCustomParagraphRelation({
      paperId,
      paperTitle,
      doi,
      paragraphId: paragraph.paragraph_id,
      paragraphText: paragraph.text,
      subjectText: customHead.trim(),
      predicate: customRelation.trim(),
      objectText: customTail.trim(),
    }));
    setCustomHead('');
    setCustomRelation('');
    setCustomTail('');
  };

  return (
    <section className="sentence-card paragraph-card" data-progress-index={paragraph.paragraph_index}>
      <div className="paragraph-card__header">
        <div>
          <span className="paragraph-kicker">Paragraph</span>
          <h3>{paragraph.paragraph_index}</h3>
        </div>
      </div>

      <div className="paragraph-text">
        {sentences.length === 0 ? (
          <>
            {paragraph.text}
            <p className="paragraph-text__notice">Entity highlights are unavailable for this paragraph because sentence alignment could not be inferred.</p>
          </>
        ) : sentences.map((sentence) => (
          <span key={sentence.sentence_id}>
            {sentenceSegments(sentence.text, mentionsBySentence.get(sentence.sentence_id) ?? []).map((segment, index) => (
              <span key={`${sentence.sentence_id}-${index}`}>
                {segment.kind === 'mention' ? (
                  <button
                    type="button"
                    className={`mention mention--typed mention-button ${selectedMentionIds.includes(segment.mention.mention_id) ? 'mention-button--selected' : ''}`}
                    onClick={() => toggleMention(segment.mention.mention_id)}
                    disabled={readOnly}
                    title={`${mentionLabel(segment.mention)} (${segment.mention.sentence_id})`}
                  >
                    {segment.text}
                  </button>
                ) : (
                  segment.text
                )}
                {' '}
              </span>
            ))}
          </span>
        ))}
      </div>

      <div className="paragraph-actions">
        <div className="relation-panel">
          <div className="relation-panel__header">
            <strong>Relations</strong>
            <div className="relation-panel__summary">
              <span>{relations.length} current</span>
              {revisionChanges ? (
                <div className="relation-change-counts" aria-label={`Changes since version ${revisionChanges.parentVersion}`}>
                  <span className="relation-change-count relation-change-count--added">+{revisionChanges.addedRelationIds.size} new</span>
                  <span className="relation-change-count relation-change-count--modified">~{revisionChanges.modifiedRelations.length} modified</span>
                  <span className="relation-change-count relation-change-count--removed">−{removedRelations.length} deleted</span>
                </div>
              ) : null}
            </div>
          </div>
          <div className="pill-row">
            {orderedRelations.length > 0 || removedRelations.length > 0 ? (
              <>
                {changedRelations.map((relation) => (
                  <RelationPill
                    key={relation.logical_relation_id || relation.relation_id}
                    relation={relation}
                    changeType={revisionChanges?.addedRelationIds.has(relationIdentity(relation)) ? 'added' : 'modified'}
                    onDelete={readOnly ? undefined : onDelete}
                    onEdit={readOnly ? undefined : setEditingRelation}
                  />
                ))}
                {removedRelations.map((relation) => (
                  <RelationPill
                    key={`removed-${relation.logical_relation_id || relation.relation_id}`}
                    relation={relation}
                    changeType="removed"
                  />
                ))}
                {unchangedRelations.map((relation) => (
                  <RelationPill
                    key={relation.logical_relation_id || relation.relation_id}
                    relation={relation}
                    changeType={revisionChanges ? 'unchanged' : undefined}
                    onDelete={readOnly ? undefined : onDelete}
                    onEdit={readOnly ? undefined : setEditingRelation}
                  />
                ))}
              </>
            ) : (
              <EmptyState icon={MousePointer2} title="No relations attached" description={readOnly ? "No relations are present in this version." : "Select two highlighted entities or add a free-form relation below."} />
            )}
          </div>
          {revisionChanges && revisionChanges.modifiedRelations.length > 0 ? (
            <div className="relation-modification-list">
              <div className="relation-modification-list__heading">
                <strong>Modified relation details</strong>
                <span>Compared with version {revisionChanges.parentVersion}</span>
              </div>
              {revisionChanges.modifiedRelations.map((change) => (
                <div className="relation-modification" key={`modified-${relationIdentity(change.after)}`}>
                  <div>
                    <span className="relation-modification__label">Before</span>
                    <p>{change.before.subject_text} — <strong>{change.before.predicate}</strong> — {change.before.object_text}</p>
                  </div>
                  <div>
                    <span className="relation-modification__label">After</span>
                    <p>{change.after.subject_text} — <strong>{change.after.predicate}</strong> — {change.after.object_text}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {editingRelation ? (
            <div className="relation-inline-editor">
              <div className="relation-inline-editor__heading">
                <strong>Edit relation</strong>
                <span>The relation keeps the same identity, so this appears as modified in version comparison.</span>
              </div>
              <div className="add-relation-form add-relation-form--paragraph">
                <Field label="Head">
                  <input
                    type="text"
                    value={editingRelation.subject_text}
                    onChange={(event) => setEditingRelation({ ...editingRelation, subject_text: event.target.value })}
                  />
                </Field>
                <Field label="Relation">
                  <input
                    type="text"
                    value={editingRelation.predicate}
                    onChange={(event) => setEditingRelation({ ...editingRelation, predicate: event.target.value })}
                  />
                </Field>
                <Field label="Tail">
                  <input
                    type="text"
                    value={editingRelation.object_text}
                    onChange={(event) => setEditingRelation({ ...editingRelation, object_text: event.target.value })}
                  />
                </Field>
                <Button variant="secondary" onClick={() => setEditingRelation(null)}>Cancel</Button>
                <Button
                  variant="success"
                  onClick={() => {
                    onUpdate(editingRelation);
                    setEditingRelation(null);
                  }}
                  disabled={!editingRelation.subject_text.trim() || !editingRelation.predicate.trim() || !editingRelation.object_text.trim()}
                >
                  Apply edit
                </Button>
              </div>
            </div>
          ) : null}
        </div>

        {!readOnly ? (
          <>
        <div className="relation-composer">
          <div className="paragraph-selection">
            <span className="paragraph-selection__label">Selected entities</span>
            <span className="paragraph-selection__value">
              {selectedMentions.length > 0
                ? selectedMentions.map((mention) => `${mention.text} [${mentionTypeValue(mention)}]`).join(' -> ')
                : 'Click highlighted entities in the paragraph'}
            </span>
          </div>
          <div className="add-relation-form add-relation-form--paragraph-selected">
            <Field label="Predicate">
              <input
                type="text"
                value={selectedRelation}
                onChange={(event) => setSelectedRelation(event.target.value)}
                placeholder="e.g. measures, generates, hasMedium"
              />
            </Field>
            <Button variant="secondary" icon={Eraser} onClick={() => setSelectedMentionIds([])} disabled={selectedMentionIds.length === 0}>
              Clear
            </Button>
            <Button
              variant="success"
              icon={Plus}
              onClick={handleAddSelectedRelation}
              disabled={selectedMentions.length !== 2 || !selectedRelation.trim() || isSavingSelectedRelation}
            >
              {isSavingSelectedRelation ? 'Adding...' : 'Add selected'}
            </Button>
          </div>
        </div>

        <div className="relation-composer relation-composer--quiet">
          <div className="relation-composer__title">Free-form relation</div>
          <div className="add-relation-form add-relation-form--paragraph">
            <Field label="Head">
              <input
                type="text"
                value={customHead}
                onChange={(event) => setCustomHead(event.target.value)}
                placeholder="Subject"
              />
            </Field>
            <Field label="Relation">
              <input
                type="text"
                value={customRelation}
                onChange={(event) => setCustomRelation(event.target.value)}
                placeholder="Predicate"
              />
            </Field>
            <Field label="Tail">
              <input
                type="text"
                value={customTail}
                onChange={(event) => setCustomTail(event.target.value)}
                placeholder="Object"
              />
            </Field>
            <Button icon={Plus} onClick={handleAddCustomRelation} disabled={!canAddCustomRelation}>
              Add free-form
            </Button>
          </div>
        </div>
          </>
        ) : null}
      </div>

      <section className={`paragraph-comment${commentReadOnly ? ' paragraph-comment--read-only' : ''}`}>
        <div className="paragraph-comment__header">
          <label className="paragraph-comment__label" htmlFor={`paragraph-comment-${paragraph.paragraph_id}`}>
            <span className="paragraph-comment__icon"><MessageSquareText aria-hidden="true" size={17} /></span>
            <span>
              <strong>Paragraph relation notes</strong>
              <small>Comments and context for this paragraph's relations</small>
            </span>
          </label>
          {commentChangeLabel ? <span className="paragraph-comment__change">{commentChangeLabel}</span> : null}
        </div>
        <textarea
          id={`paragraph-comment-${paragraph.paragraph_id}`}
          value={comment}
          onChange={(event) => onCommentChange(event.target.value)}
          placeholder={commentReadOnly ? 'No comment was added for this paragraph.' : 'Add notes, uncertainties, or context about the relations in this paragraph...'}
          rows={3}
          readOnly={commentReadOnly}
        />
        {revisionChanges?.commentChange ? (
          <details className="paragraph-comment__history">
            <summary>Compare with version {revisionChanges.parentVersion}</summary>
            <div><span>Before</span><p>{revisionChanges.commentChange.before_text || '(No comment)'}</p></div>
            <div><span>After</span><p>{revisionChanges.commentChange.after_text || '(No comment)'}</p></div>
          </details>
        ) : null}
        {!commentReadOnly ? <span className="paragraph-comment__hint">Saved with the current annotation submission.</span> : null}
      </section>
    </section>
  );
}
