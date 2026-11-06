pm.test('Quiz generation requires authentication', () => pm.response.to.have.status(401));
pm.test('Unauthenticated response contains no quiz or answer key', () => {
  const body = pm.response.json();
  pm.expect(body).not.to.have.property('questions');
  pm.expect(body).not.to.have.property('correct_option_index');
});
