"""Labeled dense-retrieval evaluation set for the stored-procedures PDF."""

SQL_DOCUMENT_ID = "bc096b36-a249-44ed-bb9e-b0227dbea0e4"

SQL_RELEVANCE_EVALUATION = [
    {"query": "What is a Stored Procedure?", "expected_relevant": True, "category": "direct"},
    {"query": "What are the advantages of stored procedures?", "expected_relevant": True, "category": "direct"},
    {"query": "What is the syntax to create a stored procedure?", "expected_relevant": True, "category": "direct"},
    {"query": "What does DELIMITER do in MySQL?", "expected_relevant": True, "category": "direct"},
    {"query": "What is the purpose of CALL in MySQL?", "expected_relevant": True, "category": "direct"},
    {"query": "How do I invoke the InsertTree procedure?", "expected_relevant": True, "category": "paraphrase"},
    {"query": "Show me how to execute InsertTree.", "expected_relevant": True, "category": "paraphrase"},
    {"query": "How can I add a Neem tree using the stored procedure?", "expected_relevant": True, "category": "paraphrase"},
    {"query": "Which command runs the procedure that inserts a tree?", "expected_relevant": True, "category": "paraphrase"},
    {"query": "How is water requirement updated using a procedure?", "expected_relevant": True, "category": "paraphrase"},
    {"query": "Explain photosynthesis in plants.", "expected_relevant": False, "category": "unrelated"},
    {"query": "What is Newton's second law?", "expected_relevant": False, "category": "unrelated"},
    {"query": "How does binary search work?", "expected_relevant": False, "category": "unrelated"},
    {"query": "What causes inflation?", "expected_relevant": False, "category": "unrelated"},
    {"query": "Explain DNA replication.", "expected_relevant": False, "category": "unrelated"},
]
