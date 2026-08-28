# -*- coding: utf-8 -*-
"""CorpusLD Extraction Package.

Shim kompatibilitas penuh: semua `from json_ld_extractor import X` lama
tetap berfungsi tanpa perubahan pada konsumen (server, benchmark_runner),
serta mengekspor kapabilitas baru Deep Knowledge Graph, RDF/Turtle, dan Async Adapters.
"""
import logging
import warnings

# Redam pesan teknis internal CMap font decoding dari PyPDF
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pypdf._cmap").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", module="pypdf")

from .schemas import (
    EducationalOrganization,
    Author,
    UniversalEntity,
    DocumentSection,
    UniversalProperty,
    UniversalTable,
    UniversalJSONLD,
    KGNode,
    KGEdge,
    DeepKnowledgeGraph,
    HowToStep,
    DefinedTerm,
    MathFormula,
    Step1Overview,
    Step2Sections,
    Step3Metrics,
    Step4Tables,
    Step5References,
    StepSectionDeepExtraction,
)
from .text_utils import (
    strip_markdown_formatting,
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_CHARS_AGENT1,
    truncate_context,
    sanitize_text_for_extraction,
    fix_concatenated_title_spacing,
    clean_document_title,
    clean_abstract_description,
    is_mathematical_formula,
)
from .tables import (
    consolidate_tables,
    is_valid_tabular_data,
    is_descriptive_table,
    parse_markdown_table_direct,
    parse_flat_text_table,
)
from .outline import (
    filter_sections_negative_constraints,
    filter_monotonic_outline_headings,
    extract_agnostic_structural_outline,
    resolve_section_pages,
)
from .dates import (
    MONTH_MAP_BILINGUAL,
    normalize_publication_date,
)
from .metadata import (
    extract_doi_deterministic,
    classify_genre,
    generate_document_id,
    detect_publisher_deterministic,
    detect_document_language,
    extract_deterministic_title,
    extract_deterministic_abstract,
    extract_deterministic_authors,
    extract_explicit_document_keywords,
    verify_and_resolve_authors,
    normalize_author_affiliations,
    sanitize_entities,
    refine_and_deduplicate_metrics,
    correct_metric_units,
)
from .references import (
    extract_references_regex_fallback,
    reconcile_references,
)
from .llm_adapters import (
    run_agentic_step,
    run_agentic_step_async,
    repair_malformed_json,
    is_safe_custom_endpoint,
    resolve_and_pin_safe_endpoint,
)
from .validation import (
    ANTONYM_PAIRS_BILINGUAL,
    NEGATION_PATTERNS_BILINGUAL,
    validate_knowledge_graph_adversarial,
    validate_json_ld_rich_results,
    get_clean_schema_org_jsonld,
    generate_google_scholar_meta_tags,
    generate_html_head_package,
    export_to_turtle_rdf,
    export_to_json_ld_graph,
    calculate_graph_health_metrics,
)
from .merging import (
    merge_and_enrich_json_ld,
    merge_authors,
    merge_sections,
    merge_metrics,
    merge_tables,
    merge_citations,
)
from .pipeline import (
    extract_json_ld_agentic_rag,
    extract_json_ld_from_chunks,
    extract_latex_formulas_deterministic,
    extract_technical_terms_deterministic,
    extract_quantitative_metrics_deterministic,
)
from .unit_ontology import (
    is_valid_scientific_unit,
    sanitize_text_strip_superscript_citations,
    is_citation_or_footnote_context,
)

__all__ = [
    'EducationalOrganization', 'Author', 'UniversalEntity', 'DocumentSection',
    'UniversalProperty', 'UniversalTable', 'UniversalJSONLD', 'KGNode', 'KGEdge',
    'DeepKnowledgeGraph', 'HowToStep', 'DefinedTerm', 'MathFormula',
    'Step1Overview', 'Step2Sections', 'Step3Metrics', 'Step4Tables', 'Step5References',
    'StepSectionDeepExtraction',
    'strip_markdown_formatting', 'MAX_CONTEXT_CHARS', 'MAX_CONTEXT_CHARS_AGENT1', 'truncate_context',
    'sanitize_text_for_extraction', 'fix_concatenated_title_spacing', 'clean_document_title', 'clean_abstract_description',
    'is_mathematical_formula', 'consolidate_tables', 'is_valid_tabular_data', 'is_descriptive_table',
    'parse_markdown_table_direct', 'parse_flat_text_table',
    'filter_sections_negative_constraints', 'filter_monotonic_outline_headings', 'extract_agnostic_structural_outline', 'resolve_section_pages',
    'MONTH_MAP_BILINGUAL', 'normalize_publication_date', 'extract_doi_deterministic', 'classify_genre',
    'generate_document_id', 'detect_publisher_deterministic', 'detect_document_language', 'extract_deterministic_title',
    'extract_deterministic_abstract', 'extract_deterministic_authors', 'extract_explicit_document_keywords', 'verify_and_resolve_authors',
    'normalize_author_affiliations', 'sanitize_entities', 'refine_and_deduplicate_metrics', 'correct_metric_units',
    'extract_references_regex_fallback', 'reconcile_references', 'run_agentic_step', 'run_agentic_step_async',
    'repair_malformed_json', 'is_safe_custom_endpoint', 'resolve_and_pin_safe_endpoint', 'ANTONYM_PAIRS_BILINGUAL',
    'NEGATION_PATTERNS_BILINGUAL', 'validate_knowledge_graph_adversarial', 'validate_json_ld_rich_results', 'get_clean_schema_org_jsonld',
    'generate_google_scholar_meta_tags', 'generate_html_head_package', 'export_to_turtle_rdf', 'export_to_json_ld_graph',
    'calculate_graph_health_metrics', 'merge_and_enrich_json_ld', 'merge_authors',
    'merge_sections', 'merge_metrics', 'merge_tables', 'merge_citations',
    'extract_json_ld_agentic_rag', 'extract_json_ld_from_chunks',
    'extract_latex_formulas_deterministic', 'extract_technical_terms_deterministic',
    'extract_quantitative_metrics_deterministic',
    'is_valid_scientific_unit', 'sanitize_text_strip_superscript_citations',
    'is_citation_or_footnote_context',
]
