import asyncio
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from pydantic import ValidationError
from app.api.routes.query import authorized_query_state
from app.graph.nodes import cite_node, generate_node
from app.schemas.query import QueryRequest
from app.services.context_selection import select_context_chunks
from app.services.grounded_context import build_grounded_context
from app.services.retrieval_quality import lexical_query, prioritize_explanations
from app.services.retrieval_service import RetrievedChunk
from app.services.tutor_answer_quality import answer_quality_issues, copies_source, equation_issues, formula_atoms
from app.services.tutor_prompt import build_tutor_prompts, DEPTH_PROFILES


def chunk(number=1, text='Textbook evidence explains that chemical changes produce different substances.'):
    return {'id': str(uuid4()), 'document_id': str(uuid4()), 'document_title': 'NCERT Science',
        'chapter': 'Chemical Reactions and Equations', 'page_number': number, 'chunk_index': number,
        'content': text, 'similarity_score': .7}


class TutorDepthTests(TestCase):
    def test_all_modes_validate_and_invalid_values_do_not_silently_default(self):
        for depth in DEPTH_PROFILES:
            self.assertEqual(QueryRequest(question='Question', explanation_depth=depth).explanation_depth, depth)
        for invalid in ['Detailed', 'long', '', None]:
            with self.assertRaises(ValidationError): QueryRequest(question='Question', explanation_depth=invalid)
        self.assertEqual(QueryRequest(question='Question').explanation_depth, 'standard')

    def test_modes_keep_one_server_authorized_scope_and_grade(self):
        grade, subject = uuid4(), uuid4()
        student = SimpleNamespace(grade=SimpleNamespace(name='Class 10'))
        scope = SimpleNamespace(grade_id=grade, subject_id=subject, chapter_id=None, document_id=None)
        filters = []
        with patch('app.api.routes.query.resolve_authorized_scope', AsyncMock(return_value=scope)):
            for depth in DEPTH_PROFILES:
                result = asyncio.run(authorized_query_state(QueryRequest(question='Question', explanation_depth=depth), student, None))
                filters.append(result['filters'])
                self.assertEqual(result['tutoring_context']['explanation_depth'], depth)
                self.assertEqual(result['tutoring_context']['grade_name'], 'Class 10')
        self.assertEqual(filters[0], filters[1]); self.assertEqual(filters[1], filters[2])
        self.assertEqual(filters[0]['grade_id'], str(grade))

    def test_selected_depth_wins_over_topic_mastery_preferences(self):
        grade, subject, topic = uuid4(), uuid4(), uuid4()
        scope = SimpleNamespace(grade_id=grade, subject_id=subject, chapter_id=None, document_id=None)
        with patch('app.api.routes.query.resolve_authorized_scope', AsyncMock(return_value=scope)), patch('app.api.routes.query.resolve_tutoring_context', AsyncMock(return_value={'subject_id': subject, 'explanation_depth': 'brief', 'mastery_status': 'Strong', 'evidence_sufficient': True})):
            state = asyncio.run(authorized_query_state(QueryRequest(question='Question', study_topic_id=topic, explanation_depth='detailed'), SimpleNamespace(grade=SimpleNamespace(name='Class 10')), None))
        self.assertEqual(state['tutoring_context']['explanation_depth'], 'detailed')

    def test_three_modes_reach_actual_generation_prompt_and_output_budget(self):
        source = chunk()
        replies = {
            'brief': 'A chemical reaction changes the starting substances into different products. [Source 1]',
            'standard': 'A chemical reaction produces new substances. The starting materials are reactants and the resulting substances are products. [Source 1]',
            'detailed': 'A chemical reaction forms different substances.\n\n1. Identify the starting reactants.\n2. Explain the change that produces the products.\n3. Relate the resulting properties to the starting materials. [Source 1]',
        }
        for depth, reply in replies.items():
            with self.subTest(depth=depth), patch('app.graph.nodes.llm_service.generate', AsyncMock(return_value=reply)) as generate:
                result = asyncio.run(generate_node({'question': 'What is a chemical reaction?', 'retrieved_chunks': [source], 'mode': 'query',
                    'tutoring_context': {'grade_name': 'Class 10', 'explanation_depth': depth}}))
                call = generate.await_args.kwargs
                self.assertIn(f'Requested explanation depth: {depth}', call['prompt'])
                self.assertIn(depth.upper()+' MODE', call['system_prompt'])
                self.assertIn('Class 10', call['system_prompt'])
                self.assertEqual(call['num_predict'], DEPTH_PROFILES[depth]['tokens'])
                self.assertEqual(call['num_ctx'], 8192)
                self.assertEqual(result['answer'], reply) # No truncation or fabricated expansion.
                self.assertEqual(result['context_chunks'], [source])

    def test_grade_language_changes_without_changing_factual_evidence(self):
        junior, prompt, _ = build_tutor_prompts('Question', 'Evidence', {'grade_name': 'Class 7', 'explanation_depth': 'standard'})
        senior, same_prompt, _ = build_tutor_prompts('Question', 'Evidence', {'grade_name': 'Class 12', 'explanation_depth': 'standard'})
        self.assertIn('concrete, simple', junior); self.assertIn('deeper reasoning', senior)
        self.assertEqual(prompt, same_prompt)
        with self.assertRaises(ValueError): build_tutor_prompts('Question', 'Evidence', {'explanation_depth': 'wrong'})

    def test_raw_passage_or_boilerplate_is_repaired_by_llm_not_postprocessed(self):
        source = chunk()
        repaired = 'Chemical changes transform the original substances into different products. [Source 1]'
        for copied in [source['content']+' [Source 1]', 'According to the textbook context, substances change. [Source 1]']:
            with patch('app.graph.nodes.llm_service.generate', AsyncMock(side_effect=[copied, repaired])) as generate:
                result = asyncio.run(generate_node({'question': 'Question', 'mode': 'query', 'retrieved_chunks': [source]}))
            self.assertEqual(generate.await_count, 2); self.assertEqual(result['answer'], repaired)
            self.assertIn('Rewrite the explanation', generate.await_args.kwargs['prompt'])

    def test_invalid_citations_are_bounded_and_never_replaced_with_invented_answers(self):
        with patch('app.graph.nodes.llm_service.generate', AsyncMock(return_value='A factual claim. [Source 99]')) as generate:
            with self.assertRaises(RuntimeError): asyncio.run(generate_node({'question': 'Question', 'mode': 'query', 'retrieved_chunks': [chunk()]}))
        self.assertEqual(generate.await_count, 2)

    def test_equations_must_reference_a_passage_establishing_a_reaction(self):
        sources = [chunk(), chunk(2, 'The reaction can be written as Magnesium + Oxygen → Magnesium oxide.')]
        bad, _ = answer_quality_issues('Magnesium + Oxygen → Magnesium oxide. [Source 1]', sources)
        good, _ = answer_quality_issues('Magnesium + Oxygen → Magnesium oxide. [Source 2]', sources)
        self.assertTrue(any('reaction equation' in issue for issue in bad))
        self.assertEqual(good, [])

    def test_skeletal_equations_cannot_be_presented_as_balanced(self):
        self.assertTrue(equation_issues('The balanced chemical equation is Mg + O2 → MgO.'))
        self.assertEqual(equation_issues('The balanced chemical equation is 2Mg + O2 → 2MgO.'), [])
        self.assertEqual(equation_issues('The skeletal equation Mg + O2 → MgO needs balancing.'), [])
        self.assertEqual(equation_issues('NCERT represents the substances as Mg + O2 → MgO (1.2).'), [])
        self.assertEqual(equation_issues('Zn + H2SO4 → ZnSO4 + H2'), [])
        self.assertEqual(equation_issues('Ca(OH)2 + 2HCl → CaCl2 + 2H2O'), [])
        self.assertEqual(dict(formula_atoms('2Ca(OH)2')), {'Ca': 2, 'O': 4, 'H': 4})

    def test_an_unrelated_equation_source_is_not_accepted_for_new_reaction_species(self):
        sources = [chunk(text='Magnesium burns in air. Mg + O2 → MgO is a skeletal equation.')]
        wrong, _ = answer_quality_issues('Zn + H2SO4 → ZnSO4 + H2. [Source 1]', sources)
        right, _ = answer_quality_issues('2Mg + O2 → 2MgO. [Source 1]', sources)
        self.assertTrue(wrong); self.assertEqual(right, [])

    def test_only_referenced_real_sources_are_attached_with_original_similarity(self):
        first, second = chunk(1), chunk(2, 'A different supporting fact.')
        result = asyncio.run(cite_node({'mode': 'query', 'answer': 'A supported fact. [Source 2]', 'context_chunks': [first, second]}))
        self.assertEqual(len(result['citations']), 1)
        self.assertEqual(result['citations'][0]['chunk_id'], second['id'])
        self.assertEqual(result['citations'][0]['source_index'], 2)
        self.assertEqual(result['citations'][0]['similarity_score'], .7)

    def test_budget_and_empty_sources_do_not_create_false_citation_provenance(self):
        empty = chunk(text='')
        source = chunk(text='Supported content. '*100)
        context, used = build_grounded_context([empty, source], 250)
        self.assertIn('[Source 1]', context); self.assertNotIn('[Source 2]', context)
        self.assertTrue(source['content'].startswith(used[0]['content']))
        self.assertLess(len(used[0]['content']), len(source['content']))

    def test_weak_lexical_noise_and_exact_duplicate_chunks_are_removed(self):
        first = chunk()
        duplicate = {**first, 'id': str(uuid4())}
        weak = {**chunk(text='Weak unrelated passage'), 'similarity_score': .51, 'lexical_rank': 1, 'lexical_score': .001}
        result = select_context_chunks([first, duplicate, weak], minimum_similarity=.5, maximum_similarity_drop=.06)
        self.assertEqual(result, [first])

    def test_query_normalization_and_explanation_ranking_do_not_rewrite_scores(self):
        self.assertEqual(lexical_query('What is photosynthesis?'), 'photosynthesis')
        self.assertEqual(lexical_query('Explain displacement reactions with examples.'), 'displacement reactions')
        exercise = RetrievedChunk('exercise', 'doc', 'NCERT', 'EXERCISES\nWhat are displacement reactions? Write equations. Explain the reactions. Name the products.', 16, 'Reactions', 1, .68)
        prose = RetrievedChunk('definition', 'doc', 'NCERT', 'Iron displaces copper from copper sulphate. This reaction is known as a displacement reaction.', 11, 'Reactions', 2, .626)
        ranked = prioritize_explanations([exercise, prose], 'Explain displacement reactions with examples.')
        self.assertEqual(ranked, [prose, exercise]); self.assertEqual(ranked[0].similarity_score, .626)
        self.assertEqual(prioritize_explanations([exercise, prose], 'Explain exercise 3'), [exercise, prose])
