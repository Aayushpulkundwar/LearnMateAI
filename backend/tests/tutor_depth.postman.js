pm.test('Running API exposes its current contract', () => pm.response.to.have.status(200));
pm.test('All three depths are validated and Standard is only the omission default', () => {
  const depth = pm.response.json().components.schemas.QueryRequest.properties.explanation_depth;
  pm.expect(depth.enum).to.eql(['brief', 'standard', 'detailed']);
  pm.expect(depth.default).to.equal('standard');
});
pm.test('Citation contract preserves source provenance and similarity', () => {
  const fields = pm.response.json().components.schemas.Citation.properties;
  ['document_title', 'chapter', 'page_number', 'source_index', 'similarity_score'].forEach(key => pm.expect(fields).to.have.property(key));
});
