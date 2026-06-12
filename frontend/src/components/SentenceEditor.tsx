import AddRelationForm from './AddRelationForm';
import RelationPill from './RelationPill';
import type { MentionRecord, RelationRecord, SentenceRecord } from '../types';
import { mentionLabel, sentenceSegments } from './editorUtils';

type Props = {
  paperId: string;
  paperTitle: string;
  doi: string;
  sentence: SentenceRecord;
  mentions: MentionRecord[];
  relations: RelationRecord[];
  predicates: string[];
  onDelete: (relationId: string) => void;
  onAdd: (relation: RelationRecord) => void;
};

export default function SentenceEditor({ paperId, paperTitle, doi, sentence, mentions, relations, predicates, onDelete, onAdd }: Props) {
  return (
    <section className="sentence-card" data-progress-index={sentence.sentence_index}>
      <h3>Sentence {sentence.sentence_index}</h3>
      <p className="sentence-text">
        {sentenceSegments(sentence.text, mentions).map((segment, index) => (
          <span key={`${sentence.sentence_id}-${index}`}>
            {index > 0 ? ' ' : null}
            {segment.kind === 'mention' ? (
              <mark
                className={segment.typed ? 'mention mention--typed' : 'mention'}
                title={mentionLabel(segment.mention)}
              >
                {segment.text}
              </mark>
            ) : (
              segment.text
            )}
          </span>
        ))}
      </p>
      <div className="pill-row">
        {relations.length > 0 ? (
          relations.map((relation) => <RelationPill key={relation.relation_id} relation={relation} onDelete={onDelete} />)
        ) : (
          <p className="muted">No relations currently attached to this sentence.</p>
        )}
      </div>
      <AddRelationForm
        paperId={paperId}
        paperTitle={paperTitle}
        doi={doi}
        sentenceId={sentence.sentence_id}
        sentenceText={sentence.text}
        mentions={mentions}
        predicates={predicates}
        onAdd={onAdd}
      />
    </section>
  );
}
