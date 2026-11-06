"""Structural quality checks, not claims of automatic factual entailment."""
from difflib import SequenceMatcher
from collections import Counter
import re
from app.evaluation.faithfulness import SOURCE_PATTERN, audit_answer

SPECIES = r'(?:\d+\s*)?(?:[A-Z][a-z]?\d*|\([A-Za-z0-9]+\)\d*)+(?:\((?:s|l|g|aq)\))?(?![A-Za-z0-9])'
REACTION = re.compile(r'(?<![\w/])(' + SPECIES + r'(?:\s*\+\s*' + SPECIES + r')*)\s*(?:→|->)\s*(' + SPECIES + r'(?:\s*\+\s*' + SPECIES + r')*)')


def formula_atoms(formula):
    formula = re.sub(r'\((?:s|l|g|aq)\)$', '', formula.strip())
    coefficient = re.match(r'^(\d+)\s*', formula)
    multiplier = int(coefficient[1]) if coefficient else 1
    if coefficient: formula = formula[coefficient.end():]
    tokens = re.findall(r'[A-Z][a-z]?|\d+|[()]', formula)
    if ''.join(tokens) != formula or not tokens: return None
    stack, index = [Counter()], 0
    while index < len(tokens):
        token = tokens[index]
        if token == '(':
            stack.append(Counter()); index += 1; continue
        if token == ')':
            if len(stack) == 1: return None
            group = stack.pop(); index += 1
            count = int(tokens[index]) if index < len(tokens) and tokens[index].isdigit() else 1
            if index < len(tokens) and tokens[index].isdigit(): index += 1
            stack[-1].update({element: value*count for element, value in group.items()}); continue
        if token.isdigit(): return None
        index += 1
        count = int(tokens[index]) if index < len(tokens) and tokens[index].isdigit() else 1
        if index < len(tokens) and tokens[index].isdigit(): index += 1
        stack[-1][token] += count
    return Counter({element: count*multiplier for element, count in stack[0].items()}) if len(stack) == 1 else None


def equation_issues(answer):
    normalized = answer.translate(str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789'))
    for match in REACTION.finditer(normalized):
        sides = []
        for side in [match[1], match[2]]:
            species = [formula_atoms(part) for part in side.split('+')]
            if any(atoms is None for atoms in species): break
            total = Counter()
            for atoms in species: total.update(atoms)
            sides.append(total)
        if len(sides) != 2 or sides[0] == sides[1]: continue
        surrounding = normalized[max(0, match.start()-90):match.end()+90]
        if re.search(r'\b(skeletal|unbalanced)\b', surrounding, re.I): continue
        # NCERT legitimately uses skeletal notation to identify substances.
        # Reject a false balance claim, not the mere use of that notation.
        if not re.search(r'\bbalanced\b|(?:same|equal)\b[^.!?\n]{0,50}\bboth (?:the )?sides', surrounding, re.I): continue
        return [f'The displayed equation {match[0]} is unbalanced. Correct its coefficients using atom conservation, or explicitly label it skeletal/unbalanced; do not present it as balanced.']
    return []


def species_keys(text):
    text = text.translate(str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789'))
    keys = set()
    for match in re.finditer(r'(?<![\w/])' + SPECIES, text):
        formula = match[0].strip()
        if formula_atoms(formula) is not None:
            keys.add(re.sub(r'^\d+\s*', '', re.sub(r'\((?:s|l|g|aq)\)$', '', formula)))
    return keys


def words(text):
    return re.findall(r'\w+', SOURCE_PATTERN.sub('', text).casefold())


def copies_source(answer, chunks):
    answer_words = words(answer)
    if not answer_words:
        return False
    covered = set()
    longest = 0
    for chunk in chunks:
        source_words = words(str(chunk.get('content', '')))
        if source_words and answer_words == source_words:
            return True
        for block in SequenceMatcher(None, answer_words, source_words, autojunk=False).get_matching_blocks():
            longest = max(longest, block.size)
            if block.size >= 12:
                covered.update(range(block.a, block.a + block.size))
    return len(answer_words) >= 40 and longest >= 35 and len(covered) / len(answer_words) >= .7


def answer_quality_issues(answer, chunks):
    audit = audit_answer(answer, chunks)
    issues = []
    if audit['invalid_source_references']:
        issues.append('Only cite source numbers that were actually supplied.')
    if not audit['valid_source_references'] and not audit['is_abstention']:
        issues.append('Include actual supporting [Source N] citations for the factual explanation.')
    if copies_source(answer, chunks):
        issues.append('Synthesize the explanation in your own words instead of returning copied textbook passages.')
    if re.match(r'^\W*(?:according to (?:the )?textbook(?: context)?|based on (?:the )?(?:provided|retrieved) context)', answer, re.I):
        issues.append('Start directly with the conceptual answer, without a textbook-context introduction.')
    blocks = re.split(r'\n\s*\n', answer)
    for index, block in enumerate(blocks):
        if not re.search(r'→|->', block):
            continue
        following = blocks[index+1] if index+1 < len(blocks) else ''
        if not SOURCE_PATTERN.sub('', following).strip():
            block += following
        references = [int(value) for value in SOURCE_PATTERN.findall(block)]
        cited = [str(chunks[number-1].get('content', '')) for number in references if 1 <= number <= len(chunks)]
        reactions = list(REACTION.finditer(block.translate(str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789'))))
        supported = any(re.search(r'→|->', content) for content in cited)
        if supported and reactions:
            supported = all(any(species_keys(reaction[0]) <= species_keys(content) for content in cited if re.search(r'→|->', content)) for reaction in reactions)
        if not supported:
            available = []
            for source_index, chunk in enumerate(chunks, 1):
                for line in str(chunk.get('content', '')).splitlines():
                    if re.search(r'→|->', line): available.append(f'[Source {source_index}] {line[:180]}')
            issues.append('For a reaction equation, cite the passage establishing its actual substances, not a source about another reaction. Do not introduce a new reaction from memory. Choose one of these supplied equations, or omit equations if none are available: ' + '; '.join(available[:5]))
            break
    return issues + equation_issues(answer), audit
