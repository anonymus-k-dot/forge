"""
FORGE – Template registry
─────────────────────────
Aggregates all 90 ForgeTemplate instances from the six domain modules
into a single ALL_TEMPLATES dict keyed by template ID.

Usage:
    from template_registry import ALL_TEMPLATES
    tmpl = ALL_TEMPLATES["C2"]
"""

from forge_templates.coding            import CODING_TEMPLATES
from forge_templates.data_analysis     import DATA_ANALYSIS_TEMPLATES
from forge_templates.marketing         import MARKETING_TEMPLATES
from forge_templates.product_management import PRODUCT_MANAGEMENT_TEMPLATES
from forge_templates.research          import RESEARCH_TEMPLATES
from forge_templates.writing           import WRITING_TEMPLATES

ALL_TEMPLATES: dict = {}
ALL_TEMPLATES.update(CODING_TEMPLATES)
ALL_TEMPLATES.update(DATA_ANALYSIS_TEMPLATES)
ALL_TEMPLATES.update(MARKETING_TEMPLATES)
ALL_TEMPLATES.update(PRODUCT_MANAGEMENT_TEMPLATES)
ALL_TEMPLATES.update(RESEARCH_TEMPLATES)
ALL_TEMPLATES.update(WRITING_TEMPLATES)

# Sanity check imported at module load time
assert len(ALL_TEMPLATES) == 90, (
    f"Expected 90 templates, got {len(ALL_TEMPLATES)}. "
    "Check for missing or duplicate IDs."
)