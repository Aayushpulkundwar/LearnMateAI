"""Small, auditable tutor reranking inside the existing hybrid candidate pool."""
import re

QUESTION_WORDS = set('a an the is are was were be being been what how why when where which who do does did can could would should explain describe define tell me please give difference between and or of to in on for with happens examples example'.split())


def lexical_query(question):
    # Preserve the natural question for BGE-M3; remove instruction/question
    # boilerplate only for full-text matching, where it otherwise becomes ANDs.
    terms = list(dict.fromkeys(word for word in re.findall(r'\w+', question.casefold()) if word not in QUESTION_WORDS))
    return ' '.join(terms) or question.strip()


def _stem(word):
    return word[:-1] if len(word) > 4 and word.endswith('s') and not word.endswith(('ss', 'sis', 'us')) else word


def evidence_tier(content, question):
    """Prefer explanatory prose over a worksheet that merely repeats the query.

    This is a ranking signal, not factual entailment or a new relevance gate.
    Original vector and lexical scores remain intact for audit/citations.
    """
    terms = {_stem(word) for word in lexical_query(question).split()}
    text = ' '.join(content.split())
    sentences = re.split(r'(?<=[.!?])\s+', text)
    declarative = [sentence for sentence in sentences if '?' not in sentence and not re.match(r'^(?:\d+[.)]?\s*)?(?:write|explain|identify|name|give|what|why|which)\b', sentence, re.I)]
    explanatory = any(terms & {_stem(word) for word in re.findall(r'\w+', sentence.casefold())}
                      and re.search(r'\b(is|are|occurs|known|called|form|forms|formed|produce|produces|change|changes|displace|displaced|react|reaction)\b', sentence, re.I)
                      for sentence in declarative)
    exercise = bool(re.search(r'\b(?:EXERCISES|QUESTIONS)\b', content)) or len(re.findall(r'\b(?:Write|Explain|Name|Identify|Give)\b', content)) >= 3
    return 2 if explanatory and not exercise else 1 if explanatory or not exercise else 0


def prioritize_explanations(chunks, question):
    if re.search(r'\b(?:exercise|question)\s*#?\s*\d+', question, re.I):
        return list(chunks)
    return [chunk for _, chunk in sorted(enumerate(chunks), key=lambda pair: (-evidence_tier(pair[1].content, question), pair[0]))]
