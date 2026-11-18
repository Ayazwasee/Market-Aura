import os
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from modules.stage1_ingestion_crawler import (
    DocumentParser,
    QueryFormulator,
    WebAndSocialCrawler,
)
from modules.stage2_indexer import TextPreprocessor, DocumentIndexer
from modules.stage5_ranking_qa import HybridRankingQAEngine
from modules.stage6_game_theory import GameTheoryIndustryEngine

app = FastAPI(title="MarketAura — Strategic Game Theory & Product Intelligence Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    html_path = os.path.join(os.path.dirname(__file__), "..", "public", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>MarketAura UI not found in public/index.html</h1>", status_code=404)


@app.post("/api/search")
async def search_and_analyze(
    query: str = Form(""),
    region: str = Form("India"),
    google_api_key: str = Form(""),
    google_cse_id: str = Form(""),
    llm_provider: str = Form("gemini"),
    trust_weight: float = Form(0.50),
    relevance_weight: float = Form(0.50),
    use_prf: bool = Form(True),
    file: UploadFile = File(None),
):
    uploaded_doc = None
    if file and file.filename:
        raw_bytes = await file.read()
        uploaded_doc = DocumentParser.parse_uploaded_file(file.filename, raw_bytes)

    active_query = QueryFormulator.formulate_query_from_input(query, uploaded_doc)

    # Stage 1: Initial Data Scraping via Google Custom Search JSON API / Gemini Grounding / Google News Index
    docs = WebAndSocialCrawler.crawl_live_web(
        query=active_query,
        max_results=8,
        region=region,
        google_api_key=google_api_key,
        google_cse_id=google_cse_id,
    )
    if uploaded_doc:
        docs.insert(0, uploaded_doc)

    # Stage 2–5: Indexing, Authority Verification & Hybrid Ranking
    indexer = DocumentIndexer(docs)
    ranking_engine = HybridRankingQAEngine(docs, indexer)
    ir_output = ranking_engine.execute_full_pipeline(
        query=active_query,
        alpha_relevance=float(relevance_weight),
        beta_reliability=float(trust_weight),
        use_prf=bool(use_prf),
    )

    # Stage 6: MarketAura Game Theory, Product Radar & Google API Dual-Engine Analysis
    q_to_pass = query.strip() if query.strip() else active_query
    game_theory_report = GameTheoryIndustryEngine.analyze_industry(
        query=q_to_pass,
        crawled_docs=docs,
        region=region,
        google_api_key=google_api_key,
        google_cse_id=google_cse_id,
    )

    first_stem = (
        TextPreprocessor.preprocess(active_query)[0]
        if TextPreprocessor.preprocess(active_query)
        else "market"
    )
    inv_postings = indexer.inverted_index.get(first_stem, [])
    pos_postings = indexer.positional_index.get(first_stem, {})
    comp_gaps = indexer.compressed_index.get(first_stem, [])

    return JSONResponse(
        content={
            "active_query": ir_output["expanded_query"],
            "added_terms": ir_output["added_prf_terms"],
            "direct_answer": ir_output["direct_answer"],
            "hybrid_results": ir_output["hybrid_results"],
            "standard_results": ir_output["standard_results"],
            "evaluation": ir_output["evaluation"],
            "index_preview": {
                "stem": first_stem,
                "inverted": inv_postings,
                "positional": pos_postings,
                "compressed_gaps": comp_gaps,
            },
            "game_theory_analysis": game_theory_report,
        }
    )
