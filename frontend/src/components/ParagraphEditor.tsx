import { useEffect, useMemo, useState } from 'react';
import { Eraser, MousePointer2, Plus } from 'lucide-react';
import type { MentionRecord, ParagraphRecord, RelationRecord, SentenceRecord } from '../types';
import RelationPill from './RelationPill';
import {
  buildCustomParagraphRelation,
  buildManualRelation,
  mentionLabel,
  mentionTypeValue,
  sentenceSegments,
} from './editorUtils';
import { Button, EmptyState, Field } from '../ui/Primitives';

type Props = {
  paperId: string;
  paperTitle: string;
  doi: string;
  paragraph: ParagraphRecord;
  sentences: SentenceRecord[];
  mentionsBySentence: Map<string, MentionRecord[]>;
  relations: RelationRecord[];
  onAddPredicate: (predicate: string) => Promise<void>;
  onDelete: (relationId: string) => void;
  onAdd: (relation: RelationRecord) => void;
  readOnly?: boolean;
};

export default function ParagraphEditor({
  paperId,
  paperTitle,
  doi,
  paragraph,
  sentences,
  mentionsBySentence,
  relations,
  onAddPredicate,
  onDelete,
  onAdd,
  readOnly = false,
}: Props) {
  const [selectedMentionIds, setSelectedMentionIds] = useState<string[]>([]);
  const [selectedRelation, setSelectedRelation] = useState('');
  const [isSavingSelectedRelation, setIsSavingSelectedRelation] = useState(false);
  const [customHead, setCustomHead] = useState('');
  const [customRelation, setCustomRelation] = useState('');
  const [customTail, setCustomTail] = useState('');

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
        <p className="muted">
          {paragraph.sentence_ids.length} sentence{paragraph.sentence_ids.length === 1 ? '' : 's'}
        </p>
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
            <span>{relations.length}</span>
          </div>
          <div className="pill-row">
            {relations.length > 0 ? (
              relations.map((relation) => (
                <RelationPill
                  key={relation.relation_id}
                  relation={relation}
                  supportLabelOverride={paragraph.paragraph_id}
                  onDelete={readOnly ? undefined : onDelete}
                />
              ))
            ) : (
              <EmptyState icon={MousePointer2} title="No relations attached" description={readOnly ? "No relations are present in this version." : "Select two highlighted entities or add a free-form relation below."} />
            )}
          </div>
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
    </section>
  );
}
