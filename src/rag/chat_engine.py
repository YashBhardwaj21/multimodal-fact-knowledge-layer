"""Conversational RAG engine with grounded source evidence."""

import re
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging

from src.rag.vector_store import SessionVectorStore
from src.sessions.session_manager import WorkspaceSession, ChatMessage
from src.facts.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class ChatEngine:
    """Answers queries in an isolated session with verified source citations."""

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        session_id: Optional[str] = None,
        session: Optional[WorkspaceSession] = None,
        vector_store: Optional[SessionVectorStore] = None,
        storage_base: str = "storage/buckets"
    ):
        self.llm = llm_provider or LLMProvider()
        self.session_id = session_id or (session.id if session else None)
        self.session = session or (WorkspaceSession(self.session_id, "Workspace") if self.session_id else None)
        self.vector_store = vector_store or (
            SessionVectorStore(self.session_id, storage_base=storage_base) if self.session_id else None
        )

    def chat(self, user_query: str) -> Dict[str, Any]:
        """Process conversational query on the bound session."""
        if not self.session or not self.vector_store:
            raise ValueError("ChatEngine requires a bound session and vector_store")
        return self.process_chat(self.session, self.vector_store, user_query)

    def process_chat(
        self,
        session: WorkspaceSession,
        vector_store: SessionVectorStore,
        user_query: str,
        document_name: Optional[str] = None,
        canonical_docs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process query within session and return grounded answer with citations."""
        q_strip = user_query.strip().lower()

        # 1. Handle common conversational greetings and meta inquiries
        if q_strip in ["hi", "hello", "hey", "hola", "yo", "good morning", "good afternoon", "good evening", "help", "who are you"]:
            doc_titles = [d.get("title", d.get("filename", "")) for d in session.documents]
            doc_list = "\n".join([f"- **{t}**" for t in doc_titles[:5]]) if doc_titles else "No documents uploaded yet."
            greeting = (
                f"Hello! I am your Document Intelligence Assistant for **{session.title}**.\n\n"
                f"Currently available documents in this workspace:\n{doc_list}\n\n"
                "**Here are things you can ask me:**\n"
                "- *'Summarize page 10 of [document]'*\n"
                "- *'What are the key financial or technical figures?'*\n"
                "- *'Compare metrics across uploaded files'*\n"
                "- *'What tables or instructions are present?'*\n\n"
                "What would you like to explore?"
            )
            user_msg = ChatMessage(role="user", content=user_query)
            ai_msg = ChatMessage(role="assistant", content=greeting, citations=[])
            session.messages.extend([user_msg, ai_msg])
            return {
                "answer": greeting,
                "reply": greeting,
                "citations": [],
                "user_message": user_msg.to_dict(),
                "assistant_message": ai_msg.to_dict()
            }

        # 2. Check if the query specifically requests a page number
        page_match = re.search(r'\b(?:page|p\.?)\s*(\d+)\b', user_query, re.IGNORECASE)
        target_page = int(page_match.group(1)) if page_match else None

        # 3. Retrieve relevant passages using vector search
        passages = vector_store.search_hybrid(
            query=user_query,
            top_k=5,
            doc_filter=document_name,
            page_filter=target_page
        )

        # Fallback to unrestricted search if filtered search returned nothing
        if not passages and (document_name or target_page):
            passages = vector_store.search_hybrid(query=user_query, top_k=5)

        # 4. If target page was requested, also attempt to load full page text from canonical cache
        page_direct_text = ""
        resolved_doc_name = document_name
        if target_page and canonical_docs:
            for d_name, cdoc in canonical_docs.items():
                if not document_name or d_name == document_name or Path(d_name).stem == Path(document_name).stem:
                    matching_pages = [p for p in cdoc.pages if p.page_number == target_page]
                    if matching_pages:
                        page_direct_text = matching_pages[0].text
                        resolved_doc_name = d_name
                        break

        # 5. Extract relevant facts matching the query or target page
        relevant_facts = []
        for f in session.knowledge_layer.facts:
            match_doc = not document_name or f.evidence.document_name == document_name
            match_page = not target_page or f.evidence.page_number == target_page
            text_match = (
                f.subject.lower() in q_strip or
                f.attribute.lower() in q_strip or
                any(w in f.value.lower() for w in q_strip.split() if len(w) > 3)
            )
            if (match_doc and match_page and target_page) or text_match:
                relevant_facts.append(f)

        # 6. Build citations
        citations = []
        if page_direct_text and resolved_doc_name:
            thumb_url = f"/api/sessions/{session.id}/documents/{Path(resolved_doc_name).stem}/pages/{target_page}/thumbnail"
            citations.append({
                "document_name": resolved_doc_name,
                "page_number": target_page,
                "verbatim_quote": page_direct_text[:280] + ("..." if len(page_direct_text) > 280 else ""),
                "thumbnail_url": thumb_url
            })

        for p in passages[:3]:
            d_name = p.get("document_name", "")
            p_num = p.get("page_number", 1)
            text_snippet = p.get("text", "")
            quote = text_snippet if len(text_snippet) < 300 else text_snippet[:280] + "..."
            thumb_url = f"/api/sessions/{session.id}/documents/{Path(d_name).stem}/pages/{p_num}/thumbnail"
            if not any(c["document_name"] == d_name and c["page_number"] == p_num for c in citations):
                citations.append({
                    "document_name": d_name,
                    "page_number": p_num,
                    "verbatim_quote": quote,
                    "thumbnail_url": thumb_url
                })

        for f in relevant_facts[:2]:
            if f.evidence:
                thumb_url = f"/api/sessions/{session.id}/documents/{Path(f.evidence.document_name).stem}/pages/{f.evidence.page_number}/thumbnail"
                if not any(c["document_name"] == f.evidence.document_name and c["page_number"] == f.evidence.page_number for c in citations):
                    citations.append({
                        "document_name": f.evidence.document_name,
                        "page_number": f.evidence.page_number,
                        "verbatim_quote": f.evidence.verbatim_quote,
                        "thumbnail_url": thumb_url
                    })

        # 7. Synthesize answer
        answer = self._synthesize_answer(
            query=user_query,
            passages=passages,
            facts=relevant_facts,
            target_page=target_page,
            page_text=page_direct_text,
            doc_name=resolved_doc_name
        )

        user_msg = ChatMessage(role="user", content=user_query)
        ai_msg = ChatMessage(role="assistant", content=answer, citations=citations)
        session.messages.extend([user_msg, ai_msg])

        return {
            "answer": answer,
            "reply": answer,
            "citations": citations,
            "user_message": user_msg.to_dict(),
            "assistant_message": ai_msg.to_dict()
        }

    def _synthesize_answer(
        self,
        query: str,
        passages: List[Dict[str, Any]],
        facts: List[Any],
        target_page: Optional[int] = None,
        page_text: str = "",
        doc_name: Optional[str] = None
    ) -> str:
        """Synthesize answer using configured LLM or intelligent structured extractor."""
        if not passages and not facts and not page_text:
            return (
                f"No verified information regarding '{query}' was found in the documents currently uploaded to this workspace. "
                "Please verify the document is uploaded or try rephrasing your question."
            )

        # Prepare context blocks
        context_blocks = []
        if page_text and target_page and doc_name:
            context_blocks.append(f"[Full Page Content from {doc_name} Page {target_page}]:\n{page_text}")
        for p in passages:
            context_blocks.append(f"[{p['document_name']} Page {p['page_number']}]: {p['text']}")
        for f in facts:
            context_blocks.append(f"[Fact from {f.evidence.document_name}]: {f.subject} - {f.attribute}: {f.value} ({f.context_scope or ''})")

        # 1. LLM Generation (Gemini, OpenAI, Ollama)
        if self.llm.is_active():
            sys_prompt = (
                "You are an expert Document Intelligence Assistant. Answer the user's question accurately, "
                "professionally, and strictly based on the provided document excerpts. "
                "If asked to summarize a page, synthesize a clear bulleted breakdown of the key information, sections, and numbers on that page. "
                "Do NOT hallucinate information not present in the context."
            )
            prompt = (
                f"User Question: {query}\n\n"
                f"Verified Document Excerpts:\n" + "\n---\n".join(context_blocks[:6]) + "\n\n"
                "Provide a clear, detailed, and formatted markdown answer directly addressing the user's question:"
            )
            try:
                response = self.llm.generate(prompt, system_prompt=sys_prompt, as_json=False)
                if response and len(response.strip()) > 10:
                    return response.strip()
            except Exception as e:
                logger.debug(f"LLM generation failed: {e}")

        # 2. Specific Page Summary Extraction
        if target_page and (page_text or passages):
            source_doc = doc_name or (passages[0]["document_name"] if passages else "the document")
            text_content = page_text or "\n".join([p["text"] for p in passages if p.get("page_number") == target_page])
            if not text_content and passages:
                text_content = passages[0]["text"]
                source_doc = passages[0]["document_name"]

            paragraphs = [p.strip() for p in text_content.split("\n") if len(p.strip()) > 20]
            if not paragraphs:
                paragraphs = [s.strip() for s in text_content.split(".") if len(s.strip()) > 25]

            bullets = "\n".join([f"- {para}" for para in paragraphs[:5]])

            page_facts = [f for f in facts if f.evidence.page_number == target_page]
            fact_summary = ""
            if page_facts:
                fact_items = "\n".join([f"  • **{f.attribute}**: {f.value}" for f in page_facts[:4]])
                fact_summary = f"\n\n**Extracted Key Metrics on Page {target_page}:**\n{fact_items}"

            return (
                f"### Summary of {source_doc} (Page {target_page})\n\n"
                f"**Key content & sections on this page:**\n"
                f"{bullets}"
                f"{fact_summary}\n\n"
                f"> *Tip: Connect an LLM (such as local Ollama or an API key) for deep generative synthesis.*"
            )

        # 3. Direct Fact Answering
        if facts:
            primary_fact = facts[0]
            ans = f"Based on **{primary_fact.evidence.document_name}** (Page {primary_fact.evidence.page_number}):\n\n"
            ans += f"- **{primary_fact.subject} - {primary_fact.attribute}**: `{primary_fact.value}`"
            if primary_fact.temporal_scope:
                ans += f" (*{primary_fact.temporal_scope}*)"
            if primary_fact.context_scope:
                ans += f" [{primary_fact.context_scope}]"

            if len(facts) > 1:
                ans += "\n\n**Related Observations:**\n"
                for of in facts[1:4]:
                    ans += f"- **{of.attribute}**: `{of.value}` ({of.evidence.document_name}, p.{of.evidence.page_number})\n"
            return ans

        # 4. Structured Excerpt Synthesis
        top_passage = passages[0]
        paragraphs = [p.strip() for p in top_passage["text"].split("\n") if len(p.strip()) > 25]
        if not paragraphs:
            paragraphs = [s.strip() for s in top_passage["text"].split(".") if len(s.strip()) > 25]

        bullet_points = "\n".join([f"- {p}" for p in paragraphs[:3]])
        return (
            f"According to **{top_passage['document_name']}** (Page {top_passage['page_number']}):\n\n"
            f"{bullet_points}\n\n"
            f"> *Grounding Confidence: {int(top_passage.get('score', 0.85) * 100)}%*"
        )
