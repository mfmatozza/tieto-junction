-- Demo seed. Branch SHAs are the real heads of Tieto's ju26 branches.
-- Route/line numbers start empty: they are filled by OUR review run, never copied from other teams.
INSERT INTO projects (id, name, repository_url)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'MessagePack for C#',
    'https://github.com/te-industry-tech-office/junction26-messagepack-csharp'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO requirements (id, project_id, external_key, title, body, source_url)
VALUES
    ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000001', '2129', 'Formatters for types in a referenced assembly', 'Add formatter support for types from a referenced assembly.', 'https://github.com/MessagePack-CSharp/MessagePack-CSharp/issues/2129'),
    ('00000000-0000-0000-0000-000000000102', '00000000-0000-0000-0000-000000000001', '2234', 'Analyzer with SuppressSourceGeneration', 'Make the analyzer behave correctly when source generation is suppressed.', 'https://github.com/MessagePack-CSharp/MessagePack-CSharp/issues/2234'),
    ('00000000-0000-0000-0000-000000000103', '00000000-0000-0000-0000-000000000001', '2283', 'Closed generic struct from a referenced assembly', 'Fix the crash when a closed generic struct comes from a referenced assembly.', 'https://github.com/MessagePack-CSharp/MessagePack-CSharp/issues/2283'),
    ('00000000-0000-0000-0000-000000000104', '00000000-0000-0000-0000-000000000001', '2297', 'Exclude generated code from coverage', 'Add ExcludeFromCodeCoverage to generated code.', 'https://github.com/MessagePack-CSharp/MessagePack-CSharp/issues/2297')
ON CONFLICT (id) DO NOTHING;

INSERT INTO pull_requests (id, project_id, requirement_id, branch_name, commit_sha)
VALUES
    ('00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000103', 'ju26-issue-2283', '9df83c38409c8bfad0517aebffe48211eda4a5b4'),
    ('00000000-0000-0000-0000-000000000202', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000104', 'ju26-issue-2297', 'a0aa5ab2de7f5a669d97e37184a89034c1de82b6'),
    ('00000000-0000-0000-0000-000000000203', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000101', 'ju26-issue-2129', '083afd994c1c9a994cb2cd5aa0b6ad805a621457'),
    ('00000000-0000-0000-0000-000000000204', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000102', 'ju26-issue-2234', '9007cee1163c4a274fd60c3cc20c21ae63622786')
ON CONFLICT (id) DO NOTHING;

-- Every code area starts untrusted. Trust is earned during the demo, not seeded.
INSERT INTO trust_ledger (project_id, code_area)
VALUES
    ('00000000-0000-0000-0000-000000000001', 'source-generation'),
    ('00000000-0000-0000-0000-000000000001', 'analyzers'),
    ('00000000-0000-0000-0000-000000000001', 'serialization-contracts')
ON CONFLICT (project_id, code_area, agent) DO NOTHING;
