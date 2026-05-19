from context_engine.prompt_builder.engine import AdvancedPromptBuilder
from context_engine.prompt_builder.models import PromptMode
from context_engine.core.pipeline import pipeline
from context_engine.retrieval.models import RetrievalQuery


def test_rules_include_diff_contract_and_safe_fallback():
    builder = AdvancedPromptBuilder()
    rules = builder._build_rules(mode=PromptMode.BUGFIX)
    assert "('---', '+++', '@@')" in rules
    assert "output an empty diff" in rules


def test_compact_hierarchy_includes_active_and_related_markers():
    builder = AdvancedPromptBuilder()
    tree = builder._build_project_hierarchy_compact(
        active_file="services/auth_service.py",
        related_files=["core/exceptions.py", "api/auth_routes.py"],
    )
    assert "Nexus-IDE" in tree
    assert "* active: services/auth_service.py" in tree
    assert "* related: core/exceptions.py" in tree


def test_architecture_mode_uses_briefing_contract():
    builder = AdvancedPromptBuilder()
    rules = builder._build_rules(mode=PromptMode.ARCHITECTURE)
    assert "Do NOT output a unified diff patch" in rules
    assert "structured architecture/engineering briefing" in rules
    assert "unified diff patch" not in builder._response_contract(PromptMode.ARCHITECTURE).lower()


def test_bugfix_prefers_method_level_anchor():
    root = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "workspace" / "nexus_test_backend")
    pipeline.initialize_project(root)
    query = RetrievalQuery(
        task="Fix weak validation logic in login and make credential checks robust",
        active_file="services/auth_service.py",
        mode="bugfix",
    )
    candidates = pipeline.retrieve(query)
    context = pipeline.extraction.extract_context(query.active_file, candidates, mode="bugfix", runtime=pipeline.runtime)
    assert context.active_file is not None
    reasons = [s.reason for s in context.active_file.slices]
    assert any("login" in reason.lower() or "verify" in reason.lower() for reason in reasons)
    dep_reasons = [r for r in reasons if r.startswith("Dependency of ")]
    assert len(dep_reasons) <= 1
