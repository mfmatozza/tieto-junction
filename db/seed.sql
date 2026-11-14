INSERT INTO projects (id, name, repository_url)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'MessagePack for C#',
    'https://github.com/te-industry-tech-office/junction26-messagepack-csharp'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO requirements (id, project_id, external_key, title, body, source_url)
VALUES
    ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000001', '2129', 'Formatters for types in a referenced assembly', 'Add formatter support for types from a referenced assembly.', 'https://github.com/te-industry-tech-office/junction26-messagepack-csharp/tree/ju26-issue-2129'),
    ('00000000-0000-0000-0000-000000000102', '00000000-0000-0000-0000-000000000001', '2234', 'Analyzer with SuppressSourceGeneration', 'Make the analyzer behave correctly when source generation is suppressed.', 'https://github.com/te-industry-tech-office/junction26-messagepack-csharp/tree/ju26-issue-2234'),
    ('00000000-0000-0000-0000-000000000103', '00000000-0000-0000-0000-000000000001', '2283', 'Closed generic struct from a referenced assembly', 'Fix the crash when a closed generic struct comes from a referenced assembly.', 'https://github.com/te-industry-tech-office/junction26-messagepack-csharp/tree/ju26-issue-2283'),
    ('00000000-0000-0000-0000-000000000104', '00000000-0000-0000-0000-000000000001', '2297', 'Exclude generated code from coverage', 'Add ExcludeFromCodeCoverage to generated code.', 'https://github.com/te-industry-tech-office/junction26-messagepack-csharp/tree/ju26-issue-2297')
ON CONFLICT (id) DO NOTHING;

INSERT INTO pull_requests (id, project_id, requirement_id, branch_name, commit_sha, review_route, status, changed_lines, lines_to_read)
VALUES
    ('00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000103', 'ju26-issue-2283', '9df83c38409c8bfad0517aebffe48211eda4a5', 'focused_read', 'reviewed', 228, 70),
    ('00000000-0000-0000-0000-000000000202', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000104', 'ju26-issue-2297', 'a0aa5ab2de7f5a669d97e37184a89034c1de82b6', 'focused_read', 'reviewed', 1392, 146),
    ('00000000-0000-0000-0000-000000000203', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000101', 'ju26-issue-2129', '083afd994c1c9a994cb2cd5aa0b6ad805a621457', 'full_read', 'reviewed', 1043, 884),
    ('00000000-0000-0000-0000-000000000204', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000102', 'ju26-issue-2234', '9007cee1163c4a274fd60c3cc20c21ae63622786', 'full_read', 'reviewed', 266, 252)
ON CONFLICT (id) DO NOTHING;

INSERT INTO trust_ledger (project_id, code_area, level, clean_signoffs)
VALUES
    ('00000000-0000-0000-0000-000000000001', 'source-generation', 'focused_read', 2),
    ('00000000-0000-0000-0000-000000000001', 'analyzers', 'full_read', 0),
    ('00000000-0000-0000-0000-000000000001', 'serialization-contracts', 'full_read', 0)
ON CONFLICT (project_id, code_area) DO NOTHING;

INSERT INTO review_events (event_type, aggregate_type, aggregate_id, payload)
VALUES
    ('review.started', 'pull_request', '00000000-0000-0000-0000-000000000201', '{"branch":"ju26-issue-2283"}'),
    ('claim.checked', 'pull_request', '00000000-0000-0000-0000-000000000201', '{"passed":6,"disputed":2}'),
    ('review.routed', 'pull_request', '00000000-0000-0000-0000-000000000201', '{"route":"focused_read","lines_to_read":70}')
ON CONFLICT DO NOTHING;

