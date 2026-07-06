# Knowledge Seeds

This folder contains starter documents for the knowledge base.

## Categories

- `career_path/`: career development path references
- `salary_market/`: hiring market and salary trend references
- `transition_guide/`: campus hiring, social hiring, and career transition guides
- `resume_template/`: resume structure, project description, and optimization references
- `jd_lib/`: job description samples for common roles
- `interview_q/`: interview preparation and question bank references
- `skill_model/`: role capability models and skill trees
- `industry_report/`: industry trend and talent demand references

The `skill_model/` category intentionally includes separate role-level files for
common evaluation targets. Keeping product manager, DevOps, data scientist,
full-stack engineer, and data analyst models as standalone documents improves
retrieval precision for role-specific capability queries.

## Import

Import all starter documents:

```bash
python backend/scripts/import_knowledge_seeds.py
```

Import a single category manually:

```bash
python backend/scripts/import_knowledge.py docs/knowledge-seeds/career_path --doc-type career_path --recursive
python backend/scripts/import_knowledge.py docs/knowledge-seeds/salary_market --doc-type salary_market --recursive
python backend/scripts/import_knowledge.py docs/knowledge-seeds/transition_guide --doc-type transition_guide --recursive
python backend/scripts/import_knowledge.py docs/knowledge-seeds/resume_template --doc-type resume_template --recursive
python backend/scripts/import_knowledge.py docs/knowledge-seeds/jd_lib --doc-type jd_lib --recursive
python backend/scripts/import_knowledge.py docs/knowledge-seeds/interview_q --doc-type interview_q --recursive
python backend/scripts/import_knowledge.py docs/knowledge-seeds/skill_model --doc-type skill_model --recursive
python backend/scripts/import_knowledge.py docs/knowledge-seeds/industry_report --doc-type industry_report --recursive
```
