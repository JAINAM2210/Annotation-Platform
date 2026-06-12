import { useEffect, useMemo, useState } from 'react';
import type { MentionRecord, RelationRecord } from '../types';
import { SelectControl } from '../ui/Primitives';
import { buildManualRelation, mentionOptionLabel, typedMentionsOnly } from './editorUtils';

type Props = {
  paperId: string;
  paperTitle: string;
  doi: string;
  sentenceId: string;
  sentenceText: string;
  mentions: MentionRecord[];
  predicates: string[];
  onAdd: (relation: RelationRecord) => void;
};

export default function AddRelationForm({ paperId, paperTitle, doi, sentenceId, sentenceText, mentions, predicates, onAdd }: Props) {
  const entityMentions = useMemo(
    () => typedMentionsOnly(mentions),
    [mentions]
  );
  const options = useMemo(
    () => entityMentions.map(mentionOptionLabel),
    [entityMentions]
  );
  const entityOptions = useMemo(
    () => options.map((label) => ({ value: label, label })),
    [options]
  );
  const predicateOptions = useMemo(
    () => predicates.map((item) => ({ value: item, label: item })),
    [predicates]
  );
  const [subject, setSubject] = useState(options[0] ?? '');
  const [predicate, setPredicate] = useState(predicates[0] ?? '');
  const [object, setObject] = useState(options[1] ?? options[0] ?? '');

  useEffect(() => {
    setSubject(options[0] ?? '');
    setObject(options[1] ?? options[0] ?? '');
  }, [options]);

  useEffect(() => {
    setPredicate((current) => (predicates.includes(current) ? current : predicates[0] ?? ''));
  }, [predicates]);

  if (entityMentions.length < 2) {
    return <p className="muted">Need at least two typed sentence entities before adding a relation here.</p>;
  }

  const parseEntity = (label: string) => entityMentions.find((item) => mentionOptionLabel(item) === label) ?? entityMentions[0];

  return (
    <div className="add-relation-form">
      <SelectControl value={subject} options={entityOptions} onChange={setSubject} ariaLabel="Choose relation subject" />
      <SelectControl value={predicate} options={predicateOptions} onChange={setPredicate} ariaLabel="Choose relation predicate" placeholder="No predicates available" disabled={predicateOptions.length === 0} />
      <SelectControl value={object} options={entityOptions} onChange={setObject} ariaLabel="Choose relation object" />
      <button type="button" onClick={() => {
        const subjectEntity = parseEntity(subject);
        const objectEntity = parseEntity(object);
        onAdd(buildManualRelation({
          paperId,
          paperTitle,
          doi,
          predicate,
          evidenceText: sentenceText,
          subject: subjectEntity,
          object: objectEntity,
          supportSentenceIds: [sentenceId],
        }));
      }}>Add relation</button>
    </div>
  );
}
