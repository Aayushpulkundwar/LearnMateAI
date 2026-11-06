pm.test('Grades endpoint is public and successful', () => pm.response.to.have.status(200));
pm.test('All six registration grades are returned in numeric order', () => {
  pm.expect(pm.response.json().map(grade => grade.name)).to.eql([
    'Class 7', 'Class 8', 'Class 9', 'Class 10', 'Class 11', 'Class 12',
  ]);
});
pm.test('Grade IDs are unique UUIDs supplied by the API', () => {
  const rows = pm.response.json();
  pm.expect(new Set(rows.map(grade => grade.id)).size).to.equal(6);
  rows.forEach(grade => pm.expect(grade.id).to.match(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i));
});
