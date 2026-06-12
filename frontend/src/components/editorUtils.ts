import type { MentionRecord, RelationRecord } from '../types';

export type SentenceSegment =
  | { kind: 'text'; text: string }
  | { kind: 'mention'; mention: MentionRecord; text: string; typed: boolean };

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function mentionLabel(mention: MentionRecord) {
  return mention.schema_type || mention.ner_label || 'Mention';
}

export function mentionTypeValue(mention: MentionRecord) {
  return mention.schema_type || mention.ner_label || 'Mention';
}

export function typedMentionsOnly(mentions: MentionRecord[]) {
  return mentions.filter((mention) => mention.schema_type && mention.schema_type.trim().length > 0);
}

export function mentionOptionLabel(mention: MentionRecord) {
  return `${mention.text} [${mention.schema_type}]`;
}

function normalizeMentionText(value: string) {
  return value.replace(/\s+/g, ' ').trim().toLowerCase();
}

function rangeIsAvailable(start: number, end: number, occupied: Set<number>) {
  for (let idx = start; idx <= end; idx += 1) {
    if (occupied.has(idx)) return false;
  }
  return true;
}

function findMentionRange(tokens: string[], mention: MentionRecord, occupied: Set<number>) {
  const expected = normalizeMentionText(mention.text);
  const offsetStart = mention.token_start ?? -1;
  const offsetEnd = mention.token_end ?? -1;

  if (offsetStart >= 0 && offsetEnd >= offsetStart && offsetEnd < tokens.length) {
    const offsetText = normalizeMentionText(tokens.slice(offsetStart, offsetEnd + 1).join(' '));
    if (offsetText === expected && rangeIsAvailable(offsetStart, offsetEnd, occupied)) {
      return { start: offsetStart, end: offsetEnd };
    }
  }

  const mentionTokenCount = mention.text.trim().split(/\s+/).filter(Boolean).length;
  if (!expected || mentionTokenCount === 0 || mentionTokenCount > tokens.length) return null;

  for (let start = 0; start <= tokens.length - mentionTokenCount; start += 1) {
    const end = start + mentionTokenCount - 1;
    if (!rangeIsAvailable(start, end, occupied)) continue;
    const candidate = normalizeMentionText(tokens.slice(start, end + 1).join(' '));
    if (candidate === expected) return { start, end };
  }

  return null;
}

export function sentenceSegments(text: string, mentions: MentionRecord[]): SentenceSegment[] {
  const tokens = text.split(' ');
  if (tokens.length === 0 || mentions.length === 0) {
    return [{ kind: 'text', text }];
  }

  const sortedMentions = [...mentions]
    .filter((mention) => mention.text.trim())
    .sort((a, b) => {
      const startDiff = (a.token_start ?? Number.MAX_SAFE_INTEGER) - (b.token_start ?? Number.MAX_SAFE_INTEGER);
      if (startDiff !== 0) return startDiff;
      return (b.token_end ?? 0) - (a.token_end ?? 0);
    });

  const occupied = new Set<number>();
  const rendered = new Map<number, { end: number; mention: MentionRecord; text: string; typed: boolean }>();

  sortedMentions.forEach((mention) => {
    const range = findMentionRange(tokens, mention, occupied);
    if (!range) return;
    for (let idx = range.start; idx <= range.end; idx += 1) {
      occupied.add(idx);
    }
    rendered.set(range.start, {
      end: range.end,
      mention,
      text: tokens.slice(range.start, range.end + 1).join(' '),
      typed: Boolean(mention.schema_type && mention.schema_type.trim()),
    });
  });

  const parts: SentenceSegment[] = [];
  let index = 0;
  while (index < tokens.length) {
    const mark = rendered.get(index);
    if (mark) {
      parts.push({
        kind: 'mention',
        mention: mark.mention,
        text: mark.text,
        typed: mark.typed,
      });
      index = mark.end + 1;
      continue;
    }
    parts.push({ kind: 'text', text: tokens[index] });
    index += 1;
  }

  return parts;
}

export function highlightSentence(text: string, mentions: MentionRecord[]) {
  return sentenceSegments(text, mentions)
    .map((segment) => {
      if (segment.kind === 'text') return escapeHtml(segment.text);
      const className = segment.typed ? 'mention mention--typed' : 'mention';
      return `<mark class="${className}" title="${escapeHtml(mentionLabel(segment.mention))}">${escapeHtml(segment.text)}</mark>`;
    })
    .join(' ');
}

export function buildManualRelation(args: {
  paperId: string;
  paperTitle: string;
  doi: string;
  predicate: string;
  evidenceText: string;
  subject: MentionRecord;
  object: MentionRecord;
  supportSentenceIds?: string[];
  supportParagraphId?: string;
}) {
  const supportSentenceIds = args.supportSentenceIds?.filter(Boolean) ?? [args.subject.sentence_id];

  const relation: RelationRecord = {
    relation_id: `manual_${Date.now()}_${args.subject.mention_id}_${args.object.mention_id}`,
    sentence_id: supportSentenceIds[0] ?? args.subject.sentence_id,
    paper_id: args.paperId,
    paper_title: args.paperTitle,
    doi: args.doi,
    subject_text: args.subject.text,
    subject_type: mentionTypeValue(args.subject),
    predicate: args.predicate,
    object_text: args.object.text,
    object_type: mentionTypeValue(args.object),
    confidence: 1.0,
    accepted: true,
    evidence_text: args.evidenceText,
    relation_origin: 'manual_edit',
    inherited_from: '',
    support_sentence_ids: supportSentenceIds.join(';'),
    support_paragraph_id: args.supportParagraphId ?? '',
  };

  return relation;
}

export function buildCustomParagraphRelation(args: {
  paperId: string;
  paperTitle: string;
  doi: string;
  paragraphId: string;
  subjectText: string;
  predicate: string;
  objectText: string;
}) {
  const relation: RelationRecord = {
    relation_id: `custom_${Date.now()}_${args.paragraphId}`,
    sentence_id: '',
    paper_id: args.paperId,
    paper_title: args.paperTitle,
    doi: args.doi,
    subject_text: args.subjectText,
    subject_type: 'custom',
    predicate: args.predicate,
    object_text: args.objectText,
    object_type: 'custom',
    confidence: 1.0,
    accepted: true,
    evidence_text: '',
    relation_origin: '',
    inherited_from: '',
    support_sentence_ids: '',
    support_paragraph_id: args.paragraphId,
  };

  return relation;
}
