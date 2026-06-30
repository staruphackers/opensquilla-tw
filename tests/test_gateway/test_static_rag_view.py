from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_rag_view_is_loaded_and_registered():
    template = (ROOT / "src/opensquilla/gateway/templates/legacy_index.html").read_text(
        encoding="utf-8"
    )
    app_js = (ROOT / "src/opensquilla/gateway/static/js/app.js").read_text(encoding="utf-8")
    view_js = (ROOT / "src/opensquilla/gateway/static/js/views/rag.js").read_text(
        encoding="utf-8"
    )
    view_css = (ROOT / "src/opensquilla/gateway/static/css/views/rag.css").read_text(
        encoding="utf-8"
    )

    assert "views/rag.js" in template
    assert "views/rag.css" in template
    assert "Router.register('/rag'" in app_js
    assert 'data-path="/rag"' in app_js
    assert "rag.status" in view_js
    assert "config.get" in view_js
    assert "config.patch" in view_js
    assert "rag.search" in view_js
    assert "waitForConnection" in view_js
    assert "_rpc.on('_state'" in view_js
    assert "STATUS_METRICS" in view_js
    assert "DEFAULT_INCLUDE" in view_js
    assert "rag-setting-enabled" in view_js
    assert "data-rag-mode-option" in view_js
    assert "rag-upload-dropzone" in view_js
    assert "rag-upload-file" in view_js
    assert "FormData" in view_js
    assert "/api/v1/rag/imports" in view_js
    assert "Server path" in view_js
    assert "data-source-mode" in view_js
    assert "rag-add-path" in view_js
    assert "/path/to/docs" in view_js
    assert "rag-source-summary" in view_js
    assert "rag-source-options" in view_js
    assert "Auto label" in view_js
    assert "_sourceLabelValue" in view_js
    assert "_sourceGroupValue" in view_js
    assert "rag.browse" not in view_js
    assert "Browse folders" not in view_js
    assert "UI.modal('Select source folder'" not in view_js
    assert "rag-path-selector" not in view_js
    assert "rag-path-clear" not in view_js
    assert "rag-folder-picker" not in view_js
    assert "Filter folders" not in view_js
    assert "Up one level" not in view_js
    assert "data-rag-path-form" not in view_js
    assert "data-rag-folder-filter" not in view_js
    assert "indexStatus" in view_js
    assert "rag-job-panel" in view_js
    assert "embeddingsWritten" in view_js
    assert "chunk matches" in view_js
    assert "Citation" in view_js
    assert "Lines" in view_js
    assert "Vector" in view_js
    assert "rag-inspect" in view_js
    assert "payloadBudget" in view_js
    assert "scoreBreakdown" in view_js
    assert "contentPreview" in view_js
    assert "rag.show" in view_js
    assert "Show chunk" in view_js
    assert "Hide chunk" in view_js
    assert "rag.enable_source" in view_js
    assert "rag.disable_source" in view_js
    assert "rag.remove_source" in view_js
    assert "data-enable" in view_js
    assert "data-disable" in view_js
    assert "data-remove" in view_js
    assert "rag-source-actions-cell__inner" in view_js
    assert "_sourceStatusMarkup" in view_js
    assert "activeJobs" in view_js
    assert "latestJob" in view_js
    assert "FTS" in view_js
    assert "textWeight" in view_js
    assert "vectorWeight" in view_js
    assert ".rag-stat" in view_css
    assert ".rag-panel" in view_css
    assert ".rag-top-grid" in view_css
    assert ".rag-path-selector" not in view_css
    assert ".rag-folder-modal" not in view_css
    assert ".rag-folder-picker" not in view_css
    assert ".rag-upload-dropzone" in view_css
    assert ".rag-source-mode" in view_css
    assert ".rag-upload-file" in view_css
    assert ".rag-source-summary" in view_css
    assert ".rag-source-options" in view_css
    assert ".rag-switch" in view_css
    assert ".rag-setting-row" in view_css
    assert ".rag-source-actions-cell__inner" in view_css
    assert ".rag-segmented" in view_css
    assert ".rag-searchbar" in view_css
    assert ".rag-progress" in view_css
    assert ".rag-result__snippet" in view_css
    assert ".rag-results-summary" in view_css
    assert ".rag-inspect" in view_css
    assert ".rag-score-breakdown" in view_css
    assert ".rag-result__preview" in view_css
